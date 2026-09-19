"""Single-URL pilot runner for JudgmentGateHandler.

Not routed through the playlist/resume/cache machinery in main.py — same category as
--inspect/--record. Run it with: deno task py -- --jev <gate-or-track-url>
"""

from __future__ import annotations

import logging

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
from soundcloud_dl.main import _save_debug_artifacts
from soundcloud_dl.playwright_browser import attached_browser
from soundcloud_dl.run_artifacts import RunRecorder
from soundcloud_dl.soundcloud_page import get_gate_url

logger = logging.getLogger("soundcloud_dl.jev_pilot")


async def run_jev_pilot(url: str, *, pause: bool = False) -> None:
    """Open a gate URL and let JudgmentGateHandler drive it, reporting the outcome."""
    validate_jev_config()

    # No TrackItem for a bare pilot URL — the file keeps Playwright's suggested_filename
    # instead of the real pipeline's "artist - title" rename. Not a bug, just how --jev works.
    logger.info("track_title=None — downloaded file will keep its suggested filename")

    recorder = RunRecorder("hypeddit_jev")

    async with attached_browser() as context:
        gate_url = await get_gate_url(context, url)
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
