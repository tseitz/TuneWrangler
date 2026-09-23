"""Single-URL pilot runner for JudgmentGateHandler.

Not routed through the playlist/resume/cache machinery in main.py — same category as
--inspect/--record. Run it with: deno task py --jev <gate-or-track-url>
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from soundcloud_dl import pending_follows
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
from soundcloud_dl.gate_handlers import GateNotSupportedError, get_handler_for_url
from soundcloud_dl.gate_handlers.base import GateHandler, StepResult
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered
from soundcloud_dl.gate_handlers.jev import gate_name_for
from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler
from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered
from soundcloud_dl.main import _save_debug_artifacts
from soundcloud_dl.playwright_browser import attached_browser
from soundcloud_dl.run_artifacts import RunRecorder
from soundcloud_dl.sc_actions_flow import (
    do_soundcloud_actions,
    release_follows_taken,
    requirement_follower,
)
from soundcloud_dl.soundcloud_page import get_gate_url
from soundcloud_dl.track_naming import judge_track_filename

if TYPE_CHECKING:
    from soundcloud_dl.soundcloud_actions import ActionResult

logger = logging.getLogger("soundcloud_dl.jev_pilot")


def _apply_oauth_policy(handler: GateHandler, gate_url: str) -> None:
    """Copy the OAuth policy registered for this host, off a class we deliberately do not use.

    --jev means "drive this with JudgmentGateHandler whatever the host", so this path builds
    that class directly instead of the registered one. The policy is not part of what --jev
    is overriding, though: without this the one gate that must never have its account grant
    auto-approved gets it auto-approved here and nowhere else.
    """
    try:
        policy = get_handler_for_url(gate_url)
    except GateNotSupportedError:
        policy = JudgmentGateHandler
    handler.auto_approve_oauth = policy.auto_approve_oauth
    handler.oauth_approve_once = policy.oauth_approve_once


async def _resolve_track_title(url: str) -> str | None:
    """Name the file "<artist> - <title>", the same as the playlist pipeline does.

    A bare gate URL carries no track, and the resolve needs a working API token, so this
    is allowed to come back empty — the download then keeps the name the gate suggested,
    which is worse but is not worth failing a run over.
    """
    if "soundcloud.com" not in url:
        return None
    try:
        from soundcloud_dl.soundcloud_api import api_client, resolve  # noqa: PLC0415

        async with api_client() as client:
            track = await resolve(client, url)
        title = await judge_track_filename(
            track.get("title"), (track.get("user") or {}).get("username")
        )
    except Exception:  # noqa: BLE001
        # Auth, network and a resolve that answers something other than a track all end the
        # same way here: name the file what the gate called it and get on with the run.
        logger.warning(
            "Could not read the track's title from SoundCloud — the download will keep "
            "the filename the gate suggests",
            exc_info=True,
        )
        return None
    logger.info("Downloads will be named %r", title)
    return title


async def _settle_follows(actions: dict[str, ActionResult], *, resuming: bool) -> None:
    """Give the follows back, or write them down for a run that can.

    Never before the run has ended: handing one back mid-run takes it away from the gate
    that is still checking for it. `resuming` means a tab was left open for a person to
    finish, so the gate still needs them and a later run releases them instead.
    """
    if resuming:
        pending_follows.hold(actions)
    else:
        await release_follows_taken(actions)


async def run_jev_pilot(url: str, *, pause: bool = False, sc_actions: bool = False) -> None:
    """Open a gate URL and let JudgmentGateHandler drive it, reporting the outcome."""
    validate_jev_config()

    actions: dict[str, ActionResult] = {}
    track_title = await _resolve_track_title(url)

    # --pause exists so the page can be inspected between steps; that needs a window.
    # None rather than False otherwise, so a configured preference for headed still wins.
    async with attached_browser(headed=True if pause else None) as context:
        # A gate URL is accepted directly so the gate can be exercised without loading a
        # SoundCloud page first — which matters when SoundCloud is rate-limiting this browser.
        if "soundcloud.com" in url:
            # Before the gate, not during it. A gate that checks SoundCloud (droploud reads
            # the repost back) then finds the work already done and only has to verify,
            # which keeps the gate loop a pure click-driver with no second browser context
            # to coordinate.
            if sc_actions:
                await do_soundcloud_actions(
                    context, url, comment_text=DOWNLOAD_COMMENT, into=actions
                )
            gate_url = await get_gate_url(context, url)
        else:
            if sc_actions:
                logger.warning(
                    "--sc-actions needs a SoundCloud track URL to know what to act on; "
                    "skipping the actions for this bare gate URL"
                )
            logger.info("Treating URL as a gate page directly (no SoundCloud lookup)")
            gate_url = url

        recorder = RunRecorder(gate_name_for(gate_url))

        page = await context.new_page()
        await page.goto(gate_url, wait_until="domcontentloaded", timeout=30_000)
        logger.info("Gate page open: %s", page.url)

        handler = JudgmentGateHandler(
            # Otherwise every line of a droploud run is logged as [hypeddit_jev], which is
            # the default baked into the handler for the gate it was first written against.
            config={"gate": gate_name_for(gate_url), "steps": []},
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
            recorder=recorder,
            on_requirements=requirement_follower(actions) if sc_actions else None,
        )
        _apply_oauth_policy(handler, gate_url)

        # Released in the finally, so a run that ends without a file still gives back what
        # it spent. A gate that charges follows and then never unlocks is how the account
        # walks into SoundCloud's 2000-following cap, and it is the gate that decides
        # whether that happens. The two states below are the deliberate exceptions.
        resuming = False
        try:
            try:
                results = await handler.run(page)
            except CaptchaEncountered as e:
                # Keep the follows: the tab stays open for a person to finish by hand, and
                # the gate is still checking for them.
                resuming = True
                logger.warning("CAPTCHA | %s — tab left open, manual followup needed", e.kind)
                recorder.finish(url=url, gate_url=gate_url, downloaded=False, terminal="captcha")
                return
            except LoginWallEncountered as e:
                resuming = True
                logger.warning("LOGIN_REQUIRED | %s — tab left open, then re-run", e.reason)
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
        finally:
            await _settle_follows(actions, resuming=resuming)

        await page.close()
