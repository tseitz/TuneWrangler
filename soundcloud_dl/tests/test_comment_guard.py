"""Tests for keep_one_comment: what gets deleted, and what never does.

Every collaborator keep_one_comment drives through the page is faked at the module
boundary — the page itself is never simulated — because what matters here is the
selection and matching logic, not Playwright's evaluate/on/goto plumbing (that lives in
test_soundcloud_api.py against the real soundcloud_api functions).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl import comment_guard
from soundcloud_dl.gate_handlers.captcha import CaptchaKind
from soundcloud_dl.soundcloud_api import ApiError, MyComment

TRACK_URL = "https://soundcloud.com/a/b"
USER_ID = 46056733


def _context() -> MagicMock:
    page = MagicMock()
    page.close = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    return context


def _comment(comment_id: int, body: str = "🔥🔥🔥") -> MyComment:
    return MyComment(id=comment_id, created_at="", body=body)


@pytest.fixture(autouse=True)
def _patch_collaborators(monkeypatch):
    """Fake every call keep_one_comment makes through the page or config."""
    monkeypatch.setattr(comment_guard, "DOWNLOAD_COMMENT", "🔥🔥🔥")
    monkeypatch.setattr(comment_guard, "block_ads", AsyncMock())
    monkeypatch.setattr(comment_guard, "ensure_on_soundcloud", AsyncMock())
    monkeypatch.setattr(comment_guard, "web_client_id", AsyncMock(return_value="cid"))
    monkeypatch.setattr(comment_guard, "browser_user_id", AsyncMock(return_value=USER_ID))
    monkeypatch.setattr(
        comment_guard, "resolve_v2", AsyncMock(return_value={"kind": "track", "id": 7})
    )
    monkeypatch.setattr(comment_guard, "detect_captcha", AsyncMock(return_value=None))
    monkeypatch.setattr(comment_guard.asyncio, "sleep", AsyncMock())


async def test_three_bot_comments_keeps_the_lowest_id_deletes_the_rest(monkeypatch):
    comments = [_comment(30), _comment(10), _comment(20)]
    monkeypatch.setattr(
        comment_guard, "my_comments_v2", AsyncMock(side_effect=[comments, [_comment(10)]])
    )
    deleted: list[int] = []

    async def _delete(_page, comment_id):
        deleted.append(comment_id)
        return True, "api-v2 204"

    monkeypatch.setattr(comment_guard, "delete_comment_v2", _delete)

    result = await comment_guard.keep_one_comment(_context(), TRACK_URL, apply=True)
    assert result.ok is True
    assert sorted(deleted) == [20, 30]
    assert set(result.deleted) == {20, 30}


async def test_a_hand_written_comment_by_the_same_account_is_never_a_candidate(monkeypatch):
    comments = [_comment(1, "🔥🔥🔥"), _comment(2, "great track!")]
    monkeypatch.setattr(comment_guard, "my_comments_v2", AsyncMock(return_value=comments))
    delete = AsyncMock()
    monkeypatch.setattr(comment_guard, "delete_comment_v2", delete)

    result = await comment_guard.keep_one_comment(_context(), TRACK_URL, apply=True)
    assert result.ok is True
    delete.assert_not_called()


async def test_a_failed_read_deletes_nothing(monkeypatch):
    monkeypatch.setattr(comment_guard, "my_comments_v2", AsyncMock(side_effect=ApiError("500")))
    delete = AsyncMock()
    monkeypatch.setattr(comment_guard, "delete_comment_v2", delete)

    result = await comment_guard.keep_one_comment(_context(), TRACK_URL, apply=True)
    assert result.ok is False
    delete.assert_not_called()


async def test_a_delete_that_still_reads_back_warns_but_does_not_raise(monkeypatch):
    comments = [_comment(10), _comment(20)]
    # The re-read after deleting still shows both — the delete did not stick.
    monkeypatch.setattr(
        comment_guard, "my_comments_v2", AsyncMock(side_effect=[comments, comments])
    )
    monkeypatch.setattr(
        comment_guard, "delete_comment_v2", AsyncMock(return_value=(True, "api-v2 204"))
    )

    result = await comment_guard.keep_one_comment(_context(), TRACK_URL, apply=True)
    # Never raised, but not reported as clean either — the caller needs to know a
    # duplicate may still be sitting on the track.
    assert result.ok is False
    assert result.deleted == (20,)


async def test_apply_false_lists_without_deleting(monkeypatch):
    comments = [_comment(10), _comment(20)]
    monkeypatch.setattr(comment_guard, "my_comments_v2", AsyncMock(return_value=comments))
    delete = AsyncMock()
    monkeypatch.setattr(comment_guard, "delete_comment_v2", delete)

    result = await comment_guard.keep_one_comment(_context(), TRACK_URL, apply=False)
    assert "would delete" in result.detail
    assert result.deleted == ()
    delete.assert_not_called()


async def test_a_captcha_on_the_cleanup_page_skips_rather_than_deleting(monkeypatch):
    monkeypatch.setattr(
        comment_guard, "detect_captcha", AsyncMock(return_value=CaptchaKind.DATADOME)
    )
    delete = AsyncMock()
    monkeypatch.setattr(comment_guard, "delete_comment_v2", delete)
    monkeypatch.setattr(comment_guard, "my_comments_v2", AsyncMock())

    result = await comment_guard.keep_one_comment(_context(), TRACK_URL, apply=True)
    assert result.ok is False
    assert "datadome" in result.detail.lower()
    delete.assert_not_called()


async def test_a_crash_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(
        comment_guard, "browser_user_id", AsyncMock(side_effect=RuntimeError("boom"))
    )
    result = await comment_guard.keep_one_comment(_context(), TRACK_URL, apply=True)
    assert result.ok is False


async def test_a_cached_client_id_still_navigates_the_fresh_page(monkeypatch):
    """web_client_id only navigates on a cache miss (see soundcloud_api.py); every call
    here is on a brand-new page starting on about:blank, so _select_track has to force
    the navigation itself rather than leaving it to web_client_id's cache state.
    """
    ensure = AsyncMock()
    monkeypatch.setattr(comment_guard, "ensure_on_soundcloud", ensure)
    monkeypatch.setattr(comment_guard, "my_comments_v2", AsyncMock(return_value=[]))

    await comment_guard.keep_one_comment(_context(), TRACK_URL, apply=True)
    ensure.assert_awaited_once()


async def test_the_page_is_always_closed(monkeypatch):
    monkeypatch.setattr(comment_guard, "my_comments_v2", AsyncMock(side_effect=ApiError("500")))
    context = _context()
    await comment_guard.keep_one_comment(context, TRACK_URL, apply=True)
    context.new_page.return_value.close.assert_awaited_once()
