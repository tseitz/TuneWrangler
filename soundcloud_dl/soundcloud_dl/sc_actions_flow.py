"""Doing the SoundCloud side of a gate's demands, and giving back what it cost.

A gate asks for a follow/like/repost/comment and then checks. Some check their own DOM,
some ask SoundCloud — droploud reads the repost back — so the actions are performed for
real, before the gate opens, and the gate is left to verify work already done.

The follows are the part that has to be accounted for. A gate that charges follows and
then never unlocks is how an account walks into SoundCloud's 2000-following cap, so every
follow a run takes is handed back once the run is over. Shared by the --jev pilot and the
playlist path so there is one copy of that accounting rather than two.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from playwright.async_api import BrowserContext

    from soundcloud_dl.soundcloud_actions import ActionResult

logger = logging.getLogger("soundcloud_dl.sc_actions_flow")


async def do_soundcloud_actions(
    context: BrowserContext,
    track_url: str,
    *,
    comment_text: str,
    into: dict[str, ActionResult] | None = None,
) -> dict[str, ActionResult]:
    """Follow/like/repost/comment for real, and say plainly which ones landed.

    Never fatal. A gate can still be satisfiable when one action fails — droploud asks for
    a repost but not a like — so a failure here is reported and the gate run continues.

    Whatever landed before a failure is kept, never discarded. The follow is taken first
    and the three actions after it can each raise, so returning an empty dict on the way
    out would drop the record of a follow that is really on the account — and the release
    step reads exactly that record to know what to give back.
    """
    from soundcloud_dl.soundcloud_actions import perform  # noqa: PLC0415

    results: dict[str, ActionResult] = {} if into is None else into
    logger.info("SoundCloud actions first: %s", track_url)
    try:
        await perform(context, track_url, comment_text=comment_text, into=results)
    except CaptchaEncountered as e:
        logger.warning("SoundCloud actions blocked by %s — continuing to the gate", e.kind)
    except Exception:
        logger.exception("SoundCloud actions failed — continuing to the gate")
    landed = [name for name, r in results.items() if r.ok]
    missed = [f"{name} ({r.detail})" for name, r in results.items() if not r.ok]
    logger.info("SoundCloud actions landed: %s", ", ".join(landed) or "none")
    if missed:
        logger.warning("SoundCloud actions missed: %s", "; ".join(missed))
    return results


def follows_to_release(actions: dict[str, ActionResult]) -> list[int]:
    """The users this run started following, so only those get handed back.

    A follow the user already had is theirs, and a gate names several profiles, so the
    subject id is the only thing that says who this run is responsible for.
    """
    return [
        r.subject_id
        for r in actions.values()
        if r.action.startswith("follow") and r.changed and r.subject_id is not None
    ]


async def release_follows_taken(actions: dict[str, ActionResult]) -> None:
    """Hand back the follows this run took, once the file is actually in hand.

    Never fatal: the download has already succeeded by this point, and failing to tidy up
    must not undo that.
    """
    user_ids = follows_to_release(actions)
    if not user_ids:
        return
    from soundcloud_dl.soundcloud_actions import release_follows  # noqa: PLC0415

    try:
        results = await release_follows(user_ids)
    except Exception:
        logger.exception("Could not give the follows back — they stay on the account")
        return
    for result in results:
        log = logger.info if result.ok else logger.warning
        log("%s unfollow — %s", "OK  " if result.ok else "FAIL", result.detail)


def requirement_follower(
    actions: dict[str, ActionResult],
) -> Callable[[list[str]], Awaitable[None]]:
    """Follow the profiles a gate names, the moment it names them.

    Results land in `actions` so the release step afterwards covers these follows too.
    """

    async def on_requirements(blocks: list[str]) -> None:
        from soundcloud_dl.gate_handlers.gate_requirements import (  # noqa: PLC0415
            soundcloud_handles,
        )
        from soundcloud_dl.soundcloud_actions import (  # noqa: PLC0415
            MAX_GATE_FOLLOWS,
            follow_handles,
        )

        handles = [h for h in soundcloud_handles(blocks) if f"follow:{h}" not in actions]
        if not handles:
            return
        # MAX_GATE_FOLLOWS caps one call, and a gate is asked for its requirements once per
        # batch of fresh blocks — so a per-call cap lets one page spend that many times over
        # by naming a few more profiles each turn. The budget is for the whole run.
        spent = sum(1 for k in actions if k.startswith("follow:"))
        room = MAX_GATE_FOLLOWS - spent
        if room <= 0:
            logger.warning(
                "gate named more profiles (%s) but this run has already followed %d — "
                "refusing the rest",
                ", ".join("@" + h for h in handles),
                spent,
            )
            return
        handles = handles[:room]
        logger.info("Gate named SoundCloud profiles: %s", ", ".join("@" + h for h in handles))
        actions.update(await follow_handles(handles))

    return on_requirements
