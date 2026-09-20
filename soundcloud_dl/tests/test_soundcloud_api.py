"""Tests for the API-driven SoundCloud actions.

The endpoint shapes asserted here were established by probing the live API, not read from
docs. They are pinned because they are unobvious and a plausible-looking "tidy-up" of any
of them silently stops the action landing.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from soundcloud_dl import soundcloud_api as api
from soundcloud_dl.soundcloud_api import AccountMismatch, ApiError


class FakePage:
    """Stands in for a Playwright page, recording the api-v2 calls made through it."""

    def __init__(self, replies: list[dict[str, Any]] | None = None, url: str = "") -> None:
        self.calls: list[tuple[str, str]] = []
        self.replies = replies or []
        self.url = url
        self.goto_urls: list[str] = []

    async def evaluate(self, _js: str, args: list[str]) -> dict[str, Any]:
        method, path = args
        self.calls.append((method, path))
        return self.replies.pop(0) if self.replies else {"status": 200, "body": "{}"}

    async def goto(self, url: str, **_kw: object) -> None:
        self.goto_urls.append(url)
        self.url = url


def client_for(handler: Any) -> httpx.AsyncClient:  # noqa: ANN401
    """An httpx client whose requests are answered by `handler` instead of the network."""
    return httpx.AsyncClient(
        base_url="https://api.soundcloud.com", transport=httpx.MockTransport(handler)
    )


# ── api.soundcloud.com ─────────────────────────────────────────────────────────


async def test_resolve_raises_rather_than_returning_a_half_answer() -> None:
    async with client_for(lambda _r: httpx.Response(404, text="nope")) as c:
        with pytest.raises(ApiError, match="resolve"):
            await api.resolve(c, "https://soundcloud.com/a/b")


async def test_follow_reports_failure_when_the_state_does_not_change() -> None:
    # The write can answer 200 and still not stick, so the status is never the proof.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, json={})
        return httpx.Response(404, json={})

    async with client_for(handler) as c:
        ok, _ = await api.set_following(c, 42, on=True)
    assert ok is False


async def test_a_failed_follow_carries_soundclouds_own_reason() -> None:
    # Hitting the 2000-following cap arrives as a bare 422; only the body says so, and
    # without it the failure reads as a bug in here rather than a full account.
    reason = "You have reached the maximum number of users you can follow."

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(422, json={"code": 422, "message": reason})
        return httpx.Response(404, json={})

    async with client_for(handler) as c:
        ok, detail = await api.set_following(c, 42, on=True)
    assert ok is False
    assert "maximum number of users" in detail


async def test_follow_reports_success_only_after_reading_the_state_back() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={})

    async with client_for(handler) as c:
        ok, _ = await api.set_following(c, 42, on=True)
    assert ok is True
    assert seen == ["PUT /me/followings/42", "GET /me/followings/42"]


async def test_unfollow_asks_for_a_delete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404 if request.method == "GET" else 200, json={})

    async with client_for(handler) as c:
        ok, detail = await api.set_following(c, 42, on=False)
    assert ok is True
    assert "not following" in detail


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ([{"id": 7}, {"id": 8}], True),
        ([{"id": 8}], False),
        ({"collection": [{"id": 7}]}, True),
        ({"collection": []}, False),
    ],
)
async def test_recent_collection_reads_both_shapes(payload: Any, expected: bool) -> None:  # noqa: ANN401
    # /me/likes/tracks answers with a bare list, /me/followings with a collection object.
    async with client_for(lambda _r: httpx.Response(200, json=payload)) as c:
        assert await api.is_liked(c, 7) is expected


async def test_like_and_repost_are_read_back_from_different_paths() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=[])

    async with client_for(handler) as c:
        await api.is_liked(c, 7)
        await api.is_reposted(c, 7)
    assert seen == ["/me/likes/tracks", "/me/reposts/tracks"]


async def test_comment_is_sent_in_the_nested_shape_the_api_demands() -> None:
    # A flat {"comment": "text"} is answered "Body can't be blank" and posts nothing.
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        sent.update(_json.loads(request.content))
        return httpx.Response(201, json={"id": 99})

    async with client_for(handler) as c:
        ok, detail = await api.post_comment(c, 7, "nice one")
    assert ok is True
    assert sent == {"comment": {"body": "nice one"}}
    assert "99" in detail


async def test_comment_without_an_id_is_not_treated_as_posted() -> None:
    async with client_for(lambda _r: httpx.Response(201, json={})) as c:
        ok, detail = await api.post_comment(c, 7, "x")
    assert ok is False
    assert "no id" in detail


# ── api-v2 through the page ────────────────────────────────────────────────────


async def test_like_is_addressed_per_user() -> None:
    page = FakePage([{"status": 200, "body": ""}])
    ok, _ = await api.set_like(page, 46056733, 2304544685, on=True)
    assert ok is True
    assert page.calls == [("PUT", "/users/46056733/track_likes/2304544685")]


async def test_repost_is_addressed_as_me_not_per_user() -> None:
    # The per-user spelling that works for likes answers 404 for reposts.
    page = FakePage([{"status": 204, "body": ""}])
    ok, _ = await api.set_repost(page, 2304544685, on=True)
    assert ok is True
    assert page.calls == [("PUT", "/me/track_reposts/2304544685")]


async def test_undo_sends_a_delete() -> None:
    page = FakePage([{"status": 200, "body": ""}, {"status": 200, "body": ""}])
    await api.set_like(page, 1, 2, on=False)
    await api.set_repost(page, 2, on=False)
    assert [m for m, _ in page.calls] == ["DELETE", "DELETE"]


async def test_a_delete_for_something_never_set_is_success() -> None:
    page = FakePage([{"status": 404, "body": ""}])
    ok, detail = await api.set_repost(page, 7, on=False)
    assert ok is True
    assert "was not set" in detail


async def test_a_404_on_a_write_is_still_a_failure() -> None:
    page = FakePage([{"status": 404, "body": ""}])
    ok, _ = await api.set_repost(page, 7, on=True)
    assert ok is False


async def test_a_signed_out_browser_is_reported_not_silently_skipped() -> None:
    page = FakePage([{"status": 0, "body": "no oauth_token cookie - the browser is signed out"}])
    ok, detail = await api.set_repost(page, 7, on=True)
    assert ok is False
    assert "signed out" in detail


# ── The account guard ──────────────────────────────────────────────────────────


async def test_matching_accounts_pass_and_return_the_id() -> None:
    page = FakePage([{"status": 200, "body": '{"id": 46056733}'}])
    assert await api.assert_same_account(page, 46056733) == 46056733


async def test_a_split_account_stops_the_run() -> None:
    # The failure this guard exists for: follows landing on one account while likes and
    # reposts land on another, with every gate seeing half its requirements met.
    page = FakePage([{"status": 200, "body": '{"id": 46056733}'}])
    with pytest.raises(AccountMismatch, match="--sc-auth"):
        await api.assert_same_account(page, 231605428)


async def test_a_long_identity_reply_still_parses() -> None:
    # The real /me is several kB. Truncating the reply in the page helper to keep error
    # messages short cut the JSON in half, and the guard could never read an id again.
    import json as _json

    big = _json.dumps({"id": 46056733, "bio": "x" * 5000, "city": "Laniakea"})
    page = FakePage([{"status": 200, "body": big}])
    assert await api.browser_user_id(page) == 46056733


async def test_an_unreadable_identity_is_an_error_not_a_guess() -> None:
    page = FakePage([{"status": 200, "body": "not json"}])
    with pytest.raises(ApiError, match="no usable id"):
        await api.assert_same_account(page, 1)


# ── Page origin ────────────────────────────────────────────────────────────────


async def test_an_off_site_page_is_navigated_before_any_api_v2_call() -> None:
    page = FakePage(url="https://droploud.com/gate/abc")
    await api.ensure_on_soundcloud(page)
    assert page.goto_urls == ["https://soundcloud.com/discover"]


async def test_a_page_already_on_soundcloud_is_left_alone() -> None:
    page = FakePage(url="https://soundcloud.com/indacollective/pressure")
    await api.ensure_on_soundcloud(page)
    assert page.goto_urls == []
