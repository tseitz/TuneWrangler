"""Tests for the URL helpers and the gate-named follows behind the SoundCloud action flow."""

from __future__ import annotations

import contextlib
from typing import Any

import httpx
import pytest

from soundcloud_dl import soundcloud_actions
from soundcloud_dl.sc_actions_flow import follows_to_release
from soundcloud_dl.soundcloud_actions import (
    ActionResult,
    artist_url_for,
    follow_handles,
    release_follows,
    track_path_for,
)
from soundcloud_dl.soundcloud_api import MyComment

TRACK = "https://soundcloud.com/urboin8/mph-raw-urboin8-bootleg"


@pytest.mark.parametrize(
    "url",
    [
        TRACK,
        TRACK + "?in=danedubz/sets/fire16/",
        TRACK + "?si=abc&utm_source=clipboard",
    ],
)
def test_artist_url_drops_the_track_and_any_query(url):
    assert artist_url_for(url) == "https://soundcloud.com/urboin8"


@pytest.mark.parametrize(
    "url",
    [TRACK, TRACK + "?in=danedubz/sets/fire16/"],
)
def test_track_path_matches_soundclouds_own_link_href(url):
    assert track_path_for(url) == "/urboin8/mph-raw-urboin8-bootleg"


def test_track_path_ignores_a_secret_share_segment():
    """A private-share URL has a third segment; the listing link still uses two."""
    assert track_path_for(TRACK + "/s-nTyZQLX9ZXF") == "/urboin8/mph-raw-urboin8-bootleg"


# ── Following the profiles a gate names ────────────────────────────────────────

USERS = {"indacollective": 1430205171, "ets_wav": 165621040}


def _fake_api(handler: Any, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Point api_client at a MockTransport, and return the request log it fills."""
    seen: list[str] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        return handler(request)

    @contextlib.asynccontextmanager
    async def fake_client():
        async with httpx.AsyncClient(
            base_url="https://api.soundcloud.com", transport=httpx.MockTransport(wrapped)
        ) as client:
            yield client

    monkeypatch.setattr(soundcloud_actions, "api_client", fake_client)
    return seen


def _resolving_handler(following: set[int]) -> Any:
    """Resolves the known handles and keeps a real following set, so reads back honestly."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/resolve":
            handle = str(request.url.params["url"]).rsplit("/", maxsplit=1)[-1]
            if handle not in USERS:
                return httpx.Response(404, text="not found")
            return httpx.Response(
                200, json={"kind": "user", "id": USERS[handle], "permalink": handle}
            )
        user_id = int(path.rsplit("/", maxsplit=1)[-1])
        if request.method == "PUT":
            following.add(user_id)
        elif request.method == "DELETE":
            following.discard(user_id)
        return httpx.Response(200 if user_id in following else 404, json={})

    return handler


async def test_every_handle_a_gate_names_is_followed(monkeypatch):
    following: set[int] = set()
    _fake_api(_resolving_handler(following), monkeypatch)

    results = await follow_handles(["indacollective", "ets_wav"])

    assert all(r.ok for r in results.values())
    assert set(results) == {"follow:indacollective", "follow:ets_wav"}
    assert following == set(USERS.values())


async def test_a_follow_carries_the_id_so_it_can_be_given_back(monkeypatch):
    _fake_api(_resolving_handler(set()), monkeypatch)
    results = await follow_handles(["indacollective"])
    assert results["follow:indacollective"].subject_id == USERS["indacollective"]


async def test_a_handle_that_resolves_to_a_playlist_is_not_followed(monkeypatch):
    # soundcloud.com/<name> is not reserved to profiles. Following whatever comes back
    # would act on a real account and could not be taken back quietly.
    seen = _fake_api(
        lambda _r: httpx.Response(200, json={"kind": "playlist", "id": 99}), monkeypatch
    )
    results = await follow_handles(["somelist"])
    assert results["follow:somelist"].ok is False
    assert "not a user" in results["follow:somelist"].detail
    assert not [s for s in seen if s.startswith("PUT")]


async def test_one_unresolvable_handle_does_not_stop_the_rest(monkeypatch):
    following: set[int] = set()
    _fake_api(_resolving_handler(following), monkeypatch)

    results = await follow_handles(["nosuchuser", "ets_wav"])

    assert results["follow:nosuchuser"].ok is False
    assert results["follow:ets_wav"].ok is True
    assert following == {USERS["ets_wav"]}


async def test_a_page_naming_hundreds_of_profiles_spends_at_most_the_cap(monkeypatch):
    # The gate page is content we do not control, and each handle is a real follow on a
    # real stranger. Droploud asks for two; a hostile page can print any number.
    following: set[int] = set()
    _fake_api(_resolving_handler(following), monkeypatch)
    many = [f"user{i:03d}" for i in range(200)]

    results = await follow_handles(many)

    assert len(results) == soundcloud_actions.MAX_GATE_FOLLOWS


async def test_a_mid_loop_failure_keeps_the_record_of_what_already_landed(monkeypatch):
    """Without the ids of the follows that did land, nothing can give them back.

    They would stay on the account with no record that this run put them there.
    """
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls > 2:
            msg = "connection reset"
            raise httpx.ConnectError(msg)
        return _resolving_handler({USERS["indacollective"]})(request)

    _fake_api(handler, monkeypatch)

    results = await follow_handles(["indacollective", "ets_wav"])

    assert results["follow:indacollective"].subject_id == USERS["indacollective"]
    assert results["follow:ets_wav"].ok is False


async def test_a_renamed_permalink_resolving_to_someone_else_is_not_followed(monkeypatch):
    # /resolve follows redirects, so a reassigned handle answers as whoever holds it now.
    seen = _fake_api(
        lambda _r: httpx.Response(200, json={"kind": "user", "id": 5, "permalink": "someoneelse"}),
        monkeypatch,
    )
    results = await follow_handles(["ets_wav"])
    assert results["follow:ets_wav"].ok is False
    assert "different profile" in results["follow:ets_wav"].detail
    assert not [s for s in seen if s.startswith("PUT")]


async def test_release_gives_back_exactly_the_ids_it_was_given(monkeypatch):
    following = set(USERS.values())
    _fake_api(_resolving_handler(following), monkeypatch)

    results = await release_follows([USERS["ets_wav"]])

    assert [r.ok for r in results] == [True]
    assert following == {USERS["indacollective"]}


# ── Which follows this run owns ────────────────────────────────────────────────


def test_only_follows_this_run_added_are_given_back():
    # A follow the user already had is theirs. changed=False is the whole guard.
    actions = {
        "follow": ActionResult("follow", ok=True, detail="", changed=True, subject_id=1),
        "follow:a": ActionResult("follow:a", ok=True, detail="", changed=False, subject_id=2),
        "follow:b": ActionResult("follow:b", ok=True, detail="", changed=True, subject_id=3),
        "like": ActionResult("like", ok=True, detail="", changed=True),
    }
    assert follows_to_release(actions) == [1, 3]


def test_a_failed_follow_is_not_given_back():
    actions = {
        "follow:a": ActionResult("follow:a", ok=False, detail="422", changed=False, subject_id=2)
    }
    assert follows_to_release(actions) == []


# ── Not doing an action twice ──────────────────────────────────────────────────


async def _fake_client_id(*_a: object, **_k: object) -> str:
    return "abc123"


async def test_a_track_already_commented_on_is_not_commented_on_again(monkeypatch):
    posted: list[str] = []

    async def fake_existing(*_a: object, **_k: object) -> list[MyComment]:
        return [MyComment(id=2594494206, created_at="", body="🔥🔥🔥")]

    async def fake_post(*_a: object, **_k: object) -> tuple[bool, str]:
        posted.append("posted")
        raise AssertionError("post_comment must not be reached")

    monkeypatch.setattr(soundcloud_actions, "web_client_id", _fake_client_id)
    monkeypatch.setattr(soundcloud_actions, "my_comments_v2", fake_existing)
    monkeypatch.setattr(soundcloud_actions, "post_comment", fake_post)

    r = await soundcloud_actions._comment_once(None, None, 7, 46056733, "nice one")
    assert r.ok is True
    assert r.changed is False
    assert "already commented" in r.detail
    assert posted == []


async def test_a_track_not_yet_commented_on_gets_the_comment(monkeypatch):
    async def fake_existing(*_a: object, **_k: object) -> list[Any]:
        return []

    async def fake_post(*_a: object, **_k: object) -> tuple[bool, str]:
        return True, "comment 1 posted"

    monkeypatch.setattr(soundcloud_actions, "web_client_id", _fake_client_id)
    monkeypatch.setattr(soundcloud_actions, "my_comments_v2", fake_existing)
    monkeypatch.setattr(soundcloud_actions, "post_comment", fake_post)

    r = await soundcloud_actions._comment_once(None, None, 7, 46056733, "nice one")
    assert r.ok is True
    assert r.changed is True


async def test_comments_that_cannot_be_read_fail_rather_than_risk_a_duplicate(monkeypatch):
    async def fake_existing(*_a: object, **_k: object) -> list[Any]:
        raise soundcloud_actions.ApiError("500")

    async def fake_post(*_a: object, **_k: object) -> tuple[bool, str]:
        raise AssertionError("post_comment must not be reached")

    monkeypatch.setattr(soundcloud_actions, "web_client_id", _fake_client_id)
    monkeypatch.setattr(soundcloud_actions, "my_comments_v2", fake_existing)
    monkeypatch.setattr(soundcloud_actions, "post_comment", fake_post)

    r = await soundcloud_actions._comment_once(None, None, 7, 46056733, "nice one")
    assert r.ok is False
    assert r.changed is False


async def test_a_like_already_in_place_skips_the_write():
    writes: list[str] = []

    async def write() -> tuple[bool, str]:
        writes.append("w")
        return True, "wrote"

    async def read_back() -> bool:
        return True

    r = await soundcloud_actions._verified("like", write, read_back, want=True)
    assert r.ok is True
    assert r.changed is False
    assert writes == []


async def test_a_like_this_run_added_is_marked_changed():
    state = {"on": False}

    async def write() -> tuple[bool, str]:
        state["on"] = True
        return True, "wrote"

    async def read_back() -> bool:
        return state["on"]

    r = await soundcloud_actions._verified("like", write, read_back, want=True)
    assert r.ok is True
    assert r.changed is True
