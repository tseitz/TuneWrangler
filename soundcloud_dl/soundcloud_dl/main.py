"""Phase 1: API track list. Phase 2: stealth Playwright gate orchestration."""

import argparse
import asyncio
import contextlib
import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from playwright.async_api import Page

    from soundcloud_dl.soundcloud_actions import ActionResult

from playwright.async_api import Error as PlaywrightError

from soundcloud_dl import pending_follows
from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    CHROME_PROFILE_DIR,
    DELAY_SECONDS,
    DOWNLOAD_COMMENT,
    DOWNLOAD_DIR,
    DOWNLOAD_EMAIL,
    DOWNLOAD_NAME,
    HEADED,
    PLAYLIST_CACHE_ENABLED,
    RESUME_ENABLED,
    SCROLL_BEFORE_CLICK,
    TRACK_TIMEOUT_SECONDS,
    TUNEWRANGLER_SC_PLAYLIST_URL,
    TYPE_DELAY_MS,
    get_debug_dir,
    validate_jev_config,
    validate_phase1_config,
    validate_phase2_config,
)
from soundcloud_dl.gate_handlers import (
    GateNotSupportedError,
    detect_handler_from_page,
    get_handler_for_url,
    is_url_blacklisted,
)
from soundcloud_dl.gate_handlers.base import (
    GateStepError,
    StuckGate,
)
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered
from soundcloud_dl.gate_handlers.jev import JevHandler, gate_name_for, judgment_handler_for
from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered
from soundcloud_dl.inspect_gate import inspect_gate
from soundcloud_dl.logger import setup_logging
from soundcloud_dl.playlist import TrackItem, extract_track_urls
from soundcloud_dl.playlist_cache import load_cached_tracks, save_cached_tracks
from soundcloud_dl.playwright_browser import attached_browser
from soundcloud_dl.recorder import record
from soundcloud_dl.resume import (
    TrackState,
    is_given_up_on,
    load_attempts,
    load_states,
    record_state,
    should_skip,
)
from soundcloud_dl.run_artifacts import RunRecorder
from soundcloud_dl.sc_actions_flow import (
    do_soundcloud_actions,
    release_follows_taken,
    requirement_follower,
)
from soundcloud_dl.soundcloud_page import SoundCloudPageError, get_gate_url, try_native_sc_download
from soundcloud_dl.track_naming import judge_track_filename

logger = logging.getLogger("soundcloud_dl.main")


class SoundCloudLoginRequiredError(RuntimeError):
    """Raised when the profile is signed out and nothing can ask a human to fix it."""


class BrowserGoneError(RuntimeError):
    """Raised when Chrome disappears mid-run, so the remaining tracks are not burned.

    Every track after the browser dies fails identically and instantly on its first
    page open. Recording those as "failed" says the gate was tried and it was not.
    """


#: Enough of a reason to act on later without going back to the log. Kept short because it
#: is written per track into processed.json, which is read by eye.
_MAX_REASON_CHARS = 180

#: Hangs in a row before the run stops rather than spending the timeout on every track left.
_MAX_CONSECUTIVE_TIMEOUTS = 2


class TrackOutcome(NamedTuple):
    """What happened to one track, and why.

    The state alone said a track needed attention but never what was wrong with it, so
    picking the work back up meant correlating processed.json against a rotating log that
    had often already aged the answer out.
    """

    state: TrackState
    reason: str = ""


def _why(exc: BaseException) -> str:
    """A one-line reason from an exception, short enough to sit in the resume file."""
    text = " ".join(str(exc).split())
    label = f"{type(exc).__name__}: {text}" if text else type(exc).__name__
    return label[:_MAX_REASON_CHARS]


#: How a dead browser announces itself. Playwright raises TargetClosedError for this but
#: does not export the class from playwright.async_api, so the message is the only public
#: signal — same bind as playwright_browser._CDP_CONTEXT_ERROR.
_BROWSER_GONE_MARKERS = (
    "target page, context or browser has been closed",
    "browser has been closed",
    "target closed",
    "connection closed",
)


def _is_browser_gone(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _BROWSER_GONE_MARKERS)


_UNSAFE_FILENAME_RE = re.compile(r"[^\w\-]")

# Strips common free-download noise tags from SC titles before using as filenames.
# Matches e.g. "[FREE DOWNLOAD]", "(FREE DL)", "[FREE]" etc., case-insensitive.
# Characters illegal in filenames on macOS/Windows/Linux.


async def _save_debug_artifacts(page: "Page", label: str) -> None:
    """Save a screenshot and the page HTML to logs/soundcloud_dl/debug/<label>.{png,html}.

    The HTML matters more than the picture when a gate site redesigns: it carries the
    selectors needed to rewrite that gate's YAML. The two saves are separate so a
    failure to grab one still leaves the other.
    """
    safe = _UNSAFE_FILENAME_RE.sub("_", label)[:80]
    base = get_debug_dir() / safe
    try:
        await page.screenshot(path=f"{base}.png", full_page=True)
        logger.info("DEBUG screenshot saved → %s.png", base)
    except Exception:  # noqa: BLE001
        logger.debug("Could not save debug screenshot", exc_info=True)
    try:
        html = await page.content()
        await asyncio.to_thread(Path(f"{base}.html").write_text, html, encoding="utf-8")
        logger.info("DEBUG html saved → %s.html", base)
    except Exception:  # noqa: BLE001
        logger.debug("Could not save debug HTML", exc_info=True)


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
        "--inspect",
        metavar="URL",
        help=(
            "Open a gate URL, wait for you to complete it by hand, then report which "
            "elements changed. Use this when a gate site redesigns and the handler's "
            "selectors no longer unlock the download."
        ),
    )
    p.add_argument(
        "--jev",
        metavar="URL",
        help=(
            "Pilot: drive a single track/gate URL with JudgmentGateHandler (a TypeSafe "
            "Choice call decides the next element) instead of the YAML step list. "
            "Requires TYPESAFE_API_KEY."
        ),
    )
    p.add_argument(
        "--sc-probe",
        metavar="TRACK_URL",
        help=(
            "Dump SoundCloud's own like/repost/follow/comment controls for a track and its "
            "artist page, so action selectors are read from the live page not guessed."
        ),
    )
    p.add_argument(
        "--sc-do",
        metavar="TRACK_URL",
        help="Follow, like, repost and comment on SoundCloud itself, verifying each action.",
    )
    p.add_argument(
        "--sc-undo",
        metavar="TRACK_URL",
        help="Reverse --sc-do: unfollow, unlike, unrepost (comments are not removed).",
    )
    p.add_argument(
        "--sc-actions",
        action="store_true",
        help=(
            "Do the SoundCloud follow/like/repost/comment for real before opening each "
            "gate, so a gate that verifies against SoundCloud (rather than its own page) "
            "finds them done. Follows this run takes are handed back when it ends. "
            "Applies to the playlist run and to --jev; --jev also needs a track URL, not "
            "a bare gate URL."
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
        "--sc-auth",
        action="store_true",
        help=(
            "Sign in to SoundCloud once in your browser and save a user token, so the API "
            "can follow/like/repost as you instead of driving the web UI. Run this once."
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
    p.add_argument(
        "--retry-unsupported",
        action="store_true",
        help=(
            "Re-queue tracks previously marked 'unsupported' so they can be retried. "
            "Combine with --limit 1 to step through them one at a time."
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


def _get_tracks_to_process(
    tracks: list[TrackItem], playlist_url: str, *, retry_unsupported: bool = False
) -> list[TrackItem]:
    """Apply resume filter: return only tracks whose state is not 'done'."""
    if not RESUME_ENABLED:
        return tracks
    states = load_states(playlist_url)
    attempts = load_attempts(playlist_url)
    if retry_unsupported:
        to_process = [t for t in tracks if states.get(t.url) != "done"]
    else:
        to_process = [t for t in tracks if not should_skip(t.url, states, attempts)]
    skipped = len(tracks) - len(to_process)
    if skipped:
        logger.info("Resume: skipping %d already-done tracks.", skipped)
    # Named individually, because a gate this gave up on is the one thing in the run that
    # nothing will raise again and that only a person can decide to take further.
    for t in tracks:
        if is_given_up_on(t.url, states, attempts):
            logger.info(
                "Resume: %s stayed stuck for %d runs — not trying it again. "
                "Use --retry-unsupported to force it.",
                t.url,
                attempts.get(t.url, 0),
            )
    return to_process


async def _api_download(
    track: TrackItem, download_dir: Path, track_title: str | None
) -> Path | None:
    """The track's own download, straight from the API. Never fatal — the gate is next.

    The playlist read already said downloadable=True, so this only has to fetch. Resolve
    again rather than carrying the raw dict: a playlist cache can be hours old and the
    artist may have withdrawn the download since.
    """
    from soundcloud_dl.soundcloud_api import api_client, fetch_download, resolve  # noqa: PLC0415

    try:
        async with api_client() as client:
            full = await resolve(client, track.url)
        return await fetch_download(full, download_dir, track_title)
    except Exception:  # noqa: BLE001
        # Auth, network and a resolve that answers something other than a track all end
        # the same way: say so, then let the gate flow have its turn.
        logger.warning("API download failed for %s — trying the gate", track.url, exc_info=True)
        return None


async def _process_track(  # noqa: C901, PLR0911, PLR0912, PLR0915
    context: object, track: TrackItem, *, pause: bool = False, sc_actions: bool = False
) -> TrackOutcome:
    """Attempt the gate flow for one track; return outcome string."""
    track_label = track.title or track.url
    track_title = await judge_track_filename(track.title, track.artist)

    page = None
    recorder: RunRecorder | None = None
    actions: dict[str, ActionResult] = {}
    # Released in the finally, so a run that ends without a file still gives back what it
    # spent. A gate that charges follows and then never unlocks is how the account walks
    # into SoundCloud's 2000-following cap. The two states below are the exceptions: both
    # leave the tab open for a person to finish, and the gate is still checking.
    keep_follows = False
    # Set as the run goes, so the finally can record how it ended whichever way it left.
    final_url: str | None = None
    results: dict[str, Any] = {}
    downloaded = False
    terminal = "no_gate_reached"
    try:
        # The API's own answer, and the only path that needs no page at all. A track page
        # renders nothing when SoundCloud's SPA throws, and the download is then invisible
        # to any amount of scraping while this keeps working — which is how a track with
        # downloadable=True came to be recorded as having no gate and no download.
        if track.downloadable and DOWNLOAD_DIR:
            saved = await _api_download(track, Path(DOWNLOAD_DIR), track_title)
            if saved is not None:
                logger.info("DOWNLOAD_SUCCESS | %s | API download → %s", track_label, saved)
                return TrackOutcome("done")

        # SoundCloud tracks with a native download button (no gate) are handled here.
        # Try this before the gate flow so we don't waste time hunting for a gate link.
        if (
            not track.purchase_url
            and DOWNLOAD_DIR
            and await try_native_sc_download(
                context,  # type: ignore[arg-type]
                track.url,
                DOWNLOAD_DIR,
                track_title,
            )
        ):
            logger.info("DOWNLOAD_SUCCESS | %s | native SC download", track_label)
            return TrackOutcome("done")

        if track.purchase_url:
            gate_url = track.purchase_url
            logger.info("Using purchase_url from API: %s", gate_url)
        else:
            gate_url = await get_gate_url(context, track.url)  # type: ignore[arg-type]
        if is_url_blacklisted(gate_url):
            logger.warning("UNSUPPORTED | %s | blacklisted gate: %s", track_label, gate_url)
            return TrackOutcome("unsupported", f"blacklisted gate: {gate_url}")

        # After the blacklist check, because a gate we will not open must not cost
        # anything: the follow is given back but the comment is permanent and only the
        # user can delete it. Before the gate opens, though — a gate that checks
        # SoundCloud (droploud reads the repost back) then finds the work already done
        # and only has to verify, which keeps the gate loop a pure click-driver.
        if sc_actions:
            await do_soundcloud_actions(
                context,  # type: ignore[arg-type]
                track.url,
                comment_text=DOWNLOAD_COMMENT,
                into=actions,
            )
        page = await context.new_page()  # type: ignore[union-attr]
        await page.goto(gate_url, wait_until="domcontentloaded", timeout=30_000)
        final_url = page.url
        if final_url != gate_url:
            logger.info("Gate URL redirected: %s → %s", gate_url, final_url)
        try:
            handler_cls = get_handler_for_url(final_url)
        except GateNotSupportedError:
            # URL not recognised — inspect page content for known gate structure
            # (handles custom-domain / white-label gates, e.g. Hypeddit on own domain).
            detected = await detect_handler_from_page(page)
            if detected is not None:
                handler_cls = detected
                logger.info(
                    "Content-detected handler %s for unrecognised URL: %s",
                    handler_cls.__name__,
                    final_url,
                )
            else:
                handler_cls = judgment_handler_for(final_url)
                logger.info("No handler registered for %s — driving it with judgment", final_url)
        # The page is open but nothing has been clicked yet. A judgment gate builds its
        # TypeSafe client on the first turn, so without this a missing key surfaces after
        # the run has already handed over follows it cannot take back.
        if issubclass(handler_cls, JevHandler):
            validate_jev_config()
        # Only judgment handlers take one; a YAML handler has no per-turn decision to record.
        extra: dict[str, Any] = {}
        if issubclass(handler_cls, JevHandler):
            recorder = RunRecorder(gate_name_for(final_url))
            extra["recorder"] = recorder
            if sc_actions:
                # Follows the gate names mid-run land in `actions` too, so the release
                # below covers them and not just the four opening actions.
                extra["on_requirements"] = requirement_follower(actions)
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
            **extra,
        )
        results = await handler.run(page)
        downloaded = handler.downloaded
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
                    downloaded = downloaded or real_handler.downloaded

            except GateNotSupportedError:
                pass
        # The handler reports whether a file reached disk. Not the step ids: every gate
        # config has a non-terminal step named for the download it is waiting on —
        # hypeddit's wait_for_download_ready, toneden's wait_for_download_unlock — so a run
        # that only ever waited was recorded done, and done is never retried.
        if not downloaded:
            # Before the page closes, and here rather than only on the exception paths:
            # a gate that runs to the end and produces nothing is the shape a new gate
            # variant takes, and it is the one outcome that used to be recorded with
            # nothing to look at afterwards.
            await _save_debug_artifacts(page, track_label)
        if recorder is not None:
            recorder.finish(
                url=track.url,
                gate_url=final_url,
                downloaded=downloaded,
                turns=len(results),
                terminal="downloaded" if downloaded else "incomplete",
                steps={k: str(v) for k, v in results.items()},
            )
        await page.close()
        page = None
        if downloaded:
            logger.info("DOWNLOAD_SUCCESS | %s | steps=%s", track_label, results)
            return TrackOutcome("done")
        else:  # noqa: RET505
            logger.warning(
                "GATE_INCOMPLETE | %s | no download step reached | steps=%s",
                track_label,
                results,
            )
            return TrackOutcome("manual_review", "gate ran out of steps with no download")
    except CaptchaEncountered as e:
        terminal = "captcha"
        keep_follows = True
        logger.warning(
            "CAPTCHA | %s | %s — tab left open, manual followup needed",
            track_label,
            e.kind,
        )
        return TrackOutcome("captcha_pending", str(e.kind))
    except LoginWallEncountered as e:
        terminal = "login_required"
        keep_follows = True
        logger.warning(
            "LOGIN_REQUIRED | %s | %s — tab left open, finish it there and re-run",
            track_label,
            e.reason,
        )
        return TrackOutcome("login_required", e.reason)
    except StuckGate as e:
        terminal = "StuckGate"
        if page:
            await _save_debug_artifacts(page, track_label)
        logger.warning(
            "STUCK | %s | last_step=%s — gate variant; consider --record",
            track_label,
            e.last_step_id,
        )
        return TrackOutcome("manual_review", f"stuck at {e.last_step_id}")
    except GateNotSupportedError as e:
        terminal = "unsupported"
        logger.warning("UNSUPPORTED | %s | no handler for gate: %s", track_label, e)
        return TrackOutcome("unsupported", f"no handler: {e}")
    except SoundCloudPageError as e:
        terminal = "no_gate"
        # SC page issues (no gate button found, "FREE DL" text not a real gate link,
        # no new tab opened) are human-review candidates, not automatic retries.
        if page:
            await _save_debug_artifacts(page, track_label)
        logger.warning("NO_GATE | %s | %s", track_label, e)
        return TrackOutcome("manual_review", f"no gate: {e}")
    except GateStepError as e:
        terminal = "GateStepError"
        if page:
            await _save_debug_artifacts(page, track_label)
        logger.exception("FAILED | %s", track_label)
        return TrackOutcome("failed", _why(e))
    except PlaywrightError as e:
        terminal = type(e).__name__
        if _is_browser_gone(e):
            msg = f"Chrome closed while working on {track_label}"
            raise BrowserGoneError(msg) from e
        if page:
            await _save_debug_artifacts(page, track_label)
        logger.exception("FAILED | %s | %s", track_label, type(e).__name__)
        return TrackOutcome("failed", _why(e))
    except Exception as e:
        terminal = type(e).__name__
        if page:
            await _save_debug_artifacts(page, track_label)
        logger.exception("FAILED | %s | unexpected error", track_label)
        return TrackOutcome("failed", _why(e))
    finally:
        # Whatever happened, the run dir gets a result. finish() keeps the first call, so
        # the detailed record written on the way through wins and this only fills the gap
        # left by an exception — which is precisely the run worth looking at afterwards.
        if recorder is not None:
            recorder.finish(
                url=track.url,
                gate_url=final_url,
                downloaded=downloaded,
                turns=len(results),
                terminal=terminal,
                steps={k: str(v) for k, v in results.items()},
            )
        if page:
            # A page belonging to a browser that has gone raises on close, which would
            # replace whatever is already on its way out with a less useful error.
            with contextlib.suppress(Exception):
                await page.close()
        # Never before the run has ended: giving a follow back mid-run takes it away from
        # the gate that is still checking for it.
        if keep_follows:
            pending_follows.hold(actions)
        else:
            await release_follows_taken(actions)


async def _run_phase2(
    playlist_url: str,
    to_process: list[TrackItem],
    *,
    pause: bool = False,
    sc_actions: bool = False,
) -> None:
    """Run gate handler against each track via CDP-attached Chrome; track outcomes."""
    validate_phase2_config()
    counts = {
        "done": 0,
        "unsupported": 0,
        "captcha_pending": 0,
        "login_required": 0,
        "manual_review": 0,
        "failed": 0,
    }
    needs_attention: list[tuple[TrackItem, TrackOutcome]] = []

    # --pause forces a window regardless of config, and the login guard below has to ask
    # about the browser it actually got, not the one the config asked for.
    headed = bool(pause or HEADED)
    async with attached_browser(headed=True if pause else None) as context:
        await _ensure_logged_in(context, headed=headed)
        # Before any track, so follows an earlier run held for a tab that has since been
        # dealt with do not sit on the account indefinitely.
        if sc_actions:
            await pending_follows.sweep()

        timed_out_in_a_row = 0
        for idx, track in enumerate(to_process, 1):
            logger.info("Phase 2 track %d/%d: %s", idx, len(to_process), track.url)
            try:
                outcome = await asyncio.wait_for(
                    _process_track(context, track, pause=pause, sc_actions=sc_actions),
                    timeout=TRACK_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                # Playwright's TimeoutError subclasses its own Error, not this one, so a
                # bounded step timing out inside the track still lands on its own handler.
                timed_out_in_a_row += 1
                logger.warning(
                    "Gave up on %s after %ds — it stopped making progress.",
                    track.title or track.url,
                    TRACK_TIMEOUT_SECONDS,
                )
                outcome = TrackOutcome(
                    "manual_review", f"hung; no progress for {TRACK_TIMEOUT_SECONDS}s"
                )
            except BrowserGoneError:
                # Deliberately no record_state: this track and the ones after it were never
                # tried, and writing "failed" would spend their retry budget on a browser
                # crash rather than on anything the gates did.
                logger.exception(
                    "Stopping: the browser went away with %d of %d tracks left. "
                    "They keep their current state and will be picked up next run.",
                    len(to_process) - idx + 1,
                    len(to_process),
                )
                break
            else:
                timed_out_in_a_row = 0
            counts[outcome.state] += 1
            if outcome.state != "done":
                needs_attention.append((track, outcome))
            if RESUME_ENABLED:
                record_state(playlist_url, track.url, outcome.state, reason=outcome.reason)
            if timed_out_in_a_row >= _MAX_CONSECUTIVE_TIMEOUTS:
                # One hang is a bad gate; several running together is the browser itself,
                # and every track after it would burn the full timeout to reach the same
                # place. Their state is left alone, so the next run still has them.
                logger.error(
                    "Stopping: %d tracks in a row hung. Chrome is wedged — the remaining "
                    "%d keep their current state. Re-run once it has been restarted.",
                    timed_out_in_a_row,
                    len(to_process) - idx,
                )
                break
            if idx < len(to_process) and DELAY_SECONDS > 0:
                await asyncio.sleep(DELAY_SECONDS)

    _print_summary(counts)
    _print_worklist(needs_attention)


def _print_worklist(items: list[tuple[TrackItem, TrackOutcome]]) -> None:
    """List what did not finish, and why, so the next run has somewhere to start."""
    if not items:
        return
    logger.info("Needs attention (%d):", len(items))
    for track, outcome in items:
        logger.info("  %-14s %s", outcome.state, track.title or track.url)
        if outcome.reason:
            logger.info("  %-14s   ↳ %s", "", outcome.reason)
        logger.info("  %-14s   %s", "", track.url.split("?")[0])
    logger.info("─" * 50)


def _print_summary(counts: dict[str, int]) -> None:
    """Print structured end-of-run summary."""
    logger.info("─" * 50)
    logger.info("✓  %d downloaded", counts["done"])
    logger.info("⊘  %d unsupported gate (skipped permanently)", counts["unsupported"])
    logger.info("⚠   %d captcha_pending (tabs open: see Chrome)", counts["captcha_pending"])
    logger.info("🔒  %d login_required (sign in yourself, then re-run)", counts["login_required"])
    logger.info("?   %d manual_review (gate variant — consider --record)", counts["manual_review"])
    logger.info("✗   %d failed", counts["failed"])
    logger.info("─" * 50)


async def _ensure_logged_in(context, *, headed: bool) -> None:  # noqa: ANN001
    """Navigate to SoundCloud and pause for manual login if signed out."""
    page = await context.new_page()
    try:
        await page.goto("https://soundcloud.com", wait_until="domcontentloaded", timeout=30_000)
        # The "Sign in" button is only present when logged out.
        sign_in = await page.query_selector("button:has-text('Sign in'), a:has-text('Sign in')")
        if sign_in is not None:
            # Waiting on stdin needs someone at the terminal AND a window to log in to.
            # An unattended headless batch has neither, and blocks here until killed —
            # which looks exactly like a run that is working, for as long as it is left.
            if not (sys.stdin.isatty() and headed):
                msg = (
                    "Not logged into SoundCloud and no way to ask: run with "
                    "TUNEWRANGLER_SC_HEADED=1 from a terminal and sign in, then re-run."
                )
                raise SoundCloudLoginRequiredError(msg)
            logger.warning(
                "Not logged into SoundCloud. Please log in in the open Chrome window, "
                "then press Enter here to continue."
            )
            await asyncio.to_thread(input, "")
        else:
            logger.info("SoundCloud session detected — continuing.")
    finally:
        await page.close()


async def main_async(
    limit: int | None = None,
    *,
    pause: bool = False,
    retry_unsupported: bool = False,
    sc_actions: bool = False,
) -> None:
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

    to_process = _get_tracks_to_process(tracks, playlist_url, retry_unsupported=retry_unsupported)
    if not to_process:
        logger.info("No tracks left to process (all already done or none found).")
        return

    if limit is not None:
        to_process = to_process[:limit]
        logger.info("--limit %d: processing %d track(s)", limit, len(to_process))

    await _run_phase2(playlist_url, to_process, pause=pause, sc_actions=sc_actions)


async def _run_login_bootstrap() -> None:
    """Open SoundCloud in attached Chrome and wait for manual login."""
    logger.info("Login session will persist in: %s", CHROME_PROFILE_DIR)
    # A window is the whole point here: the user signs in by hand.
    async with attached_browser(headed=True) as context:
        page = await context.new_page()
        await page.goto("https://soundcloud.com", wait_until="domcontentloaded", timeout=30_000)
        logger.info("Browser opened to SoundCloud for manual login.")
        logger.info("After login completes, press Enter here to close.")
        await asyncio.to_thread(input, "")
        await page.close()


def _run_one_shot(args: argparse.Namespace) -> bool:
    """Run whichever standalone tool the flags asked for. True if one ran."""
    if args.record:
        gate_name, url = args.record
        record(gate_name, url)
    elif args.inspect:
        asyncio.run(inspect_gate(args.inspect))
    elif args.sc_auth:
        from soundcloud_dl.soundcloud_auth import authorize  # noqa: PLC0415

        asyncio.run(authorize())
    elif args.sc_do or args.sc_undo:
        from soundcloud_dl.soundcloud_actions import run_actions  # noqa: PLC0415

        asyncio.run(
            run_actions(args.sc_do or args.sc_undo, DOWNLOAD_COMMENT, undo=bool(args.sc_undo))
        )
    elif args.sc_probe:
        from soundcloud_dl.soundcloud_actions import probe_urls  # noqa: PLC0415

        asyncio.run(probe_urls(args.sc_probe))
    elif args.jev:
        from soundcloud_dl.jev_pilot import run_jev_pilot  # noqa: PLC0415

        asyncio.run(run_jev_pilot(args.jev, pause=args.pause, sc_actions=args.sc_actions))
    elif args.login:
        asyncio.run(_run_login_bootstrap())
    else:
        return False
    return True


def main() -> None:
    """Run Phase 1 then Phase 2; entrypoint for CLI."""
    args = _parse_args()
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=log_level)
    if _run_one_shot(args):
        return
    asyncio.run(
        main_async(
            limit=args.limit,
            pause=args.pause,
            retry_unsupported=args.retry_unsupported,
            sc_actions=args.sc_actions,
        )
    )


if __name__ == "__main__":
    main()
