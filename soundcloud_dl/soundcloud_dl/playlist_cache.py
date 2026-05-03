"""Playlist cache: persist track list per playlist URL to avoid repeated SoundCloud API calls."""

import json
import logging

from soundcloud_dl.config import get_playlist_cache_file
from soundcloud_dl.playlist import TrackItem

logger = logging.getLogger("soundcloud_dl.playlist_cache")


def _normalize_playlist_url(url: str) -> str:
    """
    Normalize playlist URL for use as cache key.

    Uses scheme + host + path only so that the same playlist matches regardless
    of query params (e.g. utm_*, si=) or trailing slash.
    """
    s = url.strip().rstrip("/")
    if "?" in s:
        s = s.split("?")[0]
    if "#" in s:
        s = s.split("#")[0]
    return s


def _item_to_track(item: object) -> TrackItem | None:
    """Parse one cache list item into TrackItem; return None if invalid."""
    if not isinstance(item, dict) or not isinstance(item.get("url"), str):
        return None
    url = (item["url"] or "").strip()
    if not url:
        return None
    title = item.get("title")
    if title is not None and not isinstance(title, str):
        title = None
    purchase_url = item.get("purchase_url")
    if purchase_url is not None and not isinstance(purchase_url, str):
        purchase_url = None
    artist = item.get("artist")
    if artist is not None and not isinstance(artist, str):
        artist = None
    return TrackItem(url=url, title=title, purchase_url=purchase_url, artist=artist)


def _get_stored_list(data: object, key: str) -> list | None:
    """Get stored list for key from cache data; support normalized key match."""
    if not isinstance(data, dict):
        return None
    stored = data.get(key)
    if isinstance(stored, list):
        return stored
    for k, v in data.items():
        if _normalize_playlist_url(k) == key and isinstance(v, list):
            return v
    return None


def load_cached_tracks(playlist_url: str) -> list[TrackItem] | None:
    """
    Load cached track list for this playlist URL, if present and valid.

    Returns None on cache miss, file error, or invalid data.
    """
    path = get_playlist_cache_file()
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not load playlist cache %s: %s", path, e)
        return None
    key = _normalize_playlist_url(playlist_url)
    stored = _get_stored_list(data, key)
    if not isinstance(stored, list):
        return None
    tracks: list[TrackItem] = []
    for item in stored:
        track = _item_to_track(item)
        if track is not None:
            tracks.append(track)
        else:
            logger.debug("Skipping invalid cache item: %s", item)
    return tracks or None


def save_cached_tracks(playlist_url: str, tracks: list[TrackItem]) -> None:
    """Save track list for this playlist URL to the cache file."""
    path = get_playlist_cache_file()
    key = _normalize_playlist_url(playlist_url)
    payload = [
        {"url": t.url, "title": t.title, "purchase_url": t.purchase_url, "artist": t.artist}
        for t in tracks
    ]
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        else:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[key] = payload
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Cached %d tracks for playlist: %s", len(tracks), key)
    except (OSError, TypeError, ValueError) as e:
        logger.warning("Could not save playlist cache %s: %s", path, e)
