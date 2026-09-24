"""--dedupe-comments: sweep every track ever processed for extra copies of the bot's comment.

Catches what the per-track clean-up in main.py/jev_pilot.py cannot reach: a track left in
captcha_pending/login_required, a --jev run against a bare gate URL, or a duplicate from
before this existed. Runs headless regardless of TUNEWRANGLER_SC_HEADED — no person is
needed for a resolve/read/delete sweep, and headed only opens a window nobody watches.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from soundcloud_dl.comment_guard import CommentCleanup, keep_one_comment
from soundcloud_dl.playwright_browser import attached_browser
from soundcloud_dl.resume import all_track_urls

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

logger = logging.getLogger("soundcloud_dl.dedupe_comments")

_MAX_RETRIES = 3
_BACKOFF_SECONDS = 30

# Rate-limited (429) after ~100 calls on 2026-09-23, and an in-page fetch throws this
# TypeError when Chrome drops the connection mid-request — both are worth a retry. Matched
# on "returned 429" rather than a bare "429", which a track slug could contain.
_TRANSIENT_MARKERS = ("returned 429", "Failed to fetch")
# The browser tab (or Chrome itself) is gone; retrying only burns the backoff budget.
_STOP_MARKER = "Target closed"


class DedupeStoppedError(RuntimeError):
    """Raised to end the sweep early because the browser connection is gone."""


async def _clean_with_backoff(context: BrowserContext, url: str, *, apply: bool) -> CommentCleanup:
    result = CommentCleanup(ok=False, detail="never attempted")
    for attempt in range(_MAX_RETRIES):
        result = await keep_one_comment(context, url, apply=apply)
        if result.ok:
            return result
        if _STOP_MARKER in result.detail:
            msg = f"{url}: {result.detail}"
            raise DedupeStoppedError(msg)
        if not any(marker in result.detail for marker in _TRANSIENT_MARKERS):
            return result
        wait = _BACKOFF_SECONDS * (attempt + 1)
        logger.warning("Transient failure on %s (%s) — backing off %ds", url, result.detail, wait)
        await asyncio.sleep(wait)
    return result


async def dedupe_all(*, apply: bool) -> None:
    """Sweep every track URL ever recorded, deleting extra copies of the bot's comment.

    Dry run unless apply=True: lists what would be deleted and keeps nothing.
    """
    urls = all_track_urls()
    logger.info(
        "Checking %d track(s) for duplicate comments%s", len(urls), "" if apply else " (dry run)"
    )
    flagged = 0
    async with attached_browser(headed=False) as context:
        for i, url in enumerate(urls, 1):
            try:
                result = await _clean_with_backoff(context, url, apply=apply)
            except DedupeStoppedError:
                logger.exception("Stopping the sweep")
                break
            if result.deleted or "would delete" in result.detail:
                flagged += 1
            logger.info("[%d/%d] %s: %s", i, len(urls), url, result.detail)
    logger.info(
        "Done. %d of %d track(s) had more than one bot comment%s.",
        flagged,
        len(urls),
        "" if apply else " (nothing deleted — dry run)",
    )
