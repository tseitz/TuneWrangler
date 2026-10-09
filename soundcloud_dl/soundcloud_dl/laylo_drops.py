"""Laylo drops: the per-drop progress store, fetching the sent link, matching a track in it.

The store is what keeps a second track on the same drop, or a rerun after a failure, from
RSVPing again. No browser and no Gmail here: the handler and gmail_inbox hand results in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import posixpath
import shutil
import tempfile
import time
import urllib.parse
import zipfile
from dataclasses import asdict, dataclass, fields
from email.message import Message
from pathlib import Path
from typing import IO, Any, cast

import httpx

from soundcloud_dl import config, downloads
from soundcloud_dl.downloads import _AUDIO_EXTS, _same_name, audio_extension_for

logger = logging.getLogger("soundcloud_dl.laylo_drops")

_ZIP_MAGIC = b"PK"
_HEAD_BYTES = 16
_DROPBOX_HOSTS = ("dropbox.com", "www.dropbox.com")
_DROPBOX_SHARED_PREFIXES = ("/scl/fo/", "/scl/fi/")
_DROPBOX_CDN_SUFFIX = ".dropboxusercontent.com"
_MAX_REDIRECTS = 5
_MAX_DOWNLOAD_BYTES = 2 * 1024**3
_MAX_ZIP_MEMBERS = 500
_MAX_ZIP_TOTAL_BYTES = 4 * 1024**3
_MAX_ZIP_RATIO = 200
_COPY_CHUNK = 1024 * 1024
_STALE_SECONDS = 3600
_FETCH_TIMEOUT = httpx.Timeout(30.0)
_LAYLO_SUBDIR = "laylo"
_SAFE_SLUG_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_.")


class LayloFetchError(Exception):
    """The link did not yield a usable zip or audio file. Nothing was cached."""


class LayloDropStoreError(Exception):
    """The drop store exists but cannot be read."""


@dataclass
class DropRecord:
    """How far one drop has got. Epoch seconds for the two timestamps."""

    submitted_at: float | None = None
    link: str | None = None
    gmail_id: str | None = None
    #: The text's body, or the email's subject: what the link was taken from.
    message: str | None = None
    folder: str | None = None
    fetched_at: float | None = None
    sender: str | None = None
    #: "email" or "sms": which inbox the drop's link arrives in. None reads as "sms".
    channel: str | None = None


def drop_key(url: str) -> str:
    """Lowercase host and path, without scheme, "www.", query, fragment or a trailing slash.

    Two tracks that link the same drop differ in tracking params and in how the uploader
    capitalised the artist, and each of those must land on the one record.
    """
    parsed = urllib.parse.urlparse(url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lower().rstrip("/")
    return f"{host}{path}"


# ── Drop store ─────────────────────────────────────────────────────────────────


def _read_all() -> dict[str, dict[str, object]]:
    path = config.get_laylo_drops_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Starting over would forget which drops already had the number submitted, and the
        # next run would RSVP to every one of them again. Stop until a person looks.
        msg = f"{path} is not valid JSON ({exc}); fix or remove it by hand"
        raise LayloDropStoreError(msg) from exc
    if not isinstance(data, dict):
        msg = f"{path} does not hold a JSON object; fix or remove it by hand"
        raise LayloDropStoreError(msg)
    return data


def _write_all(data: dict[str, dict[str, object]]) -> None:
    path = config.get_laylo_drops_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _to_record(raw: object) -> DropRecord:
    stored = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    return DropRecord(**{f.name: stored.get(f.name) for f in fields(DropRecord)})


def load(key: str) -> DropRecord | None:
    raw = _read_all().get(key)
    return None if raw is None else _to_record(raw)


def save(key: str, record: DropRecord) -> None:
    data = _read_all()
    data[key] = asdict(record)
    _write_all(data)


def forget(key: str) -> bool:
    """Drop one record. True when there was one."""
    data = _read_all()
    if key not in data:
        return False
    del data[key]
    _write_all(data)
    return True


def used_gmail_ids() -> set[str]:
    """Every Gmail message already claimed by a drop, so two drops never take the same text."""
    return {
        record.gmail_id
        for record in (_to_record(raw) for raw in _read_all().values())
        if record.gmail_id
    }


def known_senders() -> set[str]:
    """Every texting number (digits only) a drop has been received from."""
    return {
        record.sender
        for record in (_to_record(raw) for raw in _read_all().values())
        if record.sender
    }


# ── Where files go ─────────────────────────────────────────────────────────────


def _candidate_dirs() -> list[Path]:
    primary = [config.DOWNLOAD_DIR] if config.DOWNLOAD_DIR is not None else []
    return [*primary, downloads.fallback_dir()]


def save_dir() -> Path:
    """The folder a track is saved into: the download dir, or the logs/ fallback.

    The fallback applies when the download dir is unset or cannot be created, as with an
    unplugged drive — the same place save_bytes falls back to.
    """
    return _first_usable(_candidate_dirs())


def _first_usable(candidates: list[Path], subdir: str = "") -> Path:
    last: OSError | None = None
    for base in candidates:
        target = base / subdir if subdir else base
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            last = exc
            logger.warning("Could not use %s (%s) — trying the next location", target, exc)
            continue
        return target
    msg = f"no writable save location (last error: {last})"
    raise OSError(msg)


# ── Dropbox ────────────────────────────────────────────────────────────────────


def dropbox_direct(url: str) -> str | None:
    """A shared-folder or shared-file link with dl=1, so it serves the bytes not a page.

    None for anything else, including older /s/ links and other hosts. The rlkey and every
    other query param are kept: Dropbox refuses the download without them.
    """
    parsed = urllib.parse.urlparse(url.strip())
    try:
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or port is not None:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if (parsed.hostname or "").lower() not in _DROPBOX_HOSTS:
        return None
    if not _safe_shared_path(parsed.path):
        return None
    params = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)]
    if any(k == "dl" for k, _ in params):
        params = [(k, "1" if k == "dl" else v) for k, v in params]
    else:
        params.append(("dl", "1"))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))


def _safe_shared_path(path: str) -> bool:
    # A "/scl/fo/../../l/abc" path passes the prefix check but names a different Dropbox page
    # once the server normalises it, so any dot segment or encoded dot is refused outright.
    decoded = urllib.parse.unquote(path)
    if "%2e" in path.lower() or ".." in decoded.split("/"):
        return False
    if posixpath.normpath(decoded) != decoded:
        return False
    return path.startswith(_DROPBOX_SHARED_PREFIXES)


def _allowed_download_host(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host in _DROPBOX_HOSTS or host.endswith(_DROPBOX_CDN_SUFFIX)
    )


def _sweep_debris(root: Path, *, now: float | None = None) -> None:
    """Delete .part files and hidden staging folders left by a run that was killed."""
    cutoff = (time.time() if now is None else now) - _STALE_SECONDS
    tmp_dir = config.get_laylo_tmp_dir()
    stale: list[Path] = []
    try:
        for candidate in (*tmp_dir.glob("*.part"), *root.glob(".*")):
            is_part = candidate.suffix == ".part" and candidate.parent == tmp_dir
            if (is_part or candidate.is_dir()) and candidate.stat().st_mtime < cutoff:
                stale.append(candidate)
    except OSError as exc:
        logger.warning("Could not scan for stale Laylo debris (%s)", exc)
    for path in stale:
        logger.info("Removing stale Laylo debris %s", path)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _safe_slug(slug: str) -> str:
    cleaned = "".join(c if c.lower() in _SAFE_SLUG_CHARS else "-" for c in slug.strip())
    cleaned = cleaned.strip(".-")
    if not cleaned:
        msg = f"unusable folder name from {slug!r}"
        raise LayloFetchError(msg)
    return cleaned


def _filename_from_disposition(header: str | None) -> str | None:
    if not header:
        return None
    msg = Message()
    msg["content-disposition"] = header
    name = msg.get_filename()
    if not name:
        return None
    name = Path(name.replace("\\", "/")).name
    return name if name.lower().endswith(_AUDIO_EXTS) else None


async def fetch(link: str, slug: str, *, client: httpx.AsyncClient | None = None) -> Path:
    """Download a Dropbox link and unpack it to <save dir>/laylo/<slug>/. Returns that folder.

    Raises LayloFetchError for a link that is not Dropbox, an error status, or a body that is
    neither a zip nor audio (Dropbox answers "too large", "expired" and "traffic limited" with
    a 200 HTML page). The destination only appears once everything has been extracted, so a
    failure leaves nothing behind to be mistaken for a fetched folder.
    """
    direct = dropbox_direct(link)
    if direct is None:
        msg = "not a Dropbox shared folder or file link"
        raise LayloFetchError(msg)
    name = _safe_slug(slug)
    root = _first_usable(_candidate_dirs(), _LAYLO_SUBDIR)
    dest = root / name
    _sweep_debris(root)
    if dest.exists():
        logger.info("Laylo folder %s already exists — reusing it", dest)
        return dest
    if client is None:
        async with httpx.AsyncClient(follow_redirects=False, timeout=_FETCH_TIMEOUT) as own:
            return await _fetch(direct, name, root, dest, own)
    return await _fetch(direct, name, root, dest, client)


def _open_part(name: str) -> tuple[IO[bytes], Path]:
    tmp_dir = config.get_laylo_tmp_dir()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=tmp_dir, prefix=f"{name}-", suffix=".part")
    return os.fdopen(fd, "wb"), Path(tmp_name)


def _discard(part: Path, staging: Path | None) -> None:
    part.unlink(missing_ok=True)
    if staging is not None:
        shutil.rmtree(staging, ignore_errors=True)


async def _fetch(direct: str, name: str, root: Path, dest: Path, client: httpx.AsyncClient) -> Path:
    handle, part = _open_part(name)
    staging: Path | None = None
    try:
        with handle:
            kind, head, disposition = await _download(client, direct, handle)
        staging = Path(tempfile.mkdtemp(dir=root, prefix=f".{name}-"))
        if kind == "zip":
            await asyncio.to_thread(_extract_zip, part, staging)
        else:
            audio_name = _filename_from_disposition(disposition) or (
                f"{name}{audio_extension_for(head)}"
            )
            await asyncio.to_thread(shutil.move, str(part), str(staging / audio_name))
        staging.chmod(0o755)
        staging.rename(dest)
        staging = None
    finally:
        _discard(part, staging)
    return dest


async def _download(
    client: httpx.AsyncClient, url: str, handle: IO[bytes]
) -> tuple[str, bytes, str | None]:
    """Stream the body into handle. Returns (kind, leading bytes, Content-Disposition).

    Redirects are followed here rather than by httpx so each hop can be checked against the
    Dropbox host allowlist before a request goes out.
    """
    try:
        for _ in range(_MAX_REDIRECTS + 1):
            async with client.stream("GET", url, follow_redirects=False) as resp:
                if resp.is_redirect:
                    url = _next_hop(url, resp)
                    continue
                return await _read_body(resp, handle)
    except httpx.HTTPError as exc:
        msg = f"request failed: {exc!r}"
        raise LayloFetchError(msg) from exc
    msg = f"more than {_MAX_REDIRECTS} redirects"
    raise LayloFetchError(msg)


def _next_hop(current: str, resp: httpx.Response) -> str:
    location = resp.headers.get("location", "")
    target = urllib.parse.urljoin(current, location)
    if not _allowed_download_host(target):
        parsed = urllib.parse.urlparse(target)
        msg = f"redirect to a host that is not Dropbox: {parsed.hostname!r}"
        raise LayloFetchError(msg)
    return target


async def _read_body(resp: httpx.Response, handle: IO[bytes]) -> tuple[str, bytes, str | None]:
    if resp.status_code != httpx.codes.OK:
        msg = f"Dropbox answered HTTP {resp.status_code}"
        raise LayloFetchError(msg)
    if not _allowed_download_host(str(resp.url)):
        msg = f"response came from a host that is not Dropbox: {resp.url.host!r}"
        raise LayloFetchError(msg)
    declared = resp.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > _MAX_DOWNLOAD_BYTES:
        msg = f"download declares {declared} bytes, over the {_MAX_DOWNLOAD_BYTES} byte cap"
        raise LayloFetchError(msg)
    kind: str | None = None
    head = b""
    received = 0
    content_type = resp.headers.get("content-type", "").lower()
    async for chunk in resp.aiter_bytes():
        received += len(chunk)
        if received > _MAX_DOWNLOAD_BYTES:
            msg = f"download passed the {_MAX_DOWNLOAD_BYTES} byte cap"
            raise LayloFetchError(msg)
        if len(head) < _HEAD_BYTES:
            head += chunk[: _HEAD_BYTES - len(head)]
        if kind is None and len(head) >= len(_ZIP_MAGIC):
            kind = _classify(head, content_type)
        await asyncio.to_thread(handle.write, chunk)
    if kind is None:
        msg = "empty response body"
        raise LayloFetchError(msg)
    # A compressed body is decoded on the way in, so its length no longer matches the
    # header; a truncated one fails decoding instead.
    if (
        declared is not None
        and declared.isdigit()
        and "content-encoding" not in resp.headers
        and int(declared) != received
    ):
        msg = f"truncated: got {received} of {declared} bytes"
        raise LayloFetchError(msg)
    return kind, head, resp.headers.get("content-disposition")


def _classify(head: bytes, content_type: str) -> str:
    if head.startswith(_ZIP_MAGIC):
        return "zip"
    # Dropbox serves a shared file as application/octet-stream, so the bytes decide too.
    if "audio/" in content_type or audio_extension_for(head, fallback=""):
        return "audio"
    msg = f"body is neither a zip nor audio (content-type {content_type or 'missing'})"
    raise LayloFetchError(msg)


def _check_zip_limits(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > _MAX_ZIP_MEMBERS:
        msg = f"the zip has {len(infos)} members, over the {_MAX_ZIP_MEMBERS} cap"
        raise LayloFetchError(msg)
    if sum(i.file_size for i in infos) > _MAX_ZIP_TOTAL_BYTES:
        msg = f"the zip unpacks past the {_MAX_ZIP_TOTAL_BYTES} byte cap"
        raise LayloFetchError(msg)
    for info in infos:
        if info.file_size / max(info.compress_size, 1) > _MAX_ZIP_RATIO:
            msg = f"zip member {info.filename!r} compresses past {_MAX_ZIP_RATIO}:1"
            raise LayloFetchError(msg)


def _copy_capped(src: IO[bytes], out: IO[bytes], total: int) -> int:
    """Copy src to out, returning the new running total across the whole archive."""
    while chunk := src.read(_COPY_CHUNK):
        total += len(chunk)
        if total > _MAX_ZIP_TOTAL_BYTES:
            msg = f"the zip unpacked past the {_MAX_ZIP_TOTAL_BYTES} byte cap"
            raise LayloFetchError(msg)
        out.write(chunk)
    return total


def _extract_zip(zip_path: Path, staging: Path) -> None:
    """Unpack into staging, one regular file per member, never leaving staging.

    Members are written by hand instead of with extractall so that a name like "../x" or an
    absolute path is checked against the resolved target before anything is opened, and so
    that a symlink member is written as the plain file it would otherwise have become.
    """
    base = staging.resolve()
    written = 0
    total = 0
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        msg = "body starts like a zip but is not a readable archive"
        raise LayloFetchError(msg) from exc
    with archive:
        infos = archive.infolist()
        _check_zip_limits(infos)
        for info in infos:
            parts = Path(info.filename).parts
            if info.is_dir() or "__MACOSX" in parts:
                continue
            target: Path | None = None
            try:
                target = (base / info.filename).resolve()
                if not target.is_relative_to(base) or target == base:
                    logger.warning("Skipping zip member outside the folder: %r", info.filename)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target.open("xb") as out:
                    total = _copy_capped(src, out, total)
            except FileExistsError:
                logger.warning("Skipping duplicate zip member: %r", info.filename)
                continue
            except (ValueError, OSError) as exc:
                logger.warning("Skipping unwritable zip member %r (%s)", info.filename, exc)
                if target is not None:
                    _unlink_quietly(target)
                continue
            written += 1
    if written == 0:
        msg = "the zip held no files"
        raise LayloFetchError(msg)


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except (ValueError, OSError) as exc:
        logger.warning("Could not remove partial file %s (%s)", path, exc)


# ── Matching ───────────────────────────────────────────────────────────────────


def match_track(folder: Path, track_title: str) -> Path | None:
    """The one audio file in folder that is this track, or None for no match or several.

    A drop names its files "<artist> - <title>" while the track title may carry only the
    title, or the artist and title, so both spellings are tried. Ambiguity is None on purpose:
    copying the wrong flip into the Collection is worse than asking a person.
    """
    after_dash = track_title.split(" - ", 1)[1] if " - " in track_title else None
    hits = [
        path
        for path in folder.rglob("*")
        if path.is_file()
        and path.suffix.lower() in _AUDIO_EXTS
        and not path.name.startswith("._")
        and (
            _same_name(path.stem, track_title)
            or (after_dash is not None and _same_name(path.stem, after_dash))
        )
    ]
    return hits[0] if len(hits) == 1 else None


def place_match(src: Path, dest_dir: Path, track_title: str) -> Path | None:
    """Copy src to <dest_dir>/<track_title><ext>. None when that name is already taken.

    Exclusive-create rather than an exists() check, so a file that appears between the check
    and the write is still not overwritten.
    """
    name = f"{track_title}{src.suffix}"
    if Path(name).name != name:
        msg = f"track title is not a plain filename: {track_title!r}"
        raise ValueError(msg)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    try:
        writer = dest.open("xb")
    except FileExistsError:
        return None
    except (ValueError, OSError) as exc:
        logger.warning("Track title is not usable as a filename (%s): %r", exc, track_title)
        return None
    try:
        with src.open("rb") as reader, writer:
            shutil.copyfileobj(reader, writer)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return dest


__all__ = [
    "DropRecord",
    "LayloDropStoreError",
    "LayloFetchError",
    "drop_key",
    "dropbox_direct",
    "fetch",
    "forget",
    "known_senders",
    "load",
    "match_track",
    "place_match",
    "save",
    "save_dir",
    "used_gmail_ids",
]
