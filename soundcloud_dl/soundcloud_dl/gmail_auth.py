"""One-time Gmail sign-in, so a Laylo run can read what Laylo sends after an RSVP.

That is a confirmation email, or texts Google Voice forwards to this inbox. The scope is
gmail.readonly: it reads the whole mailbox but never sends, changes or deletes anything.

The loopback, PKCE and token-file mechanics are soundcloud_auth's, reused as they are.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import webbrowser
from typing import Any
from urllib.parse import urlencode

import httpx

from soundcloud_dl import config
from soundcloud_dl.soundcloud_auth import (
    SoundCloudAuthError,
    _await_callback,
    _bind_callback_server,
    _load_stored,
    _pkce_pair,
    _save_tokens,
    _state_matches,
)

logger = logging.getLogger("soundcloud_dl.gmail_auth")

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"

_HINT = "--authorize-gmail"
_REFRESH_MARGIN_S = 120.0
_HTTP_OK = 200


class GmailAuthError(RuntimeError):
    """Raised when no usable Gmail token can be obtained."""


def _client_fields() -> dict[str, str]:
    if not config.GMAIL_CLIENT_ID or not config.GMAIL_CLIENT_SECRET:
        msg = (
            "TUNEWRANGLER_SC_GMAIL_CLIENT_ID and TUNEWRANGLER_SC_GMAIL_CLIENT_SECRET are "
            "required. Create a Desktop-app OAuth client in Google Cloud and set them in .env."
        )
        raise GmailAuthError(msg)
    return {"client_id": config.GMAIL_CLIENT_ID, "client_secret": config.GMAIL_CLIENT_SECRET}


def _post_token(data: dict[str, str]) -> dict[str, Any]:
    # No redirect following: the body carries the code, the verifier and the client secret.
    with httpx.Client(follow_redirects=False) as client:
        resp = client.post(TOKEN_URL, data=data | _client_fields(), timeout=30.0)
    if resp.status_code != _HTTP_OK:
        # invalid_grant here means the refresh token was revoked or expired — which is what
        # a consent screen left in Testing does to it after seven days.
        msg = f"Google token endpoint returned {resp.status_code}: {resp.text[:300]}"
        if "invalid_grant" in resp.text:
            msg += f". Run: deno task py {_HINT}"
        raise GmailAuthError(msg)
    body = resp.json()
    if not body.get("access_token"):
        msg = "Google token response carried no access_token"
        raise GmailAuthError(msg)
    return body


def load_gmail_access_token() -> str:
    """A usable Gmail access token, refreshed first if it is close to expiry."""
    try:
        stored = _load_stored(config.get_gmail_token_file(), _HINT)
    except SoundCloudAuthError as exc:
        raise GmailAuthError(str(exc)) from exc
    if float(stored.get("expires_at", 0)) - time.time() > _REFRESH_MARGIN_S:
        return str(stored["access_token"])
    refresh_token = str(stored.get("refresh_token", ""))
    if not refresh_token:
        msg = f"The Gmail token expired and carries no refresh token. Run: deno task py {_HINT}"
        raise GmailAuthError(msg)
    body = _post_token({"grant_type": "refresh_token", "refresh_token": refresh_token})
    # Google does not return the refresh token on a refresh; keep the one we have.
    body.setdefault("refresh_token", refresh_token)
    return str(_save_tokens(body, config.get_gmail_token_file())["access_token"])


def gmail_problem() -> str | None:
    """Why a Laylo run cannot read texts right now, or None if it can."""
    try:
        load_gmail_access_token()
    except GmailAuthError as exc:
        return f"laylo cannot read texts: {exc}"
    return None


def _account_email(access_token: str) -> str:
    resp = httpx.get(
        f"{GMAIL_API}/profile",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30.0,
    )
    if resp.status_code != _HTTP_OK:
        # The token came back but the API refused it: almost always the Gmail API not
        # being enabled on the Cloud project, which the body names.
        msg = f"Gmail API returned {resp.status_code}: {resp.text[:300]}"
        raise GmailAuthError(msg)
    return str(resp.json().get("emailAddress", "?"))


async def authorize_gmail() -> None:
    """Run the interactive sign-in once and save the resulting tokens."""
    client_id = _client_fields()["client_id"]
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    try:
        # Port 0: Desktop clients accept any loopback port, so take whichever is free.
        server = _bind_callback_server("127.0.0.1", 0, "/", state)
    except SoundCloudAuthError as exc:
        raise GmailAuthError(str(exc)) from exc
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/"
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            # offline + consent is what makes Google hand back a refresh token every time,
            # not only on the very first grant.
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    url = f"{AUTHORIZE_URL}?{query}"
    try:
        webbrowser.open(url)
        logger.info("Gmail sign-in opened in your default browser")
        logger.info("If nothing opens, paste this into a browser:\n%s", url)
        returned = await asyncio.to_thread(_await_callback, server)
    except SoundCloudAuthError as exc:
        raise GmailAuthError(str(exc)) from exc
    except BaseException:
        server.server_close()
        raise

    if returned.get("error"):
        msg = f"Google refused the sign-in: {returned['error']}"
        raise GmailAuthError(msg)
    if not _state_matches(returned.get("state", ""), state):
        msg = "The redirect carried the wrong state value — sign-in rejected"
        raise GmailAuthError(msg)
    code = returned.get("code")
    if not code:
        msg = "The redirect carried no authorization code"
        raise GmailAuthError(msg)

    body = _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
    )
    # Google's consent screen lets the box be unticked, and a token without the scope fails
    # much later as a 403 on the first poll, mid-RSVP.
    if SCOPE not in str(body.get("scope", "")).split():
        msg = "Gmail read access was not granted — run it again and leave the box ticked"
        raise GmailAuthError(msg)
    token_file = config.get_gmail_token_file()
    stored = _save_tokens(body, token_file)
    # Named because the account is the one thing a sign-in can get silently wrong: a token
    # for an inbox Google Voice does not forward to fails later as a text that never arrives.
    logger.info(
        "Gmail signed in as %r. Token saved to %s (refresh token %s)",
        _account_email(stored["access_token"]),
        token_file,
        "stored" if stored["refresh_token"] else "MISSING — you will have to sign in again",
    )
