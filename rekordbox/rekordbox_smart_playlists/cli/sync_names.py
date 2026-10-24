"""`rsp sync-names`: report and fix drift between Collection file names and Rekordbox."""

import argparse
import fcntl
import json
import os
import subprocess
import time
from pathlib import Path

from ..core import name_sync as ns
from ..core.backup_manager import (
    BackupError,
    BackupManager,
    RekordboxRunningError,
    assert_rekordbox_closed,
)
from ..core.config import REPO_ROOT, Config, ConfigurationError
from ..core.database import RekordboxDatabase
from ..utils.logging import get_logger, log_error, log_exception

EXIT_TRY_LATER = 75
SNAPSHOT_PREFIX = "sync_names_master_db"
SNAPSHOT_KEEP = 5
# rM's run lock (an OS flock): a rename run moving files in must not race these renames.
RUN_LOCK = REPO_ROOT / "logs/tunewrangler/rm.lock"

logger = get_logger(__name__)


class SyncNamesCommand:
    def __init__(self, config: Config):
        self.config = config

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        pick = parser.add_mutually_exclusive_group()
        pick.add_argument(
            "--take-file", nargs="+", metavar="STEM", help="Set Rekordbox from these file names"
        )
        pick.add_argument(
            "--take-file-all",
            action="store_true",
            help="Set Rekordbox from every drifted file name",
        )
        pick.add_argument(
            "--take-db", nargs="+", metavar="STEM", help="Rename these files from Rekordbox"
        )
        pick.add_argument("--hold", metavar="STEM", help="Leave this track out of the sync")
        pick.add_argument("--unhold", metavar="STEM", help="Put a held track back")
        parser.add_argument("--yes", action="store_true", help="Write (default is a dry run)")
        parser.add_argument(
            "--allow-bulk",
            action="store_true",
            help=f"Allow more than {ns.BULK_LIMIT} tracks in one write",
        )

    @staticmethod
    def validate_args(args: argparse.Namespace) -> bool:
        return True

    def execute(self, args: argparse.Namespace) -> int:
        try:
            return self._run(args)
        except RekordboxRunningError as e:
            log_error(logger, str(e))
            return EXIT_TRY_LATER
        except (ConfigurationError, ns.SyncError, BackupError) as e:
            log_error(logger, str(e))
            return 1
        except Exception as e:
            log_exception(logger, e, "sync-names")
            return 1

    def _holds_path(self) -> Path:
        return Path(self.config.sync_names_dir).expanduser() / "holds.json"

    def _holds(self) -> frozenset[str]:
        path = self._holds_path()
        if not path.exists():
            return frozenset()
        return frozenset(ns.nfc(s) for s in json.loads(path.read_text()))

    def _save_holds(self, holds: frozenset[str]) -> None:
        path = self._holds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        ns.write_json(path, sorted(holds))

    def _run(self, args: argparse.Namespace) -> int:
        collection = self.config.require_collection_dir()
        if not collection.is_dir():
            log_error(logger, f"Collection folder not found (drive unplugged?): {collection}")
            return EXIT_TRY_LATER
        holds = self._holds()
        if args.hold or args.unhold:
            stem = ns.nfc(args.hold or args.unhold)
            self._save_holds(holds | {stem} if args.hold else holds - {stem})
            print(f"{'held' if args.hold else 'unheld'}: {stem}")
            return 0

        with RekordboxDatabase(self.config) as db:
            contents = db.get_content()
            report = ns.find_drift(contents, collection, holds)
            if report.scanned == 0:
                log_error(logger, f"no Rekordbox tracks found in {collection}; is the path right?")
                return 1
            writes = self._plan(args, report, contents)
            if writes is None:
                print_report(report)
                return 0
            for line in describe(writes):
                print(line)
            if len(writes) > ns.BULK_LIMIT and not args.allow_bulk:
                log_error(
                    logger,
                    f"{len(writes)} tracks; add --allow-bulk to write more than {ns.BULK_LIMIT}",
                )
                return 1
            if not writes:
                print("nothing to write")
                return 0
            if self.config.dry_run or not args.yes:
                print(f"dry run: {len(writes)} tracks would change; add --yes to write")
                return 0
            manager = BackupManager(self.config)
            with run_lock() as held:
                if not held:
                    log_error(logger, f"another run holds {RUN_LOCK}; nothing was changed")
                    return EXIT_TRY_LATER
                result = ns.apply_writes(
                    db,
                    writes,
                    Path(self.config.sync_names_dir).expanduser(),
                    create_backup=lambda: manager.snapshot_db(SNAPSHOT_PREFIX),
                    discard_backup=lambda p: p.unlink(missing_ok=True),
                    assert_closed=assert_rekordbox_closed,
                    landed=lambda w: self._landed(w),
                )
        # Only after a commit, so an aborted write never costs an older good snapshot.
        manager.rotate_snapshots(SNAPSHOT_PREFIX, SNAPSHOT_KEEP)
        print(f"wrote {len(writes)} tracks; journal: {result.journal}")
        if any(w.new_path for w in writes):
            print("renamed files may stay on the SoundCloud playlist: prune matches approved names")
        return retag(collection, result.touched)

    def _landed(self, write: ns.Write) -> bool:
        with RekordboxDatabase(self.config) as fresh:
            row = fresh.get_track(write.content.ID)
        path = str(write.new_path) if write.new_path else row and row.FolderPath
        return row is not None and row.Title == write.fields.title and row.FolderPath == path

    def _plan(
        self, args: argparse.Namespace, report: ns.Report, contents: list
    ) -> list[ns.Write] | None:
        if args.take_file_all:
            return [ns.plan_take_file(d) for d in report.drifted]
        if args.take_file:
            drifts = {ns.nfc(d.stem): d for d in report.drifted + report.held}
            missing = [s for s in args.take_file if ns.nfc(s) not in drifts]
            if missing:
                raise ns.SyncError(f"not drifted (or not in the Collection): {', '.join(missing)}")
            return [ns.plan_take_file(drifts[ns.nfc(s)]) for s in args.take_file]
        if args.take_db:
            missing = [s for s in args.take_db if ns.nfc(s) not in report.by_stem]
            if missing:
                raise ns.SyncError(f"not in the Collection: {', '.join(missing)}")
            writes = [ns.plan_take_db(report.by_stem[ns.nfc(s)], contents) for s in args.take_db]
            if dupes := ns.duplicate_targets(writes):
                raise ns.SyncError(f"two tracks would get the same name: {', '.join(dupes)}")
            return writes
        return None


class run_lock:
    def __enter__(self) -> bool:
        RUN_LOCK.parent.mkdir(parents=True, exist_ok=True)
        self.file = RUN_LOCK.open("a")
        deadline = time.monotonic() + 2
        while True:
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                if time.monotonic() > deadline:
                    return False
                time.sleep(0.1)

    def __exit__(self, *_exc: object) -> None:
        self.file.close()


def print_report(report: ns.Report) -> None:
    for d in report.drifted:
        print(d.stem)
        for name, db, file in d.changes():
            print(f"  {name}: {db!r} -> {file!r}")
    if report.held:
        print(f"held ({len(report.held)}): " + "; ".join(d.stem for d in report.held))
    print(f"scanned: {report.scanned} tracks")
    print(f"drift: {len(report.drifted)} tracks ({len(report.held)} held)")


def describe(writes: list[ns.Write]) -> list[str]:
    lines = []
    for w in writes:
        if w.new_path:
            lines.append(f"rename {Path(w.content.FolderPath).name}\n    -> {w.new_path.name}")
        else:
            f, stem = w.fields, Path(w.content.FolderPath).stem
            lines.append(f"set    {stem}: {f.artist!r} / {f.album!r} / {f.title!r}")
    return lines


def retag(collection: Path, touched: list[Path]) -> int:
    """Tags follow the name, or a Reload Tag in Rekordbox brings the old fields back."""
    on_disk = {ns.nfc(name): name for name in os.listdir(collection)}
    missing = [p.name for p in touched if ns.nfc(p.name) not in on_disk]
    if missing:
        log_error(
            logger, f"not in {collection} after the write, so not retagged: {', '.join(missing)}"
        )
        return 1
    names = [on_disk[ns.nfc(p.name)] for p in touched]
    args = ["deno", "task", "retag", "--dir", str(collection), "--overwrite", "--yes"]
    if not names:
        return 0
    # "--only=NAME", so a name starting with "-" can't read as another flag.
    args += [f"--only={name}" for name in names]
    code = subprocess.run(args, cwd=REPO_ROOT, check=False).returncode
    if code != 0:
        log_error(logger, f"retag exited {code}; Rekordbox is updated, re-run: {' '.join(args)}")
        return 1
    return 0
