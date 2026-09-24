"""Tests for the user OAuth sign-in and token store."""

from __future__ import annotations

import base64
import hashlib
import json
import stat
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from soundcloud_dl import soundcloud_auth as auth
from soundcloud_dl.soundcloud_auth import SoundCloudAuthError


@pytest.fixture
def token_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the module's token store at a throwaway path."""
    path = tmp_path / "oauth_token.json"
    monkeypatch.setattr(auth, "get_token_file", lambda: path)
    return path


# ── PKCE ───────────────────────────────────────────────────────────────────────


def test_b64url_has_no_padding() -> None:
    assert "=" not in auth._b64url(b"\x00" * 10)


def test_pkce_challenge_is_the_sha256_of_the_verifier() -> None:
    verifier, challenge = auth._pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert challenge == expected.decode().rstrip("=")


def test_pkce_pair_is_different_every_time() -> None:
    assert auth._pkce_pair()[0] != auth._pkce_pair()[0]


# ── Token store ────────────────────────────────────────────────────────────────


def test_saved_token_file_is_owner_only(token_file: Path) -> None:
    auth._save_tokens({"access_token": "a", "refresh_token": "r", "expires_in": 3600})
    mode = stat.S_IMODE(token_file.stat().st_mode)
    assert mode == 0o600, f"token store is {oct(mode)}, not owner-only"


def test_save_narrows_a_file_that_was_already_too_open(token_file: Path) -> None:
    # touch() leaves an existing file's mode alone, so only the explicit chmod fixes this.
    token_file.write_text("{}")
    token_file.chmod(0o644)
    auth._save_tokens({"access_token": "a", "expires_in": 3600})
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_a_failed_write_leaves_the_previous_token_intact(
    token_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth._save_tokens({"access_token": "good", "refresh_token": "keep", "expires_in": 3600})

    def boom(*_a: object, **_k: object) -> None:
        msg = "disk full"
        raise OSError(msg)

    monkeypatch.setattr(Path, "write_text", boom)
    with pytest.raises(OSError, match="disk full"):
        auth._save_tokens({"access_token": "new", "expires_in": 3600})
    assert json.loads(token_file.read_text())["refresh_token"] == "keep"


def test_save_turns_expires_in_into_an_absolute_expiry(token_file: Path) -> None:
    before = time.time()
    stored = auth._save_tokens({"access_token": "a", "expires_in": 100})
    assert before + 100 <= stored["expires_at"] <= time.time() + 100
    assert json.loads(token_file.read_text())["expires_at"] == stored["expires_at"]


def test_missing_token_file_names_the_command_to_run(token_file: Path) -> None:
    with pytest.raises(SoundCloudAuthError, match="--sc-auth"):
        auth.load_access_token()


def test_unreadable_token_file_is_reported_not_swallowed(token_file: Path) -> None:
    token_file.write_text("{not json")
    with pytest.raises(SoundCloudAuthError, match="Could not read"):
        auth.load_access_token()


# ── Refresh ────────────────────────────────────────────────────────────────────


def test_fresh_token_is_returned_without_a_refresh(
    token_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth._save_tokens({"access_token": "fresh", "refresh_token": "r", "expires_in": 3600})
    monkeypatch.setattr(auth, "_post_token", _never_called)
    assert auth.load_access_token() == "fresh"


def test_token_inside_the_margin_is_refreshed(
    token_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth._save_tokens(
        {"access_token": "old", "refresh_token": "r1", "expires_in": auth._REFRESH_MARGIN_S / 2}
    )
    sent: dict[str, Any] = {}

    def fake_post(data: dict[str, str]) -> dict[str, Any]:
        sent.update(data)
        return {"access_token": "new", "refresh_token": "r2", "expires_in": 3600}

    monkeypatch.setattr(auth, "_post_token", fake_post)
    assert auth.load_access_token() == "new"
    assert sent == {"grant_type": "refresh_token", "refresh_token": "r1"}
    assert json.loads(token_file.read_text())["refresh_token"] == "r2"


def test_refresh_keeps_the_old_token_when_the_response_omits_one(
    token_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        auth, "_post_token", lambda _d: {"access_token": "new", "expires_in": 3600}
    )
    auth._refresh("keep-me")
    assert json.loads(token_file.read_text())["refresh_token"] == "keep-me"


def test_expired_token_with_no_refresh_token_asks_for_a_new_sign_in(token_file: Path) -> None:
    auth._save_tokens({"access_token": "old", "expires_in": -1})
    with pytest.raises(SoundCloudAuthError, match="--sc-auth"):
        auth.load_access_token()


# ── Callback server ────────────────────────────────────────────────────────────


def test_callback_server_captures_the_query() -> None:
    captured = _serve_and_request(["/callback?code=abc&state=xyz"])
    assert captured == {"code": "abc", "state": "xyz"}


def test_callback_server_ignores_a_stray_request_and_keeps_waiting() -> None:
    # A prefetch or a leftover tab hitting the port must not end the wait, or the real
    # redirect a moment later arrives at a closed socket.
    captured = _serve_and_request(["/callback?foo=1", "/callback?code=abc&state=xyz"])
    assert captured == {"code": "abc", "state": "xyz"}


def test_callback_server_ignores_a_request_with_the_wrong_state() -> None:
    captured = _serve_and_request(
        ["/callback?code=planted&state=wrong", "/callback?code=abc&state=xyz"]
    )
    assert captured == {"code": "abc", "state": "xyz"}


def test_callback_server_reports_a_port_it_cannot_take() -> None:
    import socket

    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        port = int(held.getsockname()[1])
        with pytest.raises(SoundCloudAuthError, match="Could not listen"):
            auth._bind_callback_server("127.0.0.1", port, "/callback", "xyz")


def test_callback_logging_never_carries_the_authorization_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("DEBUG", logger="soundcloud_dl.soundcloud_auth"):
        _serve_and_request(["/callback?code=s3cr3t-code&state=xyz"])
    assert "s3cr3t-code" not in caplog.text


# ── authorize() ────────────────────────────────────────────────────────────────


async def test_authorize_rejects_a_redirect_uri_it_cannot_listen_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "SOUNDCLOUD_REDIRECT_URI", "https://example.com/callback")
    with pytest.raises(SoundCloudAuthError, match="localhost"):
        await auth.authorize()


async def test_authorize_fails_fast_when_credentials_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Must raise before the browser opens, not after a five-minute wait that blames the
    # redirect for a problem that is really an empty .env.
    _stub_authorize(monkeypatch, echo_state=True)
    monkeypatch.setattr(auth, "SOUNDCLOUD_CLIENT_ID", None)
    monkeypatch.setattr(auth, "_await_callback", _never_called)
    with pytest.raises(SoundCloudAuthError, match="SOUNDCLOUD_CLIENT_ID"):
        await auth.authorize()


async def test_authorize_rejects_a_mismatched_state(
    monkeypatch: pytest.MonkeyPatch, token_file: Path
) -> None:
    _stub_authorize(monkeypatch, {"code": "abc", "state": "not-the-one-we-sent"})
    with pytest.raises(SoundCloudAuthError, match="wrong state"):
        await auth.authorize()
    assert not token_file.exists(), "a rejected sign-in must not write a token"


async def test_authorize_reports_a_refusal_from_soundcloud(
    monkeypatch: pytest.MonkeyPatch, token_file: Path
) -> None:
    _stub_authorize(monkeypatch, {"error": "access_denied", "error_description": "user said no"})
    with pytest.raises(SoundCloudAuthError, match="access_denied"):
        await auth.authorize()
    assert not token_file.exists()


async def test_authorize_saves_tokens_on_the_happy_path(
    monkeypatch: pytest.MonkeyPatch, token_file: Path
) -> None:
    sent: dict[str, Any] = {}
    _stub_authorize(monkeypatch, echo_state=True)
    monkeypatch.setattr(
        auth,
        "_post_token",
        lambda d: sent.update(d)
        or {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "*"},
    )
    await auth.authorize()
    stored = json.loads(token_file.read_text())
    assert stored["access_token"] == "at"
    assert stored["refresh_token"] == "rt"
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "abc"
    # PKCE only protects the exchange if the verifier actually rides along with it.
    assert sent["code_verifier"]


# ── The playlist owner's token ─────────────────────────────────────────────────


@pytest.fixture
def owner_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "owner_token.json"
    monkeypatch.setattr(auth, "get_owner_token_file", lambda: path)
    return path


def _grant(_data: dict[str, str]) -> dict[str, Any]:
    return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "*"}


async def test_owner_sign_in_saves_to_its_own_file_after_the_owner_check(
    monkeypatch: pytest.MonkeyPatch, token_file: Path, owner_file: Path
) -> None:
    _stub_authorize(monkeypatch, echo_state=True)
    monkeypatch.setattr(auth, "_post_token", _grant)
    monkeypatch.setattr(auth, "_me_id", lambda _t: 7)
    monkeypatch.setattr(auth, "_playlist_owner_id", lambda _t: 7)
    await auth.authorize(owner=True)
    assert json.loads(owner_file.read_text())["access_token"] == "at"
    assert not token_file.exists(), "the owner sign-in must never replace the bot's token"


async def test_owner_sign_in_refuses_an_account_that_does_not_own_the_playlist(
    monkeypatch: pytest.MonkeyPatch, token_file: Path, owner_file: Path
) -> None:
    _stub_authorize(monkeypatch, echo_state=True)
    monkeypatch.setattr(auth, "_post_token", _grant)
    monkeypatch.setattr(auth, "_me_id", lambda _t: 7)
    monkeypatch.setattr(auth, "_playlist_owner_id", lambda _t: 8)
    with pytest.raises(SoundCloudAuthError, match="belongs to 8"):
        await auth.authorize(owner=True)
    assert not owner_file.exists()
    assert not token_file.exists()


async def test_owner_sign_in_saves_nothing_when_me_does_not_answer(
    monkeypatch: pytest.MonkeyPatch, owner_file: Path
) -> None:
    _stub_authorize(monkeypatch, echo_state=True)
    monkeypatch.setattr(auth, "_post_token", _grant)

    class _Resp:
        status_code = 503

    class _Client:
        def __init__(self, **_kw: object) -> None: ...
        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_a: object) -> None: ...
        def get(self, *_a: object, **_kw: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr(auth.httpx, "Client", _Client)
    with pytest.raises(SoundCloudAuthError, match="503"):
        await auth.authorize(owner=True)
    assert not owner_file.exists()


def test_load_access_token_reads_the_file_it_is_given(token_file: Path, tmp_path: Path) -> None:
    owner = tmp_path / "owner.json"
    auth._save_tokens({"access_token": "owner-at", "expires_in": 3600}, owner)
    auth._save_tokens({"access_token": "bot-at", "expires_in": 3600})
    assert auth.load_access_token(owner) == "owner-at"
    assert auth.load_access_token() == "bot-at"


def test_a_missing_owner_token_names_the_owner_sign_in(tmp_path: Path) -> None:
    with pytest.raises(SoundCloudAuthError, match="--authorize-owner"):
        auth.load_access_token(tmp_path / "none.json", "--authorize-owner")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _never_called(*_args: object, **_kwargs: object) -> None:
    msg = "_post_token should not have been called"
    raise AssertionError(msg)


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _request(url: str, attempts: int = 40) -> None:
    """GET a localhost URL, retrying while the server is still coming up."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2):  # noqa: S310
                return
        except urllib.error.HTTPError:
            # A 404 is a real answer: the server is up and chose to ignore this request.
            return
        except OSError as exc:
            last = exc
            time.sleep(0.1)
    msg = f"server never came up for {url}"
    raise AssertionError(msg) from last


def _serve_and_request(paths: list[str], expected_state: str = "xyz") -> dict[str, str]:
    """Run one callback server, send it each path in order, and return what it captured."""
    port = _free_port()
    server = auth._bind_callback_server("127.0.0.1", port, "/callback", expected_state)
    captured: dict[str, dict[str, str]] = {}

    def serve() -> None:
        captured["q"] = auth._await_callback(server)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    for path in paths:
        _request(f"http://127.0.0.1:{port}{path}")
    thread.join(timeout=10)
    assert "q" in captured, "the callback server never returned"
    return captured["q"]


def _stub_authorize(
    monkeypatch: pytest.MonkeyPatch,
    returned: dict[str, str] | None = None,
    *,
    echo_state: bool = False,
) -> None:
    """Replace the browser and the callback server so authorize() runs offline."""
    monkeypatch.setattr(auth, "SOUNDCLOUD_REDIRECT_URI", "http://localhost:8080/callback")
    monkeypatch.setattr(auth, "SOUNDCLOUD_CLIENT_ID", "cid")
    monkeypatch.setattr(auth, "SOUNDCLOUD_CLIENT_SECRET", "secret")
    opened: dict[str, str] = {}

    async def fake_open(_stack: object, url: str) -> str:
        opened["url"] = url
        return "a fake browser"

    monkeypatch.setattr(auth, "_open_sign_in", fake_open)
    monkeypatch.setattr(auth.webbrowser, "open", lambda url: opened.update(url=url, default="yes"))
    monkeypatch.setattr(auth, "_whoami", lambda _t: "tester")

    bound: dict[str, str] = {}

    def fake_bind(_host: str, _port: int, _path: str, expected_state: str) -> object:
        bound["state"] = expected_state
        return object()

    def fake_await(_server: object) -> dict[str, str]:
        # The port has to be taken before the browser is sent anywhere, or a busy port
        # hands the authorization code to whatever already holds it.
        assert opened, "the browser was opened before the callback port was bound"
        if not echo_state:
            return dict(returned or {})
        return {"code": "abc", "state": bound["state"]}

    monkeypatch.setattr(auth, "_bind_callback_server", fake_bind)
    monkeypatch.setattr(auth, "_await_callback", fake_await)
