"""Deciding whether a network response is the track, and putting it on disk."""

from __future__ import annotations

import logging
import re
import unicodedata
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

# A gate page embeds the SoundCloud player, and that player streams while the gate is
# being worked through. Its HLS segments are served as audio/mp4, so the content-type
# test below says yes to them — one was saved as a 197K .m4s, reported as a success and
# recorded done, which is worse than failing because the track is then never retried.
# A segment is never the file a gate hands over: those arrive whole.
#
# Extensions alone cannot close this. The same segments also arrive as .mp4 and with no
# extension at all, and an extensionless name is handed .mp3 downstream — so the list
# below is the cheap first pass and is_whole_track() is what actually decides.
_STREAM_EXTS = (".m4s", ".ts", ".m3u8", ".mpd")

_REJECT_EXTS = _ASSET_EXTS + _STREAM_EXTS

#: Smallest payload worth treating as a track. A SoundCloud HLS segment is a few hundred
#: KB; the shortest plausible gated track is several MB. Sitting between the two costs a
#: run nothing when it is wrong — the gate reports no download and the track is retried —
#: whereas accepting a fragment records done and retires the track for good.
MIN_TRACK_BYTES = 1_000_000

#: Partial Content. A fragment by definition, whatever it carries.
_HTTP_PARTIAL = 206


def looks_like_audio(
    url: str,
    content_type: str | None,
    content_disposition: str | None,
    status: int | None = None,
) -> bool:
    """True when a response is plausibly the downloaded track."""
    if status == _HTTP_PARTIAL:
        return False
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(_REJECT_EXTS):
        return False
    if path.endswith(_AUDIO_EXTS):
        return True
    ct = (content_type or "").lower()
    cd = (content_disposition or "").lower()
    return "audio" in ct or "octet-stream" in ct or "force-download" in ct or "attachment" in cd


def is_whole_track(url: str, size: int) -> bool:
    """True when a payload is plausibly an entire track rather than one piece of one.

    Everything looks_like_audio can see is chosen by the far end, and an HLS segment
    satisfies all of it: real audio, typed audio/mp4, served from a CDN, extension
    whatever that CDN picked this week. Length is the one signal it cannot dress up.
    """
    if size >= MIN_TRACK_BYTES:
        return True
    logger.warning(
        "Ignoring a %d-byte response — too small to be the track, probably a stream "
        "segment from the player embedded in the gate page: %s",
        size,
        url,
    )
    return False


def looks_like_asset(name: str) -> bool:
    """True for a filename or URL that is site furniture rather than the track.

    The negative half of looks_like_audio, for a Playwright Download: that carries no
    content type, and its URL often has no extension at all (ToneDen serves the file from
    an extensionless /<id> path), so requiring positive proof of audio rejects real tracks.
    """
    return urllib.parse.urlparse(name).path.lower().endswith(_REJECT_EXTS)


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


# Braces as well as brackets: "{FREE DOWNLOAD}" is common enough in track titles that
# leaving it out put the tag straight into a filename.
_FREE_DL_RE = re.compile(r"\s*[\(\[{]\s*free\s*(download|dl)?\s*[\)\]}]", re.IGNORECASE)

# The same tag written as a trailing segment rather than a bracketed one, which is how
# "Iiidiot - FREE DOWNLOAD (link in description)" reached a filename intact. "download" or
# "dl" is required here, unlike the bracketed form: a bare trailing "- Free" is more likely
# to be part of a title than a tag, and dropping it would be unrecoverable.
_TRAILING_FREE_DL_RE = re.compile(
    # The en and em dashes are meant: uploaders separate with those as often as with a
    # plain hyphen, and a tag after one would otherwise survive into the filename.
    r"\s*[-–—]\s*free\s*(download|dl)\b[^)\]]*(\([^)]*\)|\[[^\]]*\])?\s*$",  # noqa: RUF001
    re.IGNORECASE,
)

# Trailing decoration an uploader adds to make a name stand out in a feed — "###", "~~~".
# Trailing only, and deliberately not "." or "-": "DEVOWR." is how that artist spells it,
# and a leading dash is _usable_filename's to deal with.
_EDGE_DECORATION_RE = re.compile(r"[\s~#*|]+$")

_UNSAFE_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')

# macOS NAME_MAX is 255 bytes; the rest is headroom for the extension and any suffix a
# caller adds after this.
_MAX_NAME_BYTES = 200


def tidy_title_part(text: str) -> str:
    """One artist or title as it should appear in a filename.

    NFKC first, because uploaders write their name in styled Unicode to stand out — the
    mathematical-bold "STPTBOOTS" is seven codepoints no other tool here matches against,
    and it sorts nowhere near the plain spelling.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _FREE_DL_RE.sub("", text)
    text = _TRAILING_FREE_DL_RE.sub("", text)
    text = _UNSAFE_CHARS_RE.sub("", text)
    return _EDGE_DECORATION_RE.sub("", text).strip()


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
    clean = tidy_title_part(title)
    if not clean:
        return None
    safe_artist = tidy_title_part(artist or "")
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


def discard_if_fragment(dest: Path, url: str) -> Path | None:
    """Keep a just-saved file only if it is big enough to be the track.

    For the Playwright-download paths, where the size is not known until the file is on
    disk. Returns None once the fragment has been removed, so the caller reports no
    download and the track stays retryable.
    """
    try:
        size = dest.stat().st_size
    except OSError:
        logger.warning("Could not size %s — keeping it", dest, exc_info=True)
        return dest
    if is_whole_track(url, size):
        return dest
    dest.unlink(missing_ok=True)
    return None


#: Leading bytes that identify an audio container, longest-prefix first where they overlap.
#: SoundCloud's download endpoint serves the artist's original upload and does not always
#: name it, so the extension has to come from the bytes. Guessing mp3 for a wav mislabels
#: the file for every tool downstream, including this repo's own renamer.
_MAGIC: tuple[tuple[bytes, int, str], ...] = (
    (b"fLaC", 0, ".flac"),
    (b"OggS", 0, ".ogg"),
    (b"ID3", 0, ".mp3"),
    (b"ftyp", 4, ".m4a"),
    (b"WAVE", 8, ".wav"),
    (b"AIFF", 8, ".aiff"),
    (b"AIFC", 8, ".aiff"),
)


#: An MPEG audio frame starts with eleven set bits. Matching it catches an mp3 that
#: carries no ID3 tag, which is common once a file has been through a tag stripper.
_MPEG_SYNC_BYTE = 0xFF
_MPEG_SYNC_MASK = 0xE0


def audio_extension_for(body: bytes, fallback: str = ".mp3") -> str:
    """Name the container from its own bytes rather than from a header or a guess."""
    for magic, offset, ext in _MAGIC:
        if body[offset : offset + len(magic)] == magic:
            return ext
    if (
        len(body) >= 2  # noqa: PLR2004
        and body[0] == _MPEG_SYNC_BYTE
        and (body[1] & _MPEG_SYNC_MASK) == _MPEG_SYNC_MASK
    ):
        return ".mp3"
    return fallback
