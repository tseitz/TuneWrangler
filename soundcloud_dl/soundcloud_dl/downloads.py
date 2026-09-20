"""Deciding whether a network response is the track, and putting it on disk."""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import TYPE_CHECKING, Any

from soundcloud_dl.config import get_log_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("soundcloud_dl.downloads")

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
    """Write content to dest, falling back to the log directory if that path is unusable.

    By this point the audio is already in memory and the gate has been consumed — a track
    cannot be downloaded twice. Losing it to an unwritable destination (a Google Drive mount
    that refuses mkdir, a disconnected volume) is worse than putting it somewhere else and
    saying so.
    """
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    except OSError as exc:
        fallback = get_log_dir() / "downloads" / dest.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_bytes(content)
        logger.warning("Could not write to %s (%s) — saved to %s instead", dest, exc, fallback)
        return fallback
    return dest


_FREE_DL_RE = re.compile(r"\s*[\(\[]\s*free\s*(download|dl)?\s*[\)\]]", re.IGNORECASE)
_UNSAFE_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')

# macOS NAME_MAX is 255 bytes; the rest is headroom for the extension and any suffix a
# caller adds after this.
_MAX_NAME_BYTES = 200


def _same_name(a: str, b: str) -> bool:
    """Whether two names are the same once case and punctuation stop mattering.

    "DEVOWR." off the API and "DEVOWR" typed into a title are one artist.
    """
    squashed = [re.sub(r"[^a-z0-9]", "", name.lower()) for name in (a, b)]
    return squashed[0] == squashed[1] and squashed[0] != ""


def track_filename(title: str | None, artist: str | None) -> str | None:
    """ "<artist> - <title>" with download noise and path-unsafe characters removed.

    One definition because both the playlist pipeline and the --jev pilot name files, and
    a second copy would drift into two naming schemes in one download folder.

    The artist is skipped only when the title already *starts with that artist*. Treating
    any " - " as an artist separator left "Smack My B  Up - (Lowshade Flip)" with no artist
    at all, because the dash belonged to the title.
    """
    if not title:
        return None
    clean = _UNSAFE_CHARS_RE.sub("", _FREE_DL_RE.sub("", title)).strip()
    if not clean:
        return None
    safe_artist = _UNSAFE_CHARS_RE.sub("", artist or "").strip()
    if safe_artist and not _same_name(clean.split(" - ", 1)[0], safe_artist):
        clean = f"{safe_artist} - {clean}"
    return _usable_filename(clean)


def _usable_filename(name: str) -> str | None:
    """A name the filesystem will accept, or None if nothing usable is left.

    Three separate traps, all reached from an upload title we do not control:

    - Over NAME_MAX the rename raises ENAMETOOLONG, and by then the gate has been spent on
      a follow, a like, a repost and a comment that a re-run does not get back. Measured in
      bytes, not characters, because an emoji costs four of them.
    - "." and ".." name a directory rather than a file.
    - A leading "-" reads as a flag to anything downstream that shells out without "--",
      and these files are handed to ffmpeg and the Deno side afterwards.
    """
    name = name.lstrip("-").strip()
    if not name.strip("."):
        return None
    encoded = name.encode("utf-8")
    if len(encoded) > _MAX_NAME_BYTES:
        name = encoded[:_MAX_NAME_BYTES].decode("utf-8", errors="ignore").strip()
    return name or None


def rename_to_track(dest: Path, track_title: str | None) -> Path:
    """Rename a saved file to the track title, keeping its extension."""
    if not track_title:
        return dest
    renamed = dest.parent / f"{track_title}{dest.suffix}"
    dest.rename(renamed)
    return renamed


async def save_download(download: Any, dest: Path) -> Path:  # noqa: ANN401
    """Save a Playwright download, falling back to the log directory if dest is unusable."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(dest))
    except OSError as exc:
        fallback = get_log_dir() / "downloads" / dest.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(fallback))
        logger.warning("Could not write to %s (%s) — saved to %s instead", dest, exc, fallback)
        return fallback
    return dest
