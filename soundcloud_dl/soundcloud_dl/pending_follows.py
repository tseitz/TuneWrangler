"""Follows a run took and deliberately kept, so a later run can still give them back.

A captcha or a login wall leaves a tab open for a person to finish by hand, and the gate
is still checking for the follows — so releasing them there would break the very thing
the tab is open for. That makes holding them correct and forgetting them a leak: nothing
ever collects, and a re-run cannot re-derive them because `set_following` reports
`changed=False` for a follow already in place, which is exactly what the release step
uses to tell a run's own follows from the user's.

So the ids are written down when they are held, and swept at the start of the next run.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from soundcloud_dl.config import get_pending_follows_file

if TYPE_CHECKING:
    from soundcloud_dl.soundcloud_actions import ActionResult

logger = logging.getLogger("soundcloud_dl.pending_follows")


def _load() -> list[int]:
    path = get_pending_follows_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read %s — starting a fresh ledger", path, exc_info=True)
        return []
    return [int(x) for x in data] if isinstance(data, list) else []


def _save(user_ids: list[int]) -> None:
    path = get_pending_follows_file()
    try:
        path.write_text(json.dumps(sorted(set(user_ids)), indent=2), encoding="utf-8")
    except OSError:
        logger.warning("Could not write %s — these follows are unrecorded", path, exc_info=True)


def hold(actions: dict[str, ActionResult]) -> None:
    """Record follows this run took but is keeping, so the next run can release them."""
    from soundcloud_dl.sc_actions_flow import follows_to_release  # noqa: PLC0415

    user_ids = follows_to_release(actions)
    if not user_ids:
        return
    _save([*_load(), *user_ids])
    logger.warning(
        "Keeping %d follow(s) for the open tab: %s — recorded in %s and released on a later run",
        len(user_ids),
        ", ".join(str(i) for i in user_ids),
        get_pending_follows_file(),
    )


async def sweep() -> None:
    """Give back everything an earlier run held. Never fatal — this is tidy-up."""
    user_ids = _load()
    if not user_ids:
        return
    from soundcloud_dl.soundcloud_actions import release_follows  # noqa: PLC0415

    logger.info("Releasing %d follow(s) held by an earlier run", len(user_ids))
    try:
        results = await release_follows(user_ids)
    except Exception:
        logger.exception("Could not release held follows — the ledger is kept for next time")
        return
    # Only the ones that actually came back are cleared. A failure that dropped them here
    # would be the same silent leak the ledger exists to close.
    released = {r.subject_id for r in results if r.ok and r.subject_id is not None}
    for result in results:
        log = logger.info if result.ok else logger.warning
        log("%s unfollow — %s", "OK  " if result.ok else "FAIL", result.detail)
    _save([i for i in user_ids if i not in released])
