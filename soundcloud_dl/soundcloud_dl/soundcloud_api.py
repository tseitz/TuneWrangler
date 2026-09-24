"""Do the SoundCloud actions through APIs instead of clicking the web UI.

Three surfaces, because no one of them does everything:

  - api.soundcloud.com with a user token — follows, likes and reposts, and reading back
    what landed. Likes and reposts are only routed when addressed by URN
    (`/reposts/tracks/soundcloud:tracks:<id>`); every id-only shape answered 405.
  - api-v2.soundcloud.com, called from inside the signed-in page — the fallback for a like
    or repost, and the only route for undoing one. SoundCloud's bot protection answers
    many of these with a 403 captcha challenge, which is why it is no longer first.
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
import re
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
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

# Comments are read to the end instead, so this only sets how many hops that takes. 200 is
# the most the route will return for one.
_COMMENT_PAGE_SIZE = 200

# A cursor loop driven by the server needs its own end. Without one a next_href pointing
# at itself never returns, and the per-request timeout does not bound the loop.
_MAX_COMMENT_PAGES = 25

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
async def api_client(
    token_file: Path | None = None, hint: str = "--sc-auth"
) -> AsyncIterator[httpx.AsyncClient]:
    """An httpx client carrying a stored user token (the bot's unless told otherwise)."""
    # load_access_token may refresh over the network, which would block the event loop.
    token = await asyncio.to_thread(load_access_token, token_file, hint)
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


async def write_by_token(
    client: httpx.AsyncClient, collection: str, track_id: int
) -> tuple[bool, str]:
    """Like or repost a track through the token API. `collection` is "likes" or "reposts"."""
    path = f"/{collection}/tracks/soundcloud:tracks:{track_id}"
    resp = await client.post(path)
    if resp.status_code in (_HTTP_OK, _HTTP_CREATED):
        return True, f"POST {collection} {resp.status_code}"
    return False, f"POST {path} returned {resp.status_code}: {resp.text[:80]}"


async def post_comment(client: httpx.AsyncClient, track_id: int, text: str) -> tuple[bool, str]:
    """Post a comment on a track. The id in the reply is the confirmation."""
    resp = await client.post(f"/tracks/{track_id}/comments", json={"comment": {"body": text}})
    if resp.status_code not in (_HTTP_OK, _HTTP_CREATED):
        return False, f"POST comments returned {resp.status_code}: {resp.text[:80]}"
    comment_id = resp.json().get("id")
    if not comment_id:
        return False, "comment accepted but no id came back"
    return True, f"comment {comment_id} posted"


def same_host_path(next_href: str, base: str = SOUNDCLOUD_API_BASE) -> str:
    """Reduce a pagination cursor to a path on the given API host.

    next_href is an absolute URL taken from a response body, and api_client() carries the
    user's OAuth token as a default header — which httpx attaches to whatever host it is
    handed. It strips credentials across a cross-origin *redirect*, but a URL passed
    straight to .get() is not a redirect, so nothing would strip it there. A body naming
    another host would hand that host the token.
    """
    parsed = urllib.parse.urlparse(next_href)
    if parsed.netloc and parsed.netloc != urllib.parse.urlparse(base).netloc:
        msg = f"pagination cursor pointed off-host: {parsed.netloc}"
        raise ApiError(msg)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


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
    """Call api-v2 at `path`, which the in-page JS appends to the host with bare string
    concatenation — so a path that does not open with exactly one '/' does not land on
    api-v2 at all; it changes the host the OAuth cookie is sent to (e.g. ".evil.com/x" or
    "//evil.com/x"). Every caller's path is a literal or comes from same_host_path, which
    already refuses an off-host next_href, but this is the one place that would catch a
    caller either missed.
    """
    if not path.startswith("/") or path.startswith("//"):
        msg = f"api-v2 path must start with a single '/': {path!r}"
        raise ApiError(msg)
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


# SoundCloud's own ids are alphanumeric, dash and underscore. This is also what stands
# between a client_id read off some unrelated request and a raw value with an unescaped
# character going straight into a query string.
_CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_CLIENT_ID_TIMEOUT_SECONDS = 15

# Read once per process and reused for the rest of the run. A rotation between runs is
# fine — this only has to be right for the run it was read in.
_web_client_id_cache: str | None = None


def invalidate_client_id() -> None:
    """Forget the cached client_id, so the next call re-reads it from a live page.

    For a 401/403 on a read that used to work — the client_id can go stale mid-run, and
    without this every later read fails the same way instead of just re-collecting it.
    """
    global _web_client_id_cache  # noqa: PLW0603
    _web_client_id_cache = None


async def web_client_id(page: Page) -> str:
    """The web app's own client_id, taken from a request it makes — never guessed.

    api-v2 answers a GET with no client_id "missing params" (400), and there is no
    endpoint that hands one out; the only place it exists is a request the web app
    already made. The listener is attached before the navigation expected to carry it,
    so the first load yields it and nothing needs a second round trip. A page already on
    soundcloud.com is reloaded instead, since ensure_on_soundcloud would otherwise
    navigate nowhere and no new request would fire.
    """
    global _web_client_id_cache  # noqa: PLW0603
    if _web_client_id_cache is not None:
        return _web_client_id_cache

    found: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    def on_request(request: Any) -> None:  # noqa: ANN401
        if found.done():
            return
        # A substring check on the whole URL would also match a third-party request that
        # merely mentions api-v2.soundcloud.com in a query string — the actual host, and
        # the query parameter, have to be parsed out rather than pattern-matched raw.
        parsed = urllib.parse.urlsplit(request.url)
        if parsed.hostname != "api-v2.soundcloud.com":
            return
        candidates = urllib.parse.parse_qs(parsed.query).get("client_id") or []
        if candidates and _CLIENT_ID_PATTERN.match(candidates[0]):
            found.set_result(candidates[0])

    page.on("request", on_request)
    try:
        if "soundcloud.com" in (page.url or ""):
            await page.reload(wait_until="domcontentloaded", timeout=40_000)
        else:
            await ensure_on_soundcloud(page)
        client_id = await asyncio.wait_for(found, timeout=_CLIENT_ID_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        msg = "no client_id seen among api-v2 requests after loading soundcloud.com"
        raise ApiError(msg) from exc
    finally:
        page.remove_listener("request", on_request)

    _web_client_id_cache = client_id
    return client_id


async def resolve_v2(page: Page, url: str, client_id: str) -> dict[str, Any]:
    """Turn a soundcloud.com permalink into its resource, from the page's own session.

    Comment clean-up has to work with no stored user token: a gate can post a comment
    through the page alone, before --sc-auth has ever been run. This is the web app's own
    /resolve call, the same one resolve() makes through the token API instead.
    """
    query = urllib.parse.urlencode({"url": url, "client_id": client_id})
    status, body = await _api_v2(page, "GET", f"/resolve?{query}")
    if status != _HTTP_OK:
        msg = f"api-v2 resolve({url}) returned {status}: {body[:120]}"
        raise ApiError(msg)
    return json.loads(body)


@dataclass(frozen=True)
class MyComment:
    """One comment this account left on a track, from the web (api-v2) read."""

    id: int
    created_at: str
    body: str


async def my_comments_v2(
    page: Page, track_id: int, user_id: int, client_id: str
) -> list[MyComment]:
    """Every comment this account left on a track, read fresh through the page's session.

    api.soundcloud.com's own collection can go 40s+ without showing a comment that was
    just posted or just deleted (see the module docstring) — long enough that a rerun
    reads it as missing and posts a duplicate. The web API this drives is what
    soundcloud.com itself trusts, and does not have that lag.
    """
    query = urllib.parse.urlencode(
        {
            "threaded": 1,
            "filter_replies": 0,
            "sort": "newest",
            "client_id": client_id,
            "limit": _COMMENT_PAGE_SIZE,
            "offset": 0,
            "linked_partitioning": 1,
        }
    )
    path = f"/tracks/{track_id}/comments?{query}"
    found: list[MyComment] = []
    for _ in range(_MAX_COMMENT_PAGES):
        status, body_text = await _api_v2(page, "GET", path)
        if status != _HTTP_OK:
            msg = f"api-v2 GET {path} returned {status}: {body_text[:120]}"
            raise ApiError(msg)
        body = json.loads(body_text)
        for item in body.get("collection", []):
            uid = (item.get("user") or {}).get("id", item.get("user_id"))
            if uid == user_id:
                found.append(
                    MyComment(
                        id=int(item["id"]),
                        created_at=str(item.get("created_at", "")),
                        body=str(item.get("body", "")),
                    )
                )
        next_href = body.get("next_href")
        if not next_href:
            return found
        path = same_host_path(next_href, base=API_V2)

    # Running out of pages is not "no comments found": that reading is what leaves a
    # duplicate the clean-up never sees, and posts another one from _comment_once.
    msg = f"comments on track {track_id} did not end within {_MAX_COMMENT_PAGES} pages"
    raise ApiError(msg)


async def delete_comment_v2(page: Page, comment_id: int) -> tuple[bool, str]:
    """DELETE a comment via api-v2. A 404 means it is already gone — also a success here."""
    return await _write_v2(page, "DELETE", f"/comments/{comment_id}")


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


async def fetch_download(
    track: dict[str, Any], dest_dir: Path, track_title: str | None = None
) -> Path | None:
    """Take a track's own free download straight from the API.

    No page involved, which is the point: SoundCloud's track page renders nothing when
    its SPA throws ("AF is not defined"), and the download is then invisible to any
    amount of scraping while the API keeps answering. Returns None when the track has no
    download to give.
    """
    from soundcloud_dl.downloads import (  # noqa: PLC0415
        audio_extension_for,
        discard_if_fragment,
        rename_to_track,
        save_bytes,
    )

    if track.get("downloadable") is not True:
        return None
    url = track.get("download_url")
    if not isinstance(url, str) or not url:
        logger.info("Track says downloadable but gives no download_url")
        return None

    async with api_client() as client:
        resp = await client.get(url)
        if resp.status_code != HTTPStatus.OK:
            # 401/403 here means the grant does not cover downloads; 404 means the artist
            # withdrew it between the playlist read and now. Neither is fatal to the run.
            logger.warning("Download refused (%d) for %s", resp.status_code, url)
            return None
        body = resp.content
        name = _filename_from(resp.headers.get("content-disposition"), track)

    # The endpoint serves the original upload and does not reliably name it; a wav saved
    # as .mp3 is wrong everywhere downstream.
    if not Path(name).suffix:
        name += audio_extension_for(body)

    saved = discard_if_fragment(save_bytes(dest_dir / name, body), url)
    if saved is None:
        return None
    final = rename_to_track(saved, track_title)
    logger.info("Native API download saved: %s", final)
    return final


def _filename_from(content_disposition: str | None, track: dict[str, Any]) -> str:
    """Prefer the name SoundCloud sends, because it carries the real extension.

    A track's original upload can be wav, aiff or flac and the API does not say which
    anywhere else; guessing mp3 mislabels the file for every tool downstream.
    """
    if content_disposition:
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition)
        if m:
            return m.group(1).strip()
    title = track.get("title") or "track"
    safe = re.sub(r'[/\\:*?"<>|]', "_", str(title))[:120]
    return f"{safe}.mp3"
