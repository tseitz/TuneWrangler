"""Playlist cache: persist track list per playlist URL to avoid repeated SoundCloud API calls."""

import json
import logging
from typing import cast

from soundcloud_dl.config import get_playlist_cache_file
from soundcloud_dl.playlist import TrackItem

logger = logging.getLogger("soundcloud_dl.playlist_cache")


def _normalize_playlist_url(url: str) -> str:
    """
    Normalize playlist URL for use as cache key.

    Uses scheme + host + path only so that the same playlist matches regardless
    of query params (e.g. utm_*, si=) or trailing slash.
    """
    s = url.strip()
    if "?" in s:
        s = s.split("?")[0]
    if "#" in s:
        s = s.split("#")[0]
    # Strip trailing slash AFTER splitting query/fragment so "p/?si=x" and "p?si=x"
    # both normalize to the same key.
    return s.rstrip("/")


def _str_or_none(value: object) -> str | None:
    """Return value if it's a string, else None — used to filter optional cache fields."""
    return value if isinstance(value, str) else None


def _item_to_track(item: object) -> TrackItem | None:
    """Parse one cache list item into TrackItem; return None if invalid."""
    if not isinstance(item, dict):
        return None
    # Cast: ty narrows isinstance(item, dict) to dict[Unknown, Unknown] which rejects
    # string-literal keys; cast restores expected JSON-shape for the lookups below.
    d = cast("dict[str, object]", item)
    url_value = d.get("url")
    if not isinstance(url_value, str):
        return None
    url = url_value.strip()
    if not url:
        return None
    return TrackItem(
        url=url,
        title=_str_or_none(d.get("title")),
        purchase_url=_str_or_none(d.get("purchase_url")),
        artist=_str_or_none(d.get("artist")),
        downloadable=d.get("downloadable") is True,
        download_url=_str_or_none(d.get("download_url")),
    )


def _get_stored_list(data: object, key: str) -> list | None:
    """Get stored list for key from cache data; support normalized key match."""
    if not isinstance(data, dict):
        return None
    d = cast("dict[str, object]", data)
    stored = d.get(key)
    if isinstance(stored, list):
        return stored
    for k, v in d.items():
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
    # An entry written before downloadable/download_url existed cannot answer whether a
    # track has its own download, and absent would read as "no" — silently retiring every
    # cached track to the gate flow, or to NO_GATE. Re-read the playlist instead.
    if any(isinstance(i, dict) and "url" in i and "downloadable" not in i for i in stored):
        logger.info("Playlist cache predates the download fields — re-reading from the API")
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
        {
            "url": t.url,
            "title": t.title,
            "purchase_url": t.purchase_url,
            "artist": t.artist,
            "downloadable": t.downloadable,
            "download_url": t.download_url,
        }
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
