"""Delete extra copies of the bot's own comment on a track, keeping exactly one.

Every rerun of a gate that posts its own comment (hypeddit, pl8list, droploud) submits its
comment box again, and a rerun of _comment_once can miss an existing one that the public
API has not caught up on yet — a sweep of the live account found 27 of 475 processed
tracks carrying 2-3 duplicate copies from exactly this. This cleans that up after a gate
attempt, using only the browser's session: a gate can post through the page alone, before
--sc-auth has ever been run, so this must not need a stored user token.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from soundcloud_dl.config import DOWNLOAD_COMMENT
from soundcloud_dl.gate_handlers.captcha import detect_captcha
from soundcloud_dl.playwright_browser import new_page
from soundcloud_dl.soundcloud_actions import block_ads
from soundcloud_dl.soundcloud_api import (
    ApiError,
    MyComment,
    browser_user_id,
    delete_comment_v2,
    ensure_on_soundcloud,
    invalidate_client_id,
    my_comments_v2,
    resolve_v2,
    web_client_id,
)

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

logger = logging.getLogger("soundcloud_dl.comment_guard")

# Between deletes on the same track, so they don't land as a burst.
_DELETE_SPACING_SECONDS = 1.0


@dataclass(frozen=True)
class CommentCleanup:
    """What the clean-up did, so a caller can log it. Never raised — see keep_one_comment."""

    ok: bool
    detail: str
    deleted: tuple[int, ...] = ()


def _normalized(text: str) -> str:
    """NFKC-normalise and drop the emoji variation selector, so 🔥️ matches 🔥."""
    return unicodedata.normalize("NFKC", text).replace("\ufe0f", "").strip()


def _is_auth_status(exc: ApiError) -> bool:
    return "returned 401" in str(exc) or "returned 403" in str(exc)


@dataclass(frozen=True)
class _Session:
    """The page and identifiers every read/delete call needs for one track."""

    page: Page
    track_id: int
    client_id: str
    user_id: int


async def _my_comments_with_retry(session: _Session) -> list[MyComment]:
    """Read comments, refreshing a stale client_id once on a 401/403 before giving up.

    A 403 from api-v2 is often bot protection rather than an unreadable list (see
    soundcloud_api.py's module docstring), but a stale client_id answers the same way —
    collecting it again is what tells the two apart without a second, permanent retry loop.
    """
    try:
        return await my_comments_v2(
            session.page, session.track_id, session.user_id, session.client_id
        )
    except ApiError as e:
        if not _is_auth_status(e):
            raise
        logger.warning("api-v2 comments read failed (%s) — refreshing client_id once", e)
        invalidate_client_id()
        client_id = await web_client_id(session.page)
        return await my_comments_v2(session.page, session.track_id, session.user_id, client_id)


async def _select_track(page: Page, track_url: str) -> tuple[int, str] | CommentCleanup:
    """The track id and client_id to work with, or the CommentCleanup to return instead.

    Always navigates first: web_client_id() only navigates on a cache miss, and every
    call here is on a fresh page that starts on about:blank — without this, a cache hit
    leaves the page there and every api-v2 call on it reads as signed out.
    """
    await ensure_on_soundcloud(page)
    client_id = await web_client_id(page)
    if (kind := await detect_captcha(page)) is not None:
        logger.warning("Comment clean-up for %s skipped: %s on the page", track_url, kind)
        return CommentCleanup(ok=False, detail=f"skipped: {kind}")
    resource = await resolve_v2(page, track_url, client_id)
    if resource.get("kind") != "track":
        detail = f"{track_url} resolved to {resource.get('kind')!r}, not a track"
        logger.warning("Comment clean-up: %s", detail)
        return CommentCleanup(ok=False, detail=detail)
    return int(resource["id"]), client_id


def _bot_candidates(comments: list[MyComment], track_id: int, target: str) -> list[MyComment]:
    """Every comment matching the bot's text, lowest id first — the one to keep."""
    candidates = sorted((c for c in comments if _normalized(c.body) == target), key=lambda c: c.id)
    if not candidates and len(comments) > 1:
        logger.warning(
            "Track %d: %d comments by this account but none match the current "
            "TUNEWRANGLER_SC_COMMENT — a mismatch could hide duplicates",
            track_id,
            len(comments),
        )
    return candidates


async def _delete_extras(session: _Session, candidates: list[MyComment]) -> CommentCleanup:
    """Delete every candidate but the lowest id, spaced out, then confirm only it is left."""
    keep, extra = candidates[0], candidates[1:]
    deleted: list[int] = []
    for i, comment in enumerate(extra):
        if i:
            await asyncio.sleep(_DELETE_SPACING_SECONDS)
        ok, detail = await delete_comment_v2(session.page, comment.id)
        if ok:
            deleted.append(comment.id)
            logger.info("Deleted duplicate comment %d on track %d", comment.id, session.track_id)
        else:
            logger.warning(
                "Could not delete comment %d on track %d: %s",
                comment.id,
                session.track_id,
                detail,
            )

    target = _normalized(DOWNLOAD_COMMENT)
    remaining = await _my_comments_with_retry(session)
    left = [c for c in remaining if _normalized(c.body) == target]
    confirmed = len(left) == 1 and left[0].id == keep.id
    if not confirmed:
        logger.warning(
            "Track %d: expected only comment %d left, found %s",
            session.track_id,
            keep.id,
            [c.id for c in left],
        )
    ok = confirmed and len(deleted) == len(extra)
    detail = f"kept {keep.id}, deleted {deleted}"
    return CommentCleanup(ok=ok, detail=detail, deleted=tuple(deleted))


async def keep_one_comment(
    context: BrowserContext, track_url: str, *, apply: bool
) -> CommentCleanup:
    """Delete every extra copy of the bot's comment on this track, keeping the lowest id.

    Never raises: a failed clean-up must not change the track's recorded outcome. Only a
    comment whose text matches the current TUNEWRANGLER_SC_COMMENT is ever touched —
    anything else this account wrote, including a hand-typed one, is left alone.

    apply=False (--dedupe-comments' default) reports what would be deleted without
    deleting anything — the caller decides whether to log or print `detail`.
    """
    page = await new_page(context)
    try:
        await block_ads(page)
        selected = await _select_track(page, track_url)
        if isinstance(selected, CommentCleanup):
            return selected
        track_id, client_id = selected

        session = _Session(page, track_id, client_id, await browser_user_id(page))
        comments = await _my_comments_with_retry(session)
        target = _normalized(DOWNLOAD_COMMENT)
        candidates = _bot_candidates(comments, track_id, target)
        if len(candidates) <= 1:
            detail = f"{len(candidates)} bot comment(s), nothing to do"
            return CommentCleanup(ok=True, detail=detail)

        if not apply:
            keep, extra = candidates[0], candidates[1:]
            ids = [c.id for c in extra]
            return CommentCleanup(ok=True, detail=f"would delete {ids}, keep {keep.id}")

        return await _delete_extras(session, candidates)
    except ApiError as e:
        logger.warning("Comment clean-up could not read/delete for %s: %s", track_url, e)
        return CommentCleanup(ok=False, detail=str(e))
    except Exception as e:
        # Never raised into the caller: a bug in here must not change the track's own
        # recorded outcome, which is what the caller (main.py/_process_track) writes.
        logger.exception("Comment clean-up crashed for %s", track_url)
        return CommentCleanup(ok=False, detail=f"{type(e).__name__}: {e}")
    finally:
        await page.close()
