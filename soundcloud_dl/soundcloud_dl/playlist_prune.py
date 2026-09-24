"""--prune-playlist: take tracks off the source playlist once their files are in the Collection.

A track counts as done only with proof: a rename manifest links its SoundCloud URL to the
name it was approved under, and a file with that name is in the Collection folder. Anything
short of that stays on the playlist.

Runs as the playlist's owner (--authorize-owner), never as the bot. The API replaces a
playlist's whole track list in one call, so the list sent has to be complete: the fetch is
checked against track_count, and the full list is backed up before anything is changed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from soundcloud_dl.config import (
    TUNEWRANGLER_DJMUSIC_PATH,
    TUNEWRANGLER_SC_PLAYLIST_URL,
    get_manifest_dirs,
    get_owner_token_file,
    get_playlist_backup_dir,
)
from soundcloud_dl.soundcloud_api import ApiError, api_client, same_host_path

logger = logging.getLogger("soundcloud_dl.playlist_prune")

#: Written by the Deno rename flow (renameMusic.ts) on an entry skipped as already collected.
DUPLICATE_REASON = "duplicate of an existing track in the DJ collection"

# Above either, a run needs --allow-bulk. A nightly job never passes it, so a bug in the
# proof chain costs a handful of tracks rather than the playlist.
_BULK_COUNT = 20
_BULK_SHARE = 0.25

_PAGE_SIZE = 50
# Far past any real playlist (SoundCloud caps them at 500 tracks); stops a cursor loop.
_MAX_PAGES = 100
_VERIFY_RETRY_S = 3.0


class PruneError(RuntimeError):
    """The prune stopped before changing anything it could not stand behind."""


class UpdateUncertainError(RuntimeError):
    """The update was sent, and the playlist may or may not match what was intended."""


@dataclass(frozen=True)
class Proof:
    """Why a track is known to be in the Collection."""

    name: str
    manifest: str


@dataclass
class PrunePlan:
    """Every playlist track, sorted by what the prune will do with it."""

    remove: list[tuple[dict[str, Any], Proof]] = field(default_factory=list)
    not_in_collection: list[dict[str, Any]] = field(default_factory=list)
    duplicate_skipped: list[dict[str, Any]] = field(default_factory=list)
    unlinked: list[dict[str, Any]] = field(default_factory=list)
    #: Everything not removed, in playlist order — exactly what the update sends.
    keep: list[dict[str, Any]] = field(default_factory=list)


def normalize_url(url: str) -> str:
    return url.split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()


def _stem(name: str) -> str:
    # The extension is not part of the match: the rename converts every non-MP3 to .aiff.
    return unicodedata.normalize("NFC", Path(name).stem)


def collection_stems(path: str | None) -> set[str]:
    """Names in the Collection, without extensions. Raises if the folder cannot be read.

    An unplugged drive has to stop the run rather than read as "nothing is collected".
    """
    if not path:
        msg = "TUNEWRANGLER_DJMUSIC_PATH is not set — add it to .env"
        raise PruneError(msg)
    folder = Path(path)
    if not folder.is_dir():
        msg = f"The Collection folder is not there (is the drive plugged in?): {folder}"
        raise PruneError(msg)
    stems = {_stem(p.name) for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")}
    if not stems:
        msg = f"The Collection folder has no files (is the drive fully synced?): {folder}"
        raise PruneError(msg)
    return stems


def linked_names(manifest_dirs: list[Path]) -> tuple[dict[str, Proof], set[str]]:
    """SoundCloud URL → approved name, from every manifest entry that carries a URL.

    Also returns the URLs of entries the rename skipped because the Collection already had
    them — those are not proof of anything, but are worth naming in the report.
    """
    linked: dict[str, Proof] = {}
    duplicates: set[str] = set()
    for folder in manifest_dirs:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                msg = f"Could not read manifest {path}: {exc}"
                raise PruneError(msg) from exc
            for entry in manifest.get("entries", []):
                url = (entry.get("soundcloud") or {}).get("url")
                if not isinstance(url, str) or not url:
                    continue
                key = normalize_url(url)
                proposed = entry.get("proposed")
                if entry.get("decision") == "apply" and isinstance(proposed, str) and proposed:
                    linked[key] = Proof(name=proposed, manifest=path.name)
                elif (
                    entry.get("decision") == "skip"
                    and DUPLICATE_REASON in (entry.get("reasons") or [])[:1]
                ):
                    duplicates.add(key)
    return linked, duplicates


def plan_prune(
    tracks: list[dict[str, Any]],
    linked: dict[str, Proof],
    duplicates: set[str],
    stems: set[str],
) -> PrunePlan:
    """Sort each track by the proof there is for it. Pure, so the rules are testable."""
    plan = PrunePlan()
    for track in tracks:
        url = normalize_url(str(track.get("permalink_url") or ""))
        proof = linked.get(url) if url else None
        if proof is not None and _stem(proof.name) in stems:
            plan.remove.append((track, proof))
            continue
        if proof is not None:
            plan.not_in_collection.append(track)
        elif url in duplicates:
            plan.duplicate_skipped.append(track)
        else:
            plan.unlinked.append(track)
        plan.keep.append(track)
    return plan


def check_guards(plan: PrunePlan, total: int, *, allow_bulk: bool) -> None:
    """Refuse a plan that would empty the playlist, or remove a lot without being told to."""
    removing = len(plan.remove)
    if total > 0 and not plan.keep:
        msg = f"Refusing to remove all {total} tracks — the playlist would be empty"
        raise PruneError(msg)
    if not allow_bulk and (removing > _BULK_COUNT or removing > total * _BULK_SHARE):
        msg = (
            f"Refusing to remove {removing} of {total} tracks without --allow-bulk "
            f"(the limit is {_BULK_COUNT} tracks or {int(_BULK_SHARE * 100)}%)"
        )
        raise PruneError(msg)


async def _fetch_tracks(client: httpx.AsyncClient, urn: str) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    url: str | None = f"/playlists/{urn}/tracks"
    params: dict[str, Any] | None = {"linked_partitioning": "true", "limit": _PAGE_SIZE}
    for _ in range(_MAX_PAGES):
        if not url:
            return tracks
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        page = resp.json()
        params = None
        if isinstance(page, list):
            tracks.extend(page)
            break
        tracks.extend(page.get("collection") or page.get("tracks") or [])
        next_href = page.get("next_href")
        # The owner's token may edit the playlist, so it must not follow a cursor off-host.
        url = same_host_path(next_href) if next_href else None
    if url:
        msg = f"The playlist ran past {_MAX_PAGES} pages without ending"
        raise PruneError(msg)
    return tracks


async def fetch_playlist(client: httpx.AsyncClient) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The playlist and every track on it, or PruneError if the list is not provably whole."""
    if not TUNEWRANGLER_SC_PLAYLIST_URL:
        msg = "TUNEWRANGLER_SC_PLAYLIST_URL is not set"
        raise PruneError(msg)
    resp = await client.get("/resolve", params={"url": TUNEWRANGLER_SC_PLAYLIST_URL.strip()})
    resp.raise_for_status()
    playlist = resp.json()
    tracks = await _fetch_tracks(client, playlist["urn"])

    if any(not t.get("id") for t in tracks):
        msg = "A playlist track came back without an id, so the update could not keep it"
        raise PruneError(msg)
    expected = int(playlist.get("track_count", -1))
    if len(tracks) != expected:
        fetched = {t["id"] for t in tracks}
        missing = [t.get("id") for t in playlist.get("tracks") or [] if t.get("id") not in fetched]
        msg = (
            f"Fetched {len(tracks)} tracks but the playlist says it has {expected}; an update "
            f"would drop the difference. Missing ids: {missing or 'unknown'}. A track its "
            "uploader deleted or made private is the likely cause — remove it by hand."
        )
        raise PruneError(msg)
    listed = [t.get("id") for t in playlist.get("tracks") or []]
    # Counts alone pass a repeated page that hides a missed one; the resolve body lists
    # every track too, so the two reads have to agree track for track.
    if listed and listed != [t["id"] for t in tracks]:
        msg = "The paged track list disagrees with the playlist's own list — not safe to update"
        raise PruneError(msg)
    return playlist, tracks


def write_backup(playlist: dict[str, Any], tracks: list[dict[str, Any]]) -> Path:
    """Save the whole track list before it changes. Raises, so a failed write stops the run."""
    folder = get_playlist_backup_dir()
    path = folder / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}_{int(playlist['id'])}.json"
    rows = [
        {"id": t["id"], "urn": t.get("urn"), "url": t.get("permalink_url"), "title": t.get("title")}
        for t in tracks
    ]
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"playlist": playlist["urn"], "tracks": rows}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        msg = f"Could not back up the track list to {path}: {exc}"
        raise PruneError(msg) from exc
    return path


async def _replace_tracks(client: httpx.AsyncClient, urn: str, keep: list[dict[str, Any]]) -> None:
    # {"id": n} is rejected with 422; only the urn form parses (probed 2026-09-24).
    body = {"playlist": {"tracks": [{"urn": f"soundcloud:tracks:{t['id']}"} for t in keep]}}
    resp = await client.put(f"/playlists/{urn}", json=body)
    resp.raise_for_status()


async def _verify(client: httpx.AsyncClient, urn: str, keep: list[dict[str, Any]]) -> None:
    want = [t["id"] for t in keep]
    got: list[Any] = []
    for attempt in range(2):
        got = [t.get("id") for t in await _fetch_tracks(client, urn)]
        if got == want:
            return
        if attempt == 0:
            # Reads can lag a write briefly; a deleted playlist still answered for a moment.
            await asyncio.sleep(_VERIFY_RETRY_S)
    msg = (
        f"After the update the playlist has {len(got)} tracks, expected {len(want)}. "
        "Compare it with the backup above."
    )
    raise PruneError(msg)


def _report(plan: PrunePlan, total: int) -> None:
    for track, proof in plan.remove:
        logger.info(
            "REMOVE  %s\n        in Collection as %r (%s)",
            track.get("title"),
            proof.name,
            proof.manifest,
        )
    for track in plan.not_in_collection:
        logger.info("KEEP    %s — approved, but not in the Collection yet", track.get("title"))
    logger.info(
        "%d tracks: %d to remove, %d kept (%d approved but not collected, %d already in the "
        "Collection under another download, %d with no rename record)",
        total,
        len(plan.remove),
        len(plan.keep),
        len(plan.not_in_collection),
        len(plan.duplicate_skipped),
        len(plan.unlinked),
    )


async def prune_playlist(*, apply: bool, allow_bulk: bool) -> None:
    """Dry run unless apply: list what would be removed, and why each one is safe to."""
    stems = collection_stems(TUNEWRANGLER_DJMUSIC_PATH)
    linked, duplicates = linked_names(get_manifest_dirs())
    async with api_client(get_owner_token_file(), "--authorize-owner") as client:
        try:
            playlist, tracks = await fetch_playlist(client)
        except (httpx.HTTPError, ApiError) as exc:
            msg = f"Could not read the playlist: {exc}"
            raise PruneError(msg) from exc
        plan = plan_prune(tracks, linked, duplicates, stems)
        _report(plan, len(tracks))
        if not plan.remove:
            logger.info("Nothing to remove.")
            return
        if not apply:
            try:
                check_guards(plan, len(tracks), allow_bulk=allow_bulk)
            except PruneError as exc:
                logger.warning("--apply would stop here: %s", exc)
            logger.info("Dry run — add --apply to remove them.")
            return
        check_guards(plan, len(tracks), allow_bulk=allow_bulk)
        backup = write_backup(playlist, tracks)
        logger.info("Backed up the full track list to %s", backup)
        try:
            await _replace_tracks(client, playlist["urn"], plan.keep)
            await _verify(client, playlist["urn"], plan.keep)
        except (httpx.HTTPError, ApiError, PruneError) as exc:
            # A timed-out update may still have landed, so this can't claim nothing changed.
            msg = f"{exc} — the playlist may have changed; the full list before is in {backup}"
            raise UpdateUncertainError(msg) from exc
        logger.info("Removed %d tracks; %d remain.", len(plan.remove), len(plan.keep))
