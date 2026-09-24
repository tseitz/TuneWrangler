"""Tests for --dedupe-comments: no delete without --apply, and it stops rather than
retrying forever on a dead browser."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock

from soundcloud_dl import dedupe_comments
from soundcloud_dl.comment_guard import CommentCleanup


def _fake_attached_browser(context: object):
    @contextlib.asynccontextmanager
    async def _cm(**_kw: object):
        yield context

    return _cm


async def test_no_apply_issues_no_delete(monkeypatch):
    monkeypatch.setattr(dedupe_comments, "all_track_urls", lambda: ["https://soundcloud.com/a/b"])
    monkeypatch.setattr(dedupe_comments, "attached_browser", _fake_attached_browser(object()))
    calls: list[bool] = []

    async def _clean(_context, _url, *, apply):
        calls.append(apply)
        return CommentCleanup(ok=True, detail="would delete [2], keep 1")

    monkeypatch.setattr(dedupe_comments, "keep_one_comment", _clean)

    await dedupe_comments.dedupe_all(apply=False)
    assert calls == [False]


async def test_apply_is_threaded_through(monkeypatch):
    monkeypatch.setattr(dedupe_comments, "all_track_urls", lambda: ["https://soundcloud.com/a/b"])
    monkeypatch.setattr(dedupe_comments, "attached_browser", _fake_attached_browser(object()))
    calls: list[bool] = []

    async def _clean(_context, _url, *, apply):
        calls.append(apply)
        return CommentCleanup(ok=True, detail="kept 1, deleted [2]", deleted=(2,))

    monkeypatch.setattr(dedupe_comments, "keep_one_comment", _clean)

    await dedupe_comments.dedupe_all(apply=True)
    assert calls == [True]


async def test_a_dead_browser_stops_the_sweep_without_trying_every_url(monkeypatch):
    urls = ["https://soundcloud.com/a/b", "https://soundcloud.com/c/d"]
    monkeypatch.setattr(dedupe_comments, "all_track_urls", lambda: urls)
    monkeypatch.setattr(dedupe_comments, "attached_browser", _fake_attached_browser(object()))
    seen: list[str] = []

    async def _clean(_context, url, *, apply):  # noqa: ARG001
        seen.append(url)
        return CommentCleanup(ok=False, detail="PlaywrightError: Target closed")

    monkeypatch.setattr(dedupe_comments, "keep_one_comment", _clean)

    await dedupe_comments.dedupe_all(apply=False)
    assert seen == [urls[0]]


async def test_a_429_backs_off_then_retries(monkeypatch):
    monkeypatch.setattr(dedupe_comments, "all_track_urls", lambda: ["https://soundcloud.com/a/b"])
    monkeypatch.setattr(dedupe_comments, "attached_browser", _fake_attached_browser(object()))
    monkeypatch.setattr(dedupe_comments.asyncio, "sleep", AsyncMock())
    attempts: list[int] = []

    async def _clean(_context, _url, *, apply):  # noqa: ARG001
        attempts.append(len(attempts))
        if len(attempts) == 1:
            return CommentCleanup(ok=False, detail="api-v2 GET ... returned 429: rate limited")
        return CommentCleanup(ok=True, detail="1 bot comment(s), nothing to do")

    monkeypatch.setattr(dedupe_comments, "keep_one_comment", _clean)

    await dedupe_comments.dedupe_all(apply=False)
    assert len(attempts) == 2
