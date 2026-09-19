"""Deciding whether a network response is the track, and putting it on disk."""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_AUDIO_EXTS = (".mp3", ".wav", ".flac", ".aiff", ".aif", ".aac", ".ogg", ".m4a")

# Gates serve music as octet-stream or force-download, but so do webfonts, and an
# unfiltered match once saved fontawesome-webfont.woff2 as the track. Extension wins
# over content type for anything on this list.
_ASSET_EXTS = (
    ".woff2",
    ".woff",
    ".ttf",
    ".otf",
    ".eot",
    ".css",
    ".js",
    ".json",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".html",
)


def looks_like_audio(url: str, content_type: str | None, content_disposition: str | None) -> bool:
    """True when a response is plausibly the downloaded track."""
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(_ASSET_EXTS):
        return False
    if path.endswith(_AUDIO_EXTS):
        return True
    ct = (content_type or "").lower()
    cd = (content_disposition or "").lower()
    return "audio" in ct or "octet-stream" in ct or "force-download" in ct or "attachment" in cd


def save_bytes(dest: Path, content: bytes) -> Path:
    """Write content to dest, creating the download directory if it does not exist."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest


def rename_to_track(dest: Path, track_title: str | None) -> Path:
    """Rename a saved file to the track title, keeping its extension."""
    if not track_title:
        return dest
    renamed = dest.parent / f"{track_title}{dest.suffix}"
    dest.rename(renamed)
    return renamed
