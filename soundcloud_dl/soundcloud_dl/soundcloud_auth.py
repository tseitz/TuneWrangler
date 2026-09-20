"""One-time OAuth sign-in, so the API can act as the user rather than as the app.

The client-credentials token playlist.py uses is app-only: /me answers 401 with it, so it
can never follow, like or repost — every one of those means "me". Only the
authorization-code flow issues a token that has a user behind it. A human does that once;
the refresh token keeps it alive afterwards.

The point is to stop driving SoundCloud through its own web UI. That UI's api-v2 calls sit
behind the bot protection detected in gate_handlers/captcha.py, which challenges them and
leaves the page rendering nothing. SOUNDCLOUD_API_BASE is a different surface and is not
challenged.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from soundcloud_dl.config import (
    SOUNDCLOUD_API_BASE,
    SOUNDCLOUD_CLIENT_ID,
    SOUNDCLOUD_CLIENT_SECRET,
    SOUNDCLOUD_REDIRECT_URI,
    SOUNDCLOUD_TOKEN_URL,
    get_token_file,
)

logger = logging.getLogger("soundcloud_dl.soundcloud_auth")

AUTHORIZE_URL = "https://secure.soundcloud.com/authorize"

# Refresh this far ahead of the stated expiry. A token that dies mid-run surfaces as a
# puzzling 401 on whichever call happened to be next, not as an expiry.
_REFRESH_MARGIN_S = 120.0

# How long to wait for the human to finish signing in before giving the port back.
_CALLBACK_TIMEOUT_S = 300.0
_POLL_INTERVAL_S = 0.5

_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400

_DONE_PAGE = b"""<!doctype html><meta charset="utf-8"><title>Signed in</title>
<body style="font-family:system-ui;padding:3rem">
<h2>Signed in.</h2><p>You can close this tab and go back to the terminal.</p></body>"""

_FAIL_PAGE = b"""<!doctype html><meta charset="utf-8"><title>Sign-in failed</title>
<body style="font-family:system-ui;padding:3rem">
<h2>Sign-in failed.</h2><p>The terminal has the reason.</p></body>"""


class SoundCloudAuthError(RuntimeError):
    """Raised when no usable user token can be obtained."""


def _client_fields() -> dict[str, str]:
    """Client credentials as form fields.

    Not a Basic auth header. SoundCloud takes Basic only on the client_credentials grant
    (playlist.py) and answers the authorization_code grant with a bare 400 invalid_request
    when the credentials arrive that way instead of in the body.
    """
    if not SOUNDCLOUD_CLIENT_ID or not SOUNDCLOUD_CLIENT_SECRET:
        msg = "SOUNDCLOUD_CLIENT_ID and SOUNDCLOUD_CLIENT_SECRET are required. Set them in .env."
        raise SoundCloudAuthError(msg)
    return {"client_id": SOUNDCLOUD_CLIENT_ID, "client_secret": SOUNDCLOUD_CLIENT_SECRET}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge) for PKCE, the S256 method."""
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def _state_matches(returned: str, expected: str) -> bool:
    """Constant-time state comparison that survives a non-ASCII value.

    compare_digest raises TypeError on a non-ASCII str, which would surface as a traceback
    instead of a rejection when a stray local request carries one.
    """
    if not returned.isascii() or not expected.isascii():
        return False
    return secrets.compare_digest(returned, expected)


class _CallbackHandler(BaseHTTPRequestHandler):
    """Catches the one redirect back from SoundCloud and stashes its query."""

    # Set by _bind_callback_server before the server runs.
    result: dict[str, str]
    callback_path: str
    expected_state: str

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
        if not self._is_the_redirect(parsed.path, query):
            # Anything else has to leave the wait running. Treating every request as the
            # redirect lets a background tab or a prefetch end it, and the real one then
            # arrives at a closed port.
            logger.debug("callback server: ignored a request for %s", parsed.path)
            self.send_error(404)
            return
        self.result.update(query)
        ok = "code" in query
        self.send_response(_HTTP_OK if ok else _HTTP_BAD_REQUEST)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_DONE_PAGE if ok else _FAIL_PAGE)

    def _is_the_redirect(self, path: str, query: dict[str, str]) -> bool:
        if path != self.callback_path:
            return False
        if "code" not in query and "error" not in query:
            return False
        return _state_matches(query.get("state", ""), self.expected_state)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:  # noqa: ARG002
        # The default logs self.requestline, which carries the authorization code in its
        # query string — so --debug would write a live credential into the rotating log.
        logger.debug("callback server: %s -> %s", urlparse(self.path).path, code)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ANN401
        logger.debug("callback server: %s", format % args)


def _bind_callback_server(host: str, port: int, path: str, expected_state: str) -> HTTPServer:
    """Take the callback port before the browser is sent anywhere.

    Binding first is what makes a busy port safe. Open the browser first and a port 8080
    already held by some other local app receives the redirect instead — and logs the
    authorization code in its own access log.
    """
    result: dict[str, str] = {}
    handler = type(
        "_BoundCallbackHandler",
        (_CallbackHandler,),
        {"result": result, "callback_path": path, "expected_state": expected_state},
    )
    try:
        # Loopback only. The redirect is the one thing that should reach this port, and it
        # comes from this machine's own browser.
        server = HTTPServer((host, port), handler)
    except OSError as exc:
        msg = f"Could not listen on {host}:{port} for the sign-in redirect: {exc}"
        raise SoundCloudAuthError(msg) from exc
    server.timeout = _POLL_INTERVAL_S
    return server


def _await_callback(server: HTTPServer) -> dict[str, str]:
    """Serve until the redirect arrives, and return its query parameters."""
    result: dict[str, str] = server.RequestHandlerClass.result  # type: ignore[attr-defined]
    deadline = time.monotonic() + _CALLBACK_TIMEOUT_S
    with server:
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if not result:
        host, port = server.server_address[:2]
        msg = f"No sign-in redirect arrived on {host}:{port} within {int(_CALLBACK_TIMEOUT_S)}s"
        raise SoundCloudAuthError(msg)
    return result


def _post_token(data: dict[str, str]) -> dict[str, Any]:
    """Exchange or refresh at the token endpoint, and return the parsed body."""
    # No redirect following. A 307/308 preserves the body, and the body here is the
    # authorization code, the PKCE verifier and the client secret. A token endpoint has no
    # business redirecting anyway.
    with httpx.Client(follow_redirects=False) as client:
        resp = client.post(
            SOUNDCLOUD_TOKEN_URL,
            headers={
                "Accept": "application/json; charset=utf-8",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=data | _client_fields(),
            timeout=30.0,
        )
    if resp.status_code != _HTTP_OK:
        # The body names the actual problem — a redirect URI that does not match, an
        # expired code. Included because the status alone sends people hunting the wrong one.
        msg = f"Token endpoint returned {resp.status_code}: {resp.text[:300]}"
        raise SoundCloudAuthError(msg)
    body = resp.json()
    if not body.get("access_token"):
        msg = "Token response carried no access_token"
        raise SoundCloudAuthError(msg)
    return body


def _save_tokens(body: dict[str, Any]) -> dict[str, Any]:
    """Write the token store with owner-only permissions, and return what was stored."""
    path = get_token_file()
    stored = {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token", ""),
        "expires_at": time.time() + float(body.get("expires_in", 3600)),
        "scope": body.get("scope", ""),
    }
    # Written via a sibling then renamed. Truncating the real file in place means a crash
    # mid-write leaves unparseable JSON where the only copy of a working refresh token
    # used to be, and the only way back is signing in by hand again.
    tmp = path.with_suffix(".tmp")
    # touch() will not narrow an existing file's mode, so the chmod is load-bearing.
    tmp.touch(mode=0o600, exist_ok=True)
    tmp.chmod(0o600)
    tmp.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    tmp.replace(path)
    return stored


def _load_stored() -> dict[str, Any]:
    path = get_token_file()
    if not path.exists():
        msg = f"No user token at {path}. Run: deno task py --sc-auth"
        raise SoundCloudAuthError(msg)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        msg = f"Could not read the token store at {path}: {exc}"
        raise SoundCloudAuthError(msg) from exc


def _refresh(refresh_token: str) -> dict[str, Any]:
    body = _post_token({"grant_type": "refresh_token", "refresh_token": refresh_token})
    # SoundCloud rotates the refresh token on use. Dropping the new one strands the store
    # on a value that is already spent, and the next run has to sign in by hand again.
    if not body.get("refresh_token"):
        body["refresh_token"] = refresh_token
    return _save_tokens(body)


def load_access_token() -> str:
    """Return a usable user access token, refreshing it first if it is close to expiry."""
    stored = _load_stored()
    if float(stored.get("expires_at", 0)) - time.time() > _REFRESH_MARGIN_S:
        return str(stored["access_token"])
    refresh_token = str(stored.get("refresh_token", ""))
    if not refresh_token:
        msg = "The stored token expired and carries no refresh token. Run: deno task py --sc-auth"
        raise SoundCloudAuthError(msg)
    logger.info("User token expired or near expiry — refreshing")
    return str(_refresh(refresh_token)["access_token"])


def _whoami(access_token: str) -> str:
    """The account a token belongs to, so a run can say who it is about to act as."""
    with httpx.Client(follow_redirects=True) as client:
        resp = client.get(
            f"{SOUNDCLOUD_API_BASE}/me",
            headers={
                "Authorization": f"OAuth {access_token}",
                "Accept": "application/json; charset=utf-8",
            },
            timeout=30.0,
        )
    if resp.status_code != _HTTP_OK:
        return "unknown"
    return str(resp.json().get("permalink") or "unknown")


async def _open_sign_in(stack: contextlib.AsyncExitStack, url: str) -> str:
    """Show the sign-in page, preferring the browser the gates are driven in.

    The token has to belong to the same account as that browser. Using the default browser
    signed us in as one account while the gate ran as another, and the two halves of a run
    then acted as different people — follows on one, likes and reposts on the other.

    The attach is held open by the caller's stack, because dropping it closes the tab the
    sign-in is happening in.
    """
    try:
        from soundcloud_dl.playwright_browser import attached_browser, new_page  # noqa: PLC0415

        context = await stack.enter_async_context(attached_browser(headed=True))
        page = await new_page(context)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not open the automation Chrome (%s). Falling back to your default "
            "browser — it must be signed in as the account the gates run as.",
            exc,
        )
        webbrowser.open(url)
        return "your default browser"
    return "the automation Chrome"


async def authorize() -> None:
    """Run the interactive sign-in once and save the resulting tokens."""
    parsed = urlparse(SOUNDCLOUD_REDIRECT_URI)
    if parsed.hostname not in ("localhost", "127.0.0.1") or not parsed.port:
        msg = (
            f"SOUNDCLOUD_REDIRECT_URI must be a localhost URI with a port so this can catch "
            f"the redirect. Got: {SOUNDCLOUD_REDIRECT_URI}"
        )
        raise SoundCloudAuthError(msg)
    # Checked here rather than at the exchange. Missing credentials would otherwise show up
    # as an opaque SoundCloud error page and a five-minute wait that blames the redirect.
    client_id = _client_fields()["client_id"]

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": SOUNDCLOUD_REDIRECT_URI,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    url = f"{AUTHORIZE_URL}?{query}"

    server = _bind_callback_server("127.0.0.1", parsed.port, parsed.path or "/", state)
    try:
        async with contextlib.AsyncExitStack() as stack:
            where = await _open_sign_in(stack, url)
            logger.info("SoundCloud sign-in opened in %s", where)
            logger.info("If nothing opens, paste this into a browser:\n%s", url)
            # The blocking wait runs off the event loop so the browser attach above stays
            # serviceable for the whole sign-in.
            returned = await asyncio.to_thread(_await_callback, server)
    except BaseException:
        server.server_close()
        raise

    if returned.get("error"):
        detail = returned.get("error_description", "")
        msg = f"SoundCloud refused the sign-in: {returned['error']} {detail}".strip()
        raise SoundCloudAuthError(msg)
    # The handler already rejects a mismatch, so this is the second lock on the same door.
    # Without either, anyone who can make the browser hit the callback can plant their own
    # authorization code, and the tokens we store would be for their account.
    if not _state_matches(returned.get("state", ""), state):
        msg = "The redirect carried the wrong state value — sign-in rejected"
        raise SoundCloudAuthError(msg)
    code = returned.get("code")
    if not code:
        msg = "The redirect carried no authorization code"
        raise SoundCloudAuthError(msg)

    stored = _save_tokens(
        _post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SOUNDCLOUD_REDIRECT_URI,
                "code_verifier": verifier,
            }
        )
    )
    # Named out loud because the account is the one thing a sign-in can get silently wrong,
    # and a token for the wrong account fails much later as a gate that never unlocks.
    logger.info(
        "Signed in as %r. Token saved to %s (refresh token %s)",
        _whoami(stored["access_token"]),
        get_token_file(),
        "stored" if stored["refresh_token"] else "MISSING — you will have to sign in again",
    )
