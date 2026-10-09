import json
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.backup_manager import PINNED_BACKUP_NAME
from ..utils.logging import get_logger, log_exception
from . import manifest as mf
from .library import ARCHIVE_TAG, AUTOTAG_MARKER, EXCLUDED
from .suggest import EXPERIMENTAL_BASS, HALFTIME, LANE_EXTRAS, SCORED_TAGS

ALLOWED_TAGS = frozenset(SCORED_TAGS) | {EXPERIMENTAL_BASS, HALFTIME}
BACKUP_NAME = PINNED_BACKUP_NAME

logger = get_logger(__name__)


class ApplyError(Exception):
    pass


@dataclass
class Selection:
    limit: int | None = None
    sample: int | None = None
    seed: int = 0
    only: frozenset[str] = frozenset()


@dataclass
class ApplyResult:
    writes: list[tuple[str, list[str]]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    row_ids: list[dict[str, str]] = field(default_factory=list)
    log_path: Path | None = None


def select_entries(manifest: mf.Manifest, selection: Selection) -> list[mf.Entry]:
    entries = [e for e in manifest.entries if e.decision == "apply" and e.proposed]
    if selection.only:
        entries = [e for e in entries if e.content_id in selection.only]
        missing = selection.only - {e.content_id for e in entries}
        if missing:
            raise ApplyError(f"not apply entries in this manifest: {sorted(missing)}")
    if selection.sample is not None:
        rng = random.Random(selection.seed)
        entries = rng.sample(entries, min(selection.sample, len(entries)))
    if selection.limit is not None:
        entries = entries[: selection.limit]
    return entries


def resolve_tags(db: Any, names: set[str]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for name in sorted(names):
        rows = [t for t in db.get_tags(Name=name) if t.Attribute != 1]
        if len(rows) != 1:
            raise ApplyError(
                f"My Tag {name!r} matches {len(rows)} tags; create it once in Rekordbox"
            )
        ids[name] = str(rows[0].ID)
    return ids


def check_manifest(manifest: mf.Manifest, vocab: frozenset[str], entries: list[mf.Entry]) -> None:
    mf.validate(manifest)
    if manifest.vocabulary_hash != mf.vocabulary_hash(vocab):
        raise ApplyError(
            "the lane tags changed since this manifest was made; run tag suggest again"
        )
    unknown = {t for e in entries for t in e.proposed} - ALLOWED_TAGS
    if unknown:
        raise ApplyError(f"manifest proposes tags the tool may not write: {sorted(unknown)}")


def plan_writes(
    db: Any, entries: list[mf.Entry], vocab: frozenset[str]
) -> tuple[list[tuple[str, list[str]]], list[tuple[str, str]]]:
    """Re-reads every track now: suggest ran earlier, and the user may have tagged it since."""
    lane = vocab | LANE_EXTRAS
    writes: list[tuple[str, list[str]]] = []
    skipped: list[tuple[str, str]] = []
    for e in entries:
        content = db.get_track(e.content_id)
        if content is None or content.rb_local_deleted:
            skipped.append((e.content_id, "track missing"))
            continue
        current = set(content.MyTagNames or [])
        if ARCHIVE_TAG in current or current & EXCLUDED:
            skipped.append((e.content_id, "archived or curated since suggest"))
        elif AUTOTAG_MARKER in current:
            skipped.append((e.content_id, "already autotagged"))
        elif current & lane:
            skipped.append((e.content_id, "has lane tags now"))
        else:
            writes.append((e.content_id, [*e.proposed, AUTOTAG_MARKER]))
    return writes, skipped


def _rollback(db: Any) -> None:
    """Logs a failed rollback instead of raising it, so the original error is the one surfaced."""
    try:
        db.rollback()
    except Exception as e:  # noqa: BLE001
        log_exception(logger, e, "rolling back after a failed tag write")


def apply_manifest(
    db: Any,
    manifest: mf.Manifest,
    manifest_path: Path,
    vocab: frozenset[str],
    selection: Selection,
    *,
    create_backup: Callable[[], str | None],
    assert_closed: Callable[[], None],
    dry_run: bool,
    now: Callable[[], datetime] = datetime.now,
) -> ApplyResult:
    entries = select_entries(manifest, selection)
    check_manifest(manifest, vocab, entries)
    tag_ids = resolve_tags(db, {t for e in entries for t in e.proposed} | {AUTOTAG_MARKER})
    writes, skipped = plan_writes(db, entries, vocab)
    result = ApplyResult(writes=writes, skipped=skipped)
    if dry_run or not writes:
        return result

    assert_closed()
    if not create_backup():
        raise ApplyError("backup failed; nothing was written")
    stamp = now()
    log_path = manifest_path.with_name(f"{manifest_path.stem}.applied-{stamp:%Y%m%d-%H%M%S}.json")
    log = {
        "manifest": str(manifest_path),
        "applied_at": stamp.isoformat(timespec="seconds"),
        "marker": AUTOTAG_MARKER,
        "status": "pending",
        "rows": result.row_ids,
    }
    try:
        for content_id, tags in writes:
            for tag in tags:
                row_id = db.add_song_tag(content_id, tag_ids[tag])
                result.row_ids.append({"id": row_id, "content_id": content_id, "tag": tag})
            db.mark_track_info_updated(content_id)
        # Row IDs are client-side uuids, so the log can exist before the commit: rows can never
        # land in Rekordbox without a record undo can find. A pending log for a commit that never
        # happened is harmless; undo reports its rows as already removed.
        with log_path.open("x") as f:
            json.dump(log, f, indent=2)
        # The backup can take minutes, so Rekordbox may have been opened since.
        assert_closed()
        db.commit()
    except BaseException:
        _rollback(db)
        raise
    log["status"] = "committed"
    log_path.write_text(json.dumps(log, indent=2))
    result.log_path = log_path
    return result


def _read_log(log_path: Path) -> list[dict[str, str]]:
    try:
        rows = json.loads(log_path.read_text())["rows"]
        return [{k: str(r[k]) for k in ("id", "content_id", "tag")} for r in rows]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ApplyError(f"not a readable apply log: {log_path} ({e})") from e


def undo(
    db: Any,
    log_path: Path,
    *,
    create_backup: Callable[[], str | None],
    assert_closed: Callable[[], None],
    dry_run: bool,
    force: bool = False,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Deletes exactly the rows an apply wrote, if they're still what it wrote. A track whose
    marker is gone was reviewed by the user, so its rows are left unless `force`."""
    rows = _read_log(log_path)
    tag_ids = resolve_tags(db, {r["tag"] for r in rows})
    current: dict[str, Any] = {}
    gone: list[tuple[str, str]] = []
    for r in rows:
        row = db.get_song_tag(r["id"])
        if row is None or row.rb_local_deleted:
            gone.append((r["id"], "already removed"))
        elif str(row.ContentID) != r["content_id"] or str(row.MyTagID) != tag_ids[r["tag"]]:
            gone.append((r["id"], "row changed since apply"))
        else:
            current[r["id"]] = row
    reviewed = {
        r["content_id"]
        for r in rows
        if r["tag"] == AUTOTAG_MARKER and r["id"] not in current and not force
    }
    targets = []
    for r in rows:
        if r["id"] not in current:
            continue
        if r["content_id"] in reviewed:
            gone.append((r["id"], "track reviewed since apply (marker removed)"))
        else:
            targets.append((current[r["id"]], r))
    if dry_run or not targets:
        return [r["id"] for _, r in targets], gone

    assert_closed()
    if not create_backup():
        raise ApplyError("backup failed; nothing was removed")
    try:
        for row, _ in targets:
            db.delete_song_tag(row)
        for content_id in sorted({r["content_id"] for _, r in targets}):
            db.mark_track_info_updated(content_id)
        assert_closed()
        db.commit()
    except BaseException:
        _rollback(db)
        raise
    return [r["id"] for _, r in targets], gone
