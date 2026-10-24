"""Keeps Collection file names and Rekordbox artist/album/title in step.

A file name is `artist - album - title` or `artist - title`. Drift is reported both ways; the
caller picks the direction per track: take the file's name into the DB, or build a new file name
from the DB.
"""

import json
import os
import re
import shutil
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

BULK_LIMIT = 20
MAX_NAME_BYTES = 200


class SyncError(Exception):
    """A write that was refused or failed; nothing was left half-done."""


@dataclass(frozen=True)
class Fields:
    artist: str
    album: str
    title: str


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def clean(text: str) -> str:
    """Colons break the name on some file systems; stray whitespace is never intended."""
    return re.sub(r"\s+", " ", (text or "").replace(":", "")).strip()


def fields_from_stem(stem: str) -> Fields:
    """Port of tagsFromFilename (src/core/tagging.ts); tests/fixtures/name_fields.json pins both."""
    parts = ["" if p.strip().lower() == "unknown" else p.strip() for p in nfc(stem).split(" - ")]
    if len(parts) == 1:
        return Fields("", "", parts[0])
    if len(parts) == 2:
        return Fields(parts[0], "", parts[1])
    return Fields(parts[0], parts[1], " - ".join(parts[2:]))


def db_fields(content: Any) -> Fields:
    return Fields(
        content.Artist.Name if content.Artist else "",
        content.Album.Name if content.Album else "",
        content.Title or "",
    )


def _redundant(album: str, artist: str, title: str) -> bool:
    return album.lower() in (artist.lower(), title.lower())


def target_fields(file: Fields, db: Fields) -> Fields:
    """What the DB should hold for a file name. With no album in the name, the DB's album is
    kept (it can be the only place a release name lives) unless it repeats artist or title."""
    artist, title = clean(file.artist), clean(file.title)
    if file.album:
        album = clean(file.album)
    else:
        album = "" if _redundant(clean(db.album), artist, title) else clean(db.album)
    return Fields(artist, album, title)


def same(a: Fields, b: Fields) -> bool:
    return (nfc(a.artist), nfc(a.album), nfc(a.title)) == (
        nfc(b.artist),
        nfc(b.album),
        nfc(b.title),
    )


@dataclass
class Drift:
    content: Any
    stem: str
    db: Fields
    file: Fields
    target: Fields

    def changes(self) -> list[tuple[str, str, str]]:
        return [
            (name, getattr(self.db, name), getattr(self.target, name))
            for name in ("artist", "album", "title")
            if nfc(getattr(self.db, name)) != nfc(getattr(self.target, name))
        ]


@dataclass
class Report:
    scanned: int
    drifted: list[Drift]
    held: list[Drift]
    by_stem: dict[str, Any]


def in_collection(content: Any, collection: Path) -> bool:
    path = content.FolderPath or ""
    return bool(path) and nfc(str(Path(path).parent)) == nfc(str(collection))


def find_drift(contents: Iterable[Any], collection: Path, holds: frozenset[str]) -> Report:
    drifted, held, by_stem, scanned = [], [], {}, 0
    for content in contents:
        if content.rb_local_deleted or not in_collection(content, collection):
            continue
        scanned += 1
        stem = Path(content.FolderPath).stem
        by_stem[nfc(stem)] = content
        db, file = db_fields(content), fields_from_stem(stem)
        target = target_fields(file, db)
        if same(target, db):
            continue
        drift = Drift(content, stem, db, file, target)
        (held if nfc(stem) in holds else drifted).append(drift)
    return Report(scanned, drifted, held, by_stem)


def name_from_db(db: Fields) -> str:
    """A file stem built from the DB fields; refuses one that wouldn't read back as them."""
    artist, title = clean(db.artist), clean(db.title)
    album = (
        "" if not clean(db.album) or _redundant(clean(db.album), artist, title) else clean(db.album)
    )
    if not artist or not title:
        raise SyncError(f"needs an artist and a title in Rekordbox: {db}")
    stem = " - ".join(p for p in (artist, album, title) if p)
    if not same(fields_from_stem(stem), Fields(artist, album, title)):
        raise SyncError(f"{stem!r} wouldn't read back as the same artist/album/title")
    if (
        "/" in stem
        or stem.startswith((".", "-"))
        or re.search(r"[\x00-\x1f\x7f]", stem)
        or len(stem.encode()) > MAX_NAME_BYTES
    ):
        raise SyncError(f"not a usable file name: {stem!r}")
    return stem


@dataclass
class Write:
    content: Any
    fields: Fields
    new_path: Path | None = None


@dataclass
class ApplyResult:
    writes: list[Write]
    journal: Path | None = None
    touched: list[Path] = field(default_factory=list)


def plan_take_file(drift: Drift) -> Write:
    return Write(drift.content, drift.target)


def plan_take_db(content: Any, all_contents: Iterable[Any]) -> Write:
    old = Path(content.FolderPath)
    stem = name_from_db(db_fields(content))
    new = old.with_name(f"{stem}{old.suffix}")
    sharing = sum(
        1 for c in all_contents if not c.rb_local_deleted and c.FolderPath == content.FolderPath
    )
    if sharing > 1:
        raise SyncError(f"{sharing} Rekordbox tracks share {old.name}; fix those by hand")
    if new.exists() and not (old.exists() and os.path.samefile(old, new)):
        raise SyncError(f"{new.name} already exists")
    return Write(content, fields_from_stem(stem), new if new != old else None)


def _journal_row(w: Write) -> dict[str, Any]:
    c = w.content
    return {
        "content_id": c.ID,
        "before": {
            "ArtistID": c.ArtistID,
            "AlbumID": c.AlbumID,
            "Title": c.Title,
            "FolderPath": c.FolderPath,
            "FileNameL": c.FileNameL,
        },
        "after": {
            "artist": w.fields.artist,
            "album": w.fields.album,
            "title": w.fields.title,
            "FolderPath": str(w.new_path) if w.new_path else c.FolderPath,
        },
    }


def apply_writes(
    db: Any,
    writes: list[Write],
    journal_dir: Path,
    *,
    create_backup: Callable[[], Path],
    discard_backup: Callable[[Path], None],
    assert_closed: Callable[[], None],
    landed: Callable[[Write], bool],
    now: Callable[[], datetime] = datetime.now,
) -> ApplyResult:
    """DB edits and file renames land together or not at all. The journal is written before
    the commit, so a write can never reach Rekordbox without a record of what it replaced."""
    result = ApplyResult(writes)
    if not writes:
        return result
    assert_closed()
    backup = create_backup()
    stamp = now().strftime("%Y%m%d-%H%M%S")
    run_dir = journal_dir / stamp
    anlz_copies = run_dir / "anlz"
    journal = {
        "created_at": stamp,
        "backup": str(backup),
        "status": "pending",
        "rows": [_journal_row(w) for w in writes],
    }
    renamed: list[tuple[Path, Path]] = []
    copied: list[tuple[Path, Path]] = []

    def undo_files() -> None:
        stuck = []
        for original, copy in copied:
            try:
                shutil.copy2(copy, original)
            except OSError as e:
                stuck.append(f"{original} (copy kept at {copy}): {e}")
        for old, new in reversed(renamed):
            try:
                new.rename(old)
            except OSError as e:
                stuck.append(f"{new} should be {old.name}: {e}")
        if stuck:
            raise SyncError(
                "rolled back Rekordbox, but these need fixing by hand: " + "; ".join(stuck)
            )

    journal_path = run_dir / "journal.json"
    ours = False
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
        write_json(journal_path, journal)
        ours = True
        artists: dict[str, Any] = {}
        albums: dict[str, Any] = {}
        for w in writes:
            c = w.content
            if w.new_path:
                old = Path(c.FolderPath)
                analysis = db.analysis_files(c.ID)
                for path in analysis:
                    copy = anlz_copies / str(c.ID) / Path(path).name
                    copy.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, copy)
                    copied.append((Path(path), copy))
                # rename() replaces an existing file without asking.
                if w.new_path.exists() and not os.path.samefile(old, w.new_path):
                    raise SyncError(f"{w.new_path.name} appeared since the plan was made")
                old.rename(w.new_path)
                renamed.append((old, w.new_path))
                c.FolderPath, c.FileNameL = str(w.new_path), w.new_path.name
                # Rekordbox itself stores only "?/<file name>" here, not the full path.
                for path, anlz in analysis.items():
                    anlz.set_path(f"?/{w.new_path.name}")
                    anlz.save(path)
            if w.fields.artist not in artists:
                artists[w.fields.artist] = (
                    db.get_or_create_artist(w.fields.artist) if w.fields.artist else None
                )
            if w.fields.album not in albums:
                albums[w.fields.album] = (
                    db.get_or_create_album(w.fields.album) if w.fields.album else None
                )
            artist, album = artists[w.fields.artist], albums[w.fields.album]
            c.ArtistID = artist.ID if artist else None
            c.AlbumID = album.ID if album else None
            c.Title = w.fields.title
            # A VARCHAR column holding digits; Rekordbox bumps it on every edit.
            c.TrackInfoUpdated = str(int(c.TrackInfoUpdated or 0) + 1)
        assert_closed()
    except BaseException:
        db.rollback()
        discard_backup(backup)
        if ours:
            _set_status(journal_path, "failed")
        undo_files()
        raise
    try:
        db.commit()
    except BaseException:
        # pyrekordbox commits the rows before its playlist XML step, so a failure there
        # leaves them in; undoing the files would then point Rekordbox at missing ones.
        if landed(writes[0]):
            _set_status(journal_path, "committed")
            raise
        db.rollback()
        _set_status(journal_path, "failed")
        undo_files()
        raise
    _set_status(journal_path, "committed")
    result.journal = journal_path
    result.touched = [Path(w.content.FolderPath) for w in writes]
    return result


def _set_status(journal_path: Path, status: str) -> None:
    if not journal_path.exists():
        return
    data = json.loads(journal_path.read_text())
    data["status"] = status
    write_json(journal_path, data)


def write_json(path: Path, data: Any) -> None:
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(partial, path)


def duplicate_targets(writes: list[Write]) -> list[str]:
    # The Collection drive (exFAT) ignores case, so "A.mp3" and "a.mp3" are one file.
    counts = Counter(nfc(str(w.new_path)).casefold() for w in writes if w.new_path)
    return [p for p, n in counts.items() if n > 1]
