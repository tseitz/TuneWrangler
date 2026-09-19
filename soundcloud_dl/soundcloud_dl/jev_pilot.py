"""Single-URL pilot runner for JudgmentGateHandler.

Not routed through the playlist/resume/cache machinery in main.py — same category as
--inspect/--record. Run it with: deno task py -- --jev <gate-or-track-url>
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    DOWNLOAD_COMMENT,
    DOWNLOAD_DIR,
    DOWNLOAD_EMAIL,
    DOWNLOAD_NAME,
    SCROLL_BEFORE_CLICK,
    TYPE_DELAY_MS,
    validate_jev_config,
)
from soundcloud_dl.gate_handlers.base import StepResult
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered
from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler
from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered
from soundcloud_dl.main import _save_debug_artifacts
from soundcloud_dl.playwright_browser import attached_browser
from soundcloud_dl.run_artifacts import RunRecorder
from soundcloud_dl.soundcloud_page import get_gate_url

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

logger = logging.getLogger("soundcloud_dl.jev_pilot")


def _run_name(gate_url: str) -> str:
    """Name the run folder after the gate's host, so a droploud run isn't filed as hypeddit."""
    host = urlparse(gate_url).netloc.removeprefix("www.")
    return f"{host.split('.')[0] or 'gate'}_jev"


async def _do_soundcloud_actions(context: BrowserContext, track_url: str) -> None:
    """Follow/like/repost/comment for real, and say plainly which ones landed.

    Never fatal. A gate can still be satisfiable when one action fails — droploud asks for
    a repost but not a like — so a failure here is reported and the gate run continues.
    """
    from soundcloud_dl.soundcloud_actions import perform  # noqa: PLC0415

    logger.info("SoundCloud actions first: %s", track_url)
    try:
        results = await perform(context, track_url, comment_text=DOWNLOAD_COMMENT)
    except CaptchaEncountered as e:
        logger.warning("SoundCloud actions blocked by %s — continuing to the gate", e.kind)
        return
    except Exception:
        logger.exception("SoundCloud actions failed — continuing to the gate")
        return
    landed = [name for name, r in results.items() if r.ok]
    missed = [f"{name} ({r.detail})" for name, r in results.items() if not r.ok]
    logger.info("SoundCloud actions landed: %s", ", ".join(landed) or "none")
    if missed:
        logger.warning("SoundCloud actions missed: %s", "; ".join(missed))


async def run_jev_pilot(url: str, *, pause: bool = False, sc_actions: bool = False) -> None:
    """Open a gate URL and let JudgmentGateHandler drive it, reporting the outcome."""
    validate_jev_config()

    # No TrackItem for a bare pilot URL — the file keeps Playwright's suggested_filename
    # instead of the real pipeline's "artist - title" rename. Not a bug, just how --jev works.
    logger.info("track_title=None — downloaded file will keep its suggested filename")

    async with attached_browser() as context:
        # A gate URL is accepted directly so the gate can be exercised without loading a
        # SoundCloud page first — which matters when SoundCloud is rate-limiting this browser.
        if "soundcloud.com" in url:
            # Before the gate, not during it. A gate that checks SoundCloud (droploud reads
            # the repost back) then finds the work already done and only has to verify,
            # which keeps the gate loop a pure click-driver with no second browser context
            # to coordinate.
            if sc_actions:
                await _do_soundcloud_actions(context, url)
            gate_url = await get_gate_url(context, url)
        else:
            if sc_actions:
                logger.warning(
                    "--sc-actions needs a SoundCloud track URL to know what to act on; "
                    "skipping the actions for this bare gate URL"
                )
            logger.info("Treating URL as a gate page directly (no SoundCloud lookup)")
            gate_url = url

        recorder = RunRecorder(_run_name(gate_url))

        page = await context.new_page()
        await page.goto(gate_url, wait_until="domcontentloaded", timeout=30_000)
        logger.info("Gate page open: %s", page.url)

        handler = JudgmentGateHandler(
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
            track_title=None,
            recorder=recorder,
        )

        try:
            results = await handler.run(page)
        except CaptchaEncountered as e:
            logger.warning("CAPTCHA | %s — tab left open, manual followup needed", e.kind)
            recorder.finish(url=url, gate_url=gate_url, downloaded=False, terminal="captcha")
            return
        except LoginWallEncountered as e:
            logger.warning("LOGIN_REQUIRED | %s — sign in on that tab, then re-run", e.reason)
            recorder.finish(
                url=url,
                gate_url=gate_url,
                downloaded=False,
                terminal="login_required",
                stopped_at=e.url,
            )
            return
        except Exception as exc:
            await _save_debug_artifacts(page, "jev_pilot")
            recorder.finish(
                url=url, gate_url=gate_url, downloaded=False, terminal=type(exc).__name__
            )
            logger.exception("FAILED | jev pilot run")
            raise

        downloaded = any(
            step_id.endswith("_download") and result == StepResult.EXECUTED
            for step_id, result in results.items()
        )
        recorder.finish(
            url=url,
            gate_url=gate_url,
            downloaded=downloaded,
            turns=len(results),
            terminal="downloaded" if downloaded else "incomplete",
            steps={k: str(v) for k, v in results.items()},
        )
        if downloaded:
            logger.info("DOWNLOAD_SUCCESS | steps=%s", results)
        else:
            await _save_debug_artifacts(page, "jev_pilot")
            logger.warning("GATE_INCOMPLETE | no download step reached | steps=%s", results)

        await page.close()
