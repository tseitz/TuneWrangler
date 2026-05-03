"""Phase 1: API track list. Phase 2: stealth Playwright gate orchestration."""

import argparse
import asyncio
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    CHROME_PROFILE_DIR,
    DELAY_SECONDS,
    DOWNLOAD_COMMENT,
    DOWNLOAD_DIR,
    DOWNLOAD_EMAIL,
    DOWNLOAD_NAME,
    PLAYLIST_CACHE_ENABLED,
    RESUME_ENABLED,
    SCROLL_BEFORE_CLICK,
    TUNEWRANGLER_SC_PLAYLIST_URL,
    TYPE_DELAY_MS,
    get_log_dir,
    validate_phase1_config,
    validate_phase2_config,
)
from soundcloud_dl.gate_handlers import GateNotSupportedError, get_handler_for_url
from soundcloud_dl.gate_handlers.base import (
    CaptchaEncountered,
    GateStepError,
    StepResult,
    StuckGate,
)
from soundcloud_dl.logger import setup_logging
from soundcloud_dl.playlist import TrackItem, extract_track_urls
from soundcloud_dl.playlist_cache import load_cached_tracks, save_cached_tracks
from soundcloud_dl.playwright_browser import attached_browser
from soundcloud_dl.recorder import record
from soundcloud_dl.resume import load_states, record_state, should_skip
from soundcloud_dl.soundcloud_page import SoundCloudPageError, get_gate_url, try_native_sc_download

logger = logging.getLogger("soundcloud_dl.main")

_UNSAFE_FILENAME_RE = re.compile(r"[^\w\-]")

# Strips common free-download noise tags from SC titles before using as filenames.
# Matches e.g. "[FREE DOWNLOAD]", "(FREE DL)", "[FREE]" etc., case-insensitive.
_FREE_DL_RE = re.compile(r"\s*[\(\[]\s*free\s*(download|dl)?\s*[\)\]]", re.IGNORECASE)
# Characters illegal in filenames on macOS/Windows/Linux.
_UNSAFE_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_sc_title(title: str) -> str:
    """Strip free-download noise and filesystem-unsafe chars from a SoundCloud title."""
    title = _FREE_DL_RE.sub("", title)
    title = _UNSAFE_CHARS_RE.sub("", title)
    return title.strip()


async def _save_debug_screenshot(page: "Page", label: str) -> None:
    """Save a screenshot to logs/debug_<label>.png for post-mortem inspection."""
    try:
        safe = _UNSAFE_FILENAME_RE.sub("_", label)[:80]
        path = get_log_dir() / f"debug_{safe}.png"
        await page.screenshot(path=str(path), full_page=True)
        logger.info("DEBUG screenshot saved → %s", path)
    except Exception:  # noqa: BLE001
        logger.debug("Could not save debug screenshot", exc_info=True)


def _parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    p = argparse.ArgumentParser(
        description=(
            "SoundCloud free-download automation (Phase 1: API, Phase 2: stealth Playwright)."
        )
    )
    p.add_argument(
        "--record",
        nargs=2,
        metavar=("GATE_NAME", "URL"),
        help=(
            "Bootstrap a new gate config: launch playwright codegen and scaffold GATE_NAME.yaml."
        ),
    )
    p.add_argument(
        "--login",
        action="store_true",
        help=(
            "Open headed browser for manual SoundCloud login "
            "and persist session in browser profile."
        ),
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging (shows per-selector probe results and full tracebacks).",
    )
    p.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Process at most N tracks (useful for iterating on a single gate).",
    )
    p.add_argument(
        "--pause",
        action="store_true",
        help="Pause before each gate step (waits for Enter) to inspect the page in DevTools.",
    )
    return p.parse_args()


def _load_tracks(playlist_url: str) -> list[TrackItem]:
    """Load track list from cache or API; save to cache if enabled."""
    tracks: list[TrackItem] | None = None
    if PLAYLIST_CACHE_ENABLED:
        tracks = load_cached_tracks(playlist_url)
        if tracks is not None:
            logger.info("Phase 1: using cached track list (%d tracks)", len(tracks))
    if tracks is None:
        tracks = extract_track_urls(playlist_url)
        if PLAYLIST_CACHE_ENABLED:
            save_cached_tracks(playlist_url, tracks)
    return tracks


def _log_track_list(playlist_url: str, tracks: list[TrackItem]) -> None:
    """Log playlist URL and each track."""
    logger.info("Playlist URL: %s", playlist_url)
    logger.info("Number of tracks found: %d", len(tracks))
    for i, t in enumerate(tracks, 1):
        if t.title:
            logger.info("  %d. %s | %s", i, t.title, t.url)
        else:
            logger.info("  %d. %s", i, t.url)


def _get_tracks_to_process(tracks: list[TrackItem], playlist_url: str) -> list[TrackItem]:
    """Apply resume filter: return only tracks whose state is not 'done'."""
    if not RESUME_ENABLED:
        return tracks
    states = load_states(playlist_url)
    to_process = [t for t in tracks if not should_skip(t.url, states)]
    skipped = len(tracks) - len(to_process)
    if skipped:
        logger.info("Resume: skipping %d already-done tracks.", skipped)
    return to_process


async def _process_track(  # noqa: C901, PLR0911, PLR0912
    context: object, track: TrackItem, *, pause: bool = False
) -> str:
    """Attempt the gate flow for one track; return outcome string."""
    track_label = track.title or track.url
    track_title = _sanitize_sc_title(track.title) if track.title else None
    if track_title and track.artist and " - " not in track_title:
        safe_artist = _UNSAFE_CHARS_RE.sub("", track.artist).strip()
        if safe_artist:
            track_title = f"{safe_artist} - {track_title}"

    page = None
    try:
        # SoundCloud tracks with a native download button (no gate) are handled here.
        # Try this before the gate flow so we don't waste time hunting for a gate link.
        if not track.purchase_url and DOWNLOAD_DIR and await try_native_sc_download(
            context,  # type: ignore[arg-type]
            track.url,
            DOWNLOAD_DIR,
            track_title,
        ):
            logger.info("DOWNLOAD_SUCCESS | %s | native SC download", track_label)
            return "done"

        if track.purchase_url:
            gate_url = track.purchase_url
            logger.info("Using purchase_url from API: %s", gate_url)
        else:
            gate_url = await get_gate_url(context, track.url)  # type: ignore[arg-type]
        page = await context.new_page()  # type: ignore[union-attr]
        await page.goto(gate_url, wait_until="domcontentloaded", timeout=30_000)
        final_url = page.url
        if final_url != gate_url:
            logger.info("Gate URL redirected: %s → %s", gate_url, final_url)
        handler_cls = get_handler_for_url(final_url)
        handler = handler_cls(
            template_vars={
                "email": DOWNLOAD_EMAIL,
                "name": DOWNLOAD_NAME,
                "comment": DOWNLOAD_COMMENT,
            },
            action_delay_min_ms=ACTION_DELAY_MIN_MS,
            action_delay_max_ms=ACTION_DELAY_MAX_MS,
            type_delay_ms=TYPE_DELAY_MS,
            scroll_before_click=SCROLL_BEFORE_CLICK,
            pause=pause,
            download_dir=DOWNLOAD_DIR,
            track_title=track_title,
        )
        results = await handler.run(page)
        # Meta-gate redirect: if the handler navigated us to a different gate
        # (e.g. fanlink.tv → toneden.io), run the real gate handler on the same page.
        post_url = page.url
        if post_url and post_url != final_url:
            try:
                real_handler_cls = get_handler_for_url(post_url)
                if real_handler_cls is not handler_cls:
                    logger.info("Meta-gate → %s, running %s", post_url, real_handler_cls.__name__)
                    real_handler = real_handler_cls(
                        template_vars={
                            "email": DOWNLOAD_EMAIL,
                            "name": DOWNLOAD_NAME,
                            "comment": DOWNLOAD_COMMENT,
                        },
                        action_delay_min_ms=ACTION_DELAY_MIN_MS,
                        action_delay_max_ms=ACTION_DELAY_MAX_MS,
                        type_delay_ms=TYPE_DELAY_MS,
                        scroll_before_click=SCROLL_BEFORE_CLICK,
                        pause=pause,
                        download_dir=DOWNLOAD_DIR,
                        track_title=track_title,
                    )
                    results = await real_handler.run(page)
            except GateNotSupportedError:
                pass
        await page.close()
        page = None
        # Any step with "download" in its ID that executed counts as success —
        # handles both the standard final_download step and alternate paths like
        # toneden's click_direct_download variant.
        download_executed = any(
            "download" in step_id and result == StepResult.EXECUTED
            for step_id, result in results.items()
        )
        if download_executed:
            logger.info("DOWNLOAD_SUCCESS | %s | steps=%s", track_label, results)
            return "done"
        else:  # noqa: RET505
            logger.warning(
                "GATE_INCOMPLETE | %s | no download step reached | steps=%s",
                track_label,
                results,
            )
            return "manual_review"
    except CaptchaEncountered as e:
        logger.warning(
            "CAPTCHA | %s | %s — tab left open, manual followup needed",
            track_label,
            e.kind,
        )
        return "captcha_pending"
    except StuckGate as e:
        if page:
            await _save_debug_screenshot(page, track_label)
        logger.warning(
            "STUCK | %s | last_step=%s — gate variant; consider --record",
            track_label,
            e.last_step_id,
        )
        return "manual_review"
    except GateNotSupportedError as e:
        logger.warning("UNSUPPORTED | %s | no handler for gate: %s", track_label, e)
        return "unsupported"
    except SoundCloudPageError as e:
        # SC page issues (no gate button found, "FREE DL" text not a real gate link,
        # no new tab opened) are human-review candidates, not automatic retries.
        if page:
            await _save_debug_screenshot(page, track_label)
        logger.warning("NO_GATE | %s | %s", track_label, e)
        return "manual_review"
    except GateStepError:
        if page:
            await _save_debug_screenshot(page, track_label)
        logger.exception("FAILED | %s", track_label)
        return "failed"
    except Exception:
        if page:
            await _save_debug_screenshot(page, track_label)
        logger.exception("FAILED | %s | unexpected error", track_label)
        return "failed"
    finally:
        if page:
            await page.close()


async def _run_phase2(
    playlist_url: str, to_process: list[TrackItem], *, pause: bool = False
) -> None:
    """Run gate handler against each track via CDP-attached Chrome; track outcomes."""
    validate_phase2_config()
    counts = {"done": 0, "unsupported": 0, "captcha_pending": 0, "manual_review": 0, "failed": 0}

    async with attached_browser() as context:
        await _ensure_logged_in(context)

        for idx, track in enumerate(to_process, 1):
            logger.info("Phase 2 track %d/%d: %s", idx, len(to_process), track.url)
            outcome = await _process_track(context, track, pause=pause)
            counts[outcome] += 1
            if RESUME_ENABLED:
                record_state(playlist_url, track.url, outcome)
            if idx < len(to_process) and DELAY_SECONDS > 0:
                await asyncio.sleep(DELAY_SECONDS)

    _print_summary(counts)


def _print_summary(counts: dict[str, int]) -> None:
    """Print structured end-of-run summary."""
    logger.info("─" * 50)
    logger.info("✓  %d downloaded", counts["done"])
    logger.info("⊘  %d unsupported gate (skipped permanently)", counts["unsupported"])
    logger.info("⚠   %d captcha_pending (tabs open: see Chrome)", counts["captcha_pending"])
    logger.info("?   %d manual_review (gate variant — consider --record)", counts["manual_review"])
    logger.info("✗   %d failed", counts["failed"])
    logger.info("─" * 50)


async def _ensure_logged_in(context) -> None:  # noqa: ANN001
    """Navigate to SoundCloud and pause for manual login if signed out."""
    page = await context.new_page()
    try:
        await page.goto("https://soundcloud.com", wait_until="domcontentloaded", timeout=30_000)
        # The "Sign in" button is only present when logged out.
        sign_in = await page.query_selector("button:has-text('Sign in'), a:has-text('Sign in')")
        if sign_in is not None:
            logger.warning(
                "Not logged into SoundCloud. Please log in in the open Chrome window, "
                "then press Enter here to continue."
            )
            await asyncio.to_thread(input, "")
        else:
            logger.info("SoundCloud session detected — continuing.")
    finally:
        await page.close()


async def main_async(limit: int | None = None, *, pause: bool = False) -> None:
    """Load config, run Phase 1 (API track list), then Phase 2 (stealth Playwright per track)."""
    validate_phase1_config()
    if not TUNEWRANGLER_SC_PLAYLIST_URL:
        msg = "TUNEWRANGLER_SC_PLAYLIST_URL is required"
        raise RuntimeError(msg)
    playlist_url = TUNEWRANGLER_SC_PLAYLIST_URL.strip()
    logger.info("Phase 1: extracting track URLs from playlist: %s", playlist_url)

    tracks = _load_tracks(playlist_url)
    _log_track_list(playlist_url, tracks)

    if not tracks:
        logger.info("No tracks to process; skipping Phase 2.")
        return

    to_process = _get_tracks_to_process(tracks, playlist_url)
    if not to_process:
        logger.info("No tracks left to process (all already done or none found).")
        return

    if limit is not None:
        to_process = to_process[:limit]
        logger.info("--limit %d: processing %d track(s)", limit, len(to_process))

    await _run_phase2(playlist_url, to_process, pause=pause)


async def _run_login_bootstrap() -> None:
    """Open SoundCloud in attached Chrome and wait for manual login."""
    logger.info("Login session will persist in: %s", CHROME_PROFILE_DIR)
    async with attached_browser() as context:
        page = await context.new_page()
        await page.goto("https://soundcloud.com", wait_until="domcontentloaded", timeout=30_000)
        logger.info("Browser opened to SoundCloud for manual login.")
        logger.info("After login completes, press Enter here to close.")
        await asyncio.to_thread(input, "")
        await page.close()


def main() -> None:
    """Run Phase 1 then Phase 2; entrypoint for CLI."""
    args = _parse_args()
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)
    if args.record:
        gate_name, url = args.record
        record(gate_name, url)
        return
    if args.login:
        asyncio.run(_run_login_bootstrap())
        return
    asyncio.run(main_async(limit=args.limit, pause=args.pause))


if __name__ == "__main__":
    main()
