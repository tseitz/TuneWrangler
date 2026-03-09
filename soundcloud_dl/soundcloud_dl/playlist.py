"""Extract track URLs from a SoundCloud playlist using the SoundCloud API."""

import base64
import logging
from dataclasses import dataclass

import httpx

from soundcloud_dl.config import SOUNDCLOUD_CLIENT_ID, SOUNDCLOUD_CLIENT_SECRET

logger = logging.getLogger("soundcloud_dl.playlist")

SOUNDCLOUD_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"  # noqa: S105
API_BASE = "https://api.soundcloud.com"
RESOLVE_URL = f"{API_BASE}/resolve"


@dataclass
class TrackItem:
    """A single track from a playlist."""

    url: str
    title: str | None = None


def _get_access_token(client_id: str, client_secret: str) -> str:
    """Obtain an access token via Client Credentials flow. Raises on failure."""
    credentials = f"{client_id}:{client_secret}"
    basic = base64.b64encode(credentials.encode()).decode()
    with httpx.Client(follow_redirects=True) as client:
        resp = client.post(
            SOUNDCLOUD_TOKEN_URL,
            headers={
                "Accept": "application/json; charset=utf-8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
            },
            data={"grant_type": "client_credentials"},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    token = data.get("access_token")
    if not token:
        msg = "Token response missing access_token"
        raise RuntimeError(msg)
    return token


def _resolve_playlist(playlist_url: str, token: str) -> dict:
    """Resolve a playlist URL to the playlist resource. Raises on failure or non-playlist."""
    with httpx.Client(follow_redirects=True) as client:
        resp = client.get(
            RESOLVE_URL,
            params={"url": playlist_url},
            headers={
                "Accept": "application/json; charset=utf-8",
                "Authorization": f"OAuth {token}",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    kind = data.get("kind")
    if kind != "playlist":
        msg = f"Resolved resource is not a playlist (kind={kind})"
        raise ValueError(msg)
    return data


def _track_to_item(track: dict) -> TrackItem | None:
    """Build TrackItem from API track object. Returns None if URL cannot be determined."""
    # Prefer permalink_url (web URL); fallback to uri or construct from permalink
    url = track.get("permalink_url")
    if not url and track.get("permalink"):
        user_permalink = track.get("user", {}).get("permalink", "")
        url = f"https://soundcloud.com/{user_permalink}/{track['permalink']}"
    if not url:
        url = track.get("uri")  # API URI, but still usable as identifier
    if not url:
        return None
    title = track.get("title")
    return TrackItem(url=url, title=title if isinstance(title, str) else None)


def _tracks_from_playlist_data(data: dict) -> list[TrackItem]:
    """Extract TrackItems from a playlist API response (has 'tracks' array)."""
    tracks: list[TrackItem] = []
    items = data.get("tracks")
    if isinstance(items, list):
        for t in items:
            if isinstance(t, dict):
                item = _track_to_item(t)
                if item:
                    tracks.append(item)
    return tracks


def _fetch_next_page(url: str, token: str) -> tuple[dict, str | None]:
    """GET a playlist page (full URL); return (json data, next_href or None)."""
    with httpx.Client(follow_redirects=True) as client:
        resp = client.get(
            url,
            headers={
                "Accept": "application/json; charset=utf-8",
                "Authorization": f"OAuth {token}",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    return data, data.get("next_href")


def extract_track_urls(playlist_url: str) -> list[TrackItem]:
    """
    Fetch playlist track URLs (and titles) from the SoundCloud API.

    Requires SOUNDCLOUD_CLIENT_ID and SOUNDCLOUD_CLIENT_SECRET in the environment.
    Uses Client Credentials flow; no browser.
    """
    client_id = SOUNDCLOUD_CLIENT_ID or ""
    client_secret = SOUNDCLOUD_CLIENT_SECRET or ""
    if not client_id or not client_secret:
        msg = "SOUNDCLOUD_CLIENT_ID and SOUNDCLOUD_CLIENT_SECRET are required"
        raise RuntimeError(msg)

    logger.info("Getting access token")
    token = _get_access_token(client_id, client_secret)
    logger.info("Resolving playlist URL: %s", playlist_url)
    playlist = _resolve_playlist(playlist_url.strip(), token)
    # Use resolved playlist body (has tracks); refetch by id 404s for URN/secret playlists
    tracks = _tracks_from_playlist_data(playlist)
    next_href = playlist.get("next_href")
    while next_href:
        logger.debug("Fetching next page: %s", next_href)
        data, next_href = _fetch_next_page(next_href, token)
        tracks.extend(_tracks_from_playlist_data(data))
    logger.info("Found %d tracks", len(tracks))
    return tracks
