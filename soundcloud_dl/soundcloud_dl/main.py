"""Phase 1: API track list. Phase 2: stealth Playwright gate orchestration."""

import argparse
import asyncio
import logging

from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    CHROME_PROFILE_DIR,
    DELAY_SECONDS,
    DOWNLOAD_COMMENT,
    DOWNLOAD_EMAIL,
    DOWNLOAD_NAME,
    PLAYLIST_CACHE_ENABLED,
    RESUME_ENABLED,
    SCROLL_BEFORE_CLICK,
    TUNEWRANGLER_SC_PLAYLIST_URL,
    TYPE_DELAY_MS,
    validate_phase1_config,
    validate_phase2_config,
)
from soundcloud_dl.gate_handlers import GateNotSupportedError, get_handler_for_url
from soundcloud_dl.gate_handlers.base import (
    CaptchaEncountered,
    GateStepError,
    StuckGate,
)
from soundcloud_dl.logger import setup_logging
from soundcloud_dl.playlist import TrackItem, extract_track_urls
from soundcloud_dl.playlist_cache import load_cached_tracks, save_cached_tracks
from soundcloud_dl.playwright_browser import attached_browser
from soundcloud_dl.recorder import record
from soundcloud_dl.resume import load_states, record_state, should_skip
from soundcloud_dl.soundcloud_page import SoundCloudPageError, get_gate_url

logger = logging.getLogger("soundcloud_dl.main")


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


async def _run_phase2(playlist_url: str, to_process: list[TrackItem]) -> None:
    """Run gate handler against each track via CDP-attached Chrome; track outcomes."""
    validate_phase2_config()
    counts = {"done": 0, "captcha_pending": 0, "manual_review": 0, "failed": 0}

    async with attached_browser() as context:
        await _ensure_logged_in(context)

        for idx, track in enumerate(to_process, 1):
            logger.info("Phase 2 track %d/%d: %s", idx, len(to_process), track.url)
            outcome: str
            try:
                gate_url = await get_gate_url(context, track.url)
                handler_cls = get_handler_for_url(gate_url)
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
                )
                page = await context.new_page()
                await page.goto(gate_url, wait_until="domcontentloaded", timeout=30_000)
                results = await handler.run(page)
                await page.close()
                logger.info("DOWNLOAD_SUCCESS | %s | steps=%s", track.title or track.url, results)
                outcome = "done"
            except CaptchaEncountered as e:
                logger.warning(
                    "CAPTCHA | %s | %s — tab left open, manual followup needed",
                    track.title or track.url,
                    e.kind,
                )
                outcome = "captcha_pending"
            except StuckGate as e:
                logger.warning(
                    "STUCK | %s | last_step=%s — gate variant; consider --record",
                    track.title or track.url,
                    e.last_step_id,
                )
                outcome = "manual_review"
            except GateNotSupportedError as e:
                logger.warning("SKIPPED | %s | unsupported gate: %s", track.title or track.url, e)
                outcome = "failed"
            except (GateStepError, SoundCloudPageError):
                logger.exception("FAILED | %s", track.title or track.url)
                outcome = "failed"
            except Exception:
                logger.exception("FAILED | %s | unexpected error", track.title or track.url)
                outcome = "failed"

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


async def main_async() -> None:
    """Load config, run Phase 1 (API track list), then Phase 2 (stealth Playwright per track)."""
    setup_logging()
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

    await _run_phase2(playlist_url, to_process)


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
    setup_logging()
    if args.record:
        gate_name, url = args.record
        record(gate_name, url)
        return
    if args.login:
        asyncio.run(_run_login_bootstrap())
        return
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
