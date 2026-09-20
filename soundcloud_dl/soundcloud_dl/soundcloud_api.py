"""Do the SoundCloud actions through APIs instead of clicking the web UI.

Three surfaces, because no one of them does everything:

  - api.soundcloud.com with a user token — follows, and reading back what landed. It has
    no write route for likes or reposts; every shape tried answered 405 unknown route.
  - api-v2.soundcloud.com, called from inside the signed-in page — the like and repost
    writes. This is what the web app itself does, so the calls carry the page's session
    and look like the UI rather than like a script.
  - the buttons, still in soundcloud_actions.py, as the fallback.

Clicking failed on finding the controls rather than on the actions. A half-rendered track
page still offers the player bar's like button, which likes whatever was played last
instead of the track in hand — addressing tracks by id is what removes that whole class of
mistake.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

from soundcloud_dl.config import SOUNDCLOUD_API_BASE
from soundcloud_dl.soundcloud_auth import load_access_token

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.soundcloud_api")

API_V2 = "https://api-v2.soundcloud.com"

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NO_CONTENT = 204
_HTTP_NOT_FOUND = 404

# Only ever read straight after a write, when the track is the newest entry. Paging a whole
# collection to answer "is this old track liked" would cost many requests to learn nothing
# the write itself did not already report.
_VERIFY_PAGE_SIZE = 200

# Runs inside the page so the request carries its session. The web app sends the token as a
# header, not as a cookie, even though that is where it keeps it.
_API_V2_JS = """
async ([method, path]) => {
  const raw = (document.cookie.match(/(?:^|; )oauth_token=([^;]+)/) || [])[1];
  if (!raw) return { status: 0, body: 'no oauth_token cookie - the browser is signed out' };
  const r = await fetch('https://api-v2.soundcloud.com' + path, {
    method,
    credentials: 'include',
    headers: { 'Authorization': 'OAuth ' + decodeURIComponent(raw) },
  });
  // Returned whole. Truncating here to keep error messages short also cut /me's JSON in
  // half, so the identity check could never parse it. Python trims for display instead.
  return { status: r.status, body: await r.text() };
}
"""


class ApiError(RuntimeError):
    """A SoundCloud API call did not do what was asked."""


class AccountMismatch(RuntimeError):  # noqa: N818
    """The browser and the stored token are different SoundCloud users."""


@contextlib.asynccontextmanager
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    """An httpx client carrying the stored user token, for api.soundcloud.com."""
    # load_access_token may refresh over the network, which would block the event loop.
    token = await asyncio.to_thread(load_access_token)
    async with httpx.AsyncClient(
        base_url=SOUNDCLOUD_API_BASE,
        headers={
            "Authorization": f"OAuth {token}",
            "Accept": "application/json; charset=utf-8",
        },
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        yield client


# ── api.soundcloud.com ─────────────────────────────────────────────────────────


async def resolve(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Turn a soundcloud.com permalink into its resource, which carries the numeric id."""
    resp = await client.get("/resolve", params={"url": url})
    if resp.status_code != _HTTP_OK:
        msg = f"resolve({url}) returned {resp.status_code}: {resp.text[:120]}"
        raise ApiError(msg)
    return resp.json()


async def resolve_user(client: httpx.AsyncClient, handle: str) -> dict[str, Any]:
    """Turn a @handle a gate named into that user, refusing anything that is not one.

    A permalink is not reserved to profiles — soundcloud.com/<handle> can be a playlist or
    a track. The kind check is what stops a mistyped handle being followed as if it were a
    person, which is a real action on a real account and cannot be taken back quietly.
    """
    resource = await resolve(client, f"https://soundcloud.com/{handle}")
    if resource.get("kind") != "user":
        msg = f"@{handle} resolved to {resource.get('kind')!r}, not a user"
        raise ApiError(msg)
    # /resolve follows redirects, so a permalink that has been renamed or reassigned
    # answers as whoever holds it now — a different person than the gate asked for.
    got = str(resource.get("permalink", "")).lower()
    if got != handle.lower():
        msg = f"@{handle} resolved to a different profile, @{got}"
        raise ApiError(msg)
    return resource


async def me(client: httpx.AsyncClient) -> dict[str, Any]:
    """The account the stored token belongs to."""
    resp = await client.get("/me")
    if resp.status_code != _HTTP_OK:
        msg = f"/me returned {resp.status_code} — the stored token may be dead"
        raise ApiError(msg)
    return resp.json()


async def is_following(client: httpx.AsyncClient, user_id: int) -> bool:
    """Exact, unlike the collection reads — this route answers for one user."""
    return (await client.get(f"/me/followings/{user_id}")).status_code == _HTTP_OK


async def set_following(
    client: httpx.AsyncClient, user_id: int, *, on: bool
) -> tuple[bool, str, bool]:
    """Follow or unfollow, then read the state back rather than trusting the status.

    The third value says whether this call changed anything. That is what lets a caller
    give back a follow a gate charged without touching one the user already had.
    """
    before = await is_following(client, user_id)
    if before is on:
        return True, f"already {'following' if on else 'not following'} {user_id}", False

    method = "PUT" if on else "DELETE"
    resp = await client.request(method, f"/me/followings/{user_id}")
    if await is_following(client, user_id) is on:
        return True, f"{'following' if on else 'not following'} {user_id}", True
    # The body carries the real reason and is often the whole answer: hitting SoundCloud's
    # 2000-following cap reads as a bare 422 without it.
    return False, f"{method} returned {resp.status_code}: {resp.text[:160]}", False


async def post_comment(client: httpx.AsyncClient, track_id: int, text: str) -> tuple[bool, str]:
    """Post a comment on a track. The id in the reply is the confirmation."""
    resp = await client.post(f"/tracks/{track_id}/comments", json={"comment": {"body": text}})
    if resp.status_code not in (_HTTP_OK, _HTTP_CREATED):
        return False, f"POST comments returned {resp.status_code}: {resp.text[:80]}"
    comment_id = resp.json().get("id")
    if not comment_id:
        return False, "comment accepted but no id came back"
    return True, f"comment {comment_id} posted"


async def _in_recent(client: httpx.AsyncClient, path: str, track_id: int) -> bool:
    resp = await client.get(path, params={"limit": _VERIFY_PAGE_SIZE})
    if resp.status_code != _HTTP_OK:
        return False
    body = resp.json()
    items = body if isinstance(body, list) else body.get("collection", [])
    return any(item.get("id") == track_id for item in items)


async def is_liked(client: httpx.AsyncClient, track_id: int) -> bool:
    """True if the track is in the newest page of likes. See _VERIFY_PAGE_SIZE."""
    return await _in_recent(client, "/me/likes/tracks", track_id)


async def is_reposted(client: httpx.AsyncClient, track_id: int) -> bool:
    """True if the track is in the newest page of reposts. See _VERIFY_PAGE_SIZE."""
    return await _in_recent(client, "/me/reposts/tracks", track_id)


# ── api-v2, through the signed-in page ─────────────────────────────────────────


async def ensure_on_soundcloud(page: Page) -> None:
    """api-v2 answers same-origin calls, and the session cookie is only readable there."""
    if "soundcloud.com" not in (page.url or ""):
        await page.goto(
            "https://soundcloud.com/discover", wait_until="domcontentloaded", timeout=40_000
        )


async def _api_v2(page: Page, method: str, path: str) -> tuple[int, str]:
    result = await page.evaluate(_API_V2_JS, [method, path])
    return int(result["status"]), str(result["body"])


async def browser_user_id(page: Page) -> int:
    """The account the browser is signed in as."""
    status, body = await _api_v2(page, "GET", "/me")
    if status != _HTTP_OK:
        msg = f"api-v2 /me returned {status}: {body[:120]}"
        raise ApiError(msg)
    try:
        return int(json.loads(body).get("id"))
    except (ValueError, TypeError, AttributeError) as exc:
        msg = f"api-v2 /me gave no usable id: {body[:120]}"
        raise ApiError(msg) from exc


async def assert_same_account(page: Page, token_user_id: int) -> int:
    """Raise unless the browser and the token are the same user, and return that id.

    They diverged once, and nothing failed until much later: follows went to one account
    through the token while likes and reposts went to another through the page, so every
    gate saw half its requirements met and none of them said why.
    """
    browser_id = await browser_user_id(page)
    if browser_id != token_user_id:
        msg = (
            f"the browser is signed in as user {browser_id} but the stored token is for "
            f"{token_user_id} — re-run: deno task py --sc-auth"
        )
        raise AccountMismatch(msg)
    return browser_id


async def _write_v2(page: Page, method: str, path: str) -> tuple[bool, str]:
    status, body = await _api_v2(page, method, path)
    if status in (_HTTP_OK, _HTTP_NO_CONTENT):
        return True, f"api-v2 {status}"
    # A DELETE for something that was never set is the state we wanted, not a failure.
    if status == _HTTP_NOT_FOUND and method == "DELETE":
        return True, "api-v2 404 — was not set"
    return False, f"api-v2 {method} {path} returned {status}: {body[:80]}"


async def set_like(page: Page, user_id: int, track_id: int, *, on: bool) -> tuple[bool, str]:
    """Like or unlike, by id. The path is per-user here — unlike set_repost."""
    method = "PUT" if on else "DELETE"
    return await _write_v2(page, method, f"/users/{user_id}/track_likes/{track_id}")


async def set_repost(page: Page, track_id: int, *, on: bool) -> tuple[bool, str]:
    """Repost or un-repost, by id.

    Addressed as /me, not /users/{id} like set_like. That asymmetry reads like a typo and
    is not: the per-user spelling answers 404 for reposts.
    """
    method = "PUT" if on else "DELETE"
    return await _write_v2(page, method, f"/me/track_reposts/{track_id}")
