import json
import os
import shutil
import zipfile

import pytest

from rekordbox_smart_playlists.core import backup_manager as bm
from rekordbox_smart_playlists.core.backup_manager import BACKUP_CREATED_BY, BackupManager
from rekordbox_smart_playlists.core.config import Config


@pytest.fixture(autouse=True)
def rekordbox_closed(monkeypatch):
    monkeypatch.setattr(bm, "get_rekordbox_pid", lambda: 0)


@pytest.fixture
def pioneer(tmp_path):
    library = tmp_path / "Pioneer"
    (library / "rekordbox").mkdir(parents=True)
    (library / "rekordbox" / "master.db").write_text("original")
    app_support = tmp_path / "AppSupport"
    app_support.mkdir()
    (app_support / "settings").write_text("original")
    return library, app_support


@pytest.fixture
def manager(tmp_path, pioneer):
    backups = tmp_path / "backups"
    backups.mkdir()
    library, app_support = pioneer
    config = Config(
        backup_base_path=str(backups),
        pioneer_library=str(library),
        pioneer_app_support=str(app_support),
        max_backups=10,
    )
    return BackupManager(config)


def _zip(path, metadata=None, mtime=0):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("x_content/Library/rekordbox/master.db", "db")
        if metadata is not None:
            zf.writestr("x_content/backup_metadata.json", json.dumps(metadata))
    os.utime(path, (mtime, mtime))


def test_cleanup_deletes_only_zips_this_tool_wrote(tmp_path):
    ours = {"created_by": BACKUP_CREATED_BY}
    _zip(tmp_path / "before_playlist_creation_1.zip", ours, mtime=1_000)
    _zip(tmp_path / "before_playlist_creation_2.zip", ours, mtime=2_000)
    _zip(tmp_path / "my_backup_photos.zip", mtime=500)
    _zip(tmp_path / "before_trip.zip", {"created_by": "someone else"}, mtime=400)

    manager = BackupManager(Config(backup_base_path=str(tmp_path), max_backups=1))
    manager._cleanup_old_backups()

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "before_playlist_creation_2.zip",
        "before_trip.zip",
        "my_backup_photos.zip",
    ]


def test_backup_round_trip_restores_live_folders(manager, pioneer):
    library, app_support = pioneer
    backup = manager.create_backup("before_test")
    assert backup is not None
    assert not list(manager.backup_base.glob(".*"))

    (library / "rekordbox" / "master.db").write_text("changed")
    (app_support / "settings").write_text("changed")

    assert manager.restore_backup(backup)
    assert (library / "rekordbox" / "master.db").read_text() == "original"
    assert (app_support / "settings").read_text() == "original"
    assert sorted(p.name for p in library.parent.iterdir() if "restor" in p.name) == []
    assert len(manager.list_backups()) == 2  # the restored one + the safety backup


def test_backup_refused_while_rekordbox_runs(manager, monkeypatch):
    monkeypatch.setattr(bm, "get_rekordbox_pid", lambda: 4242)

    assert manager.create_backup("before_test") is None
    assert not list(manager.backup_base.iterdir())


def test_backup_without_library_is_refused(manager, pioneer):
    shutil.rmtree(pioneer[0])

    assert manager.create_backup("before_test") is None
    assert not list(manager.backup_base.iterdir())


def test_failed_restore_copy_leaves_live_folders_untouched(manager, pioneer, monkeypatch):
    library, _ = pioneer
    backup = manager.create_backup("before_test")
    (library / "rekordbox" / "master.db").write_text("live")

    def disk_full(src, dst, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(bm.shutil, "copytree", disk_full)
    assert not manager.restore_backup(backup, create_safety_backup=False)

    assert (library / "rekordbox" / "master.db").read_text() == "live"
    assert sorted(p.name for p in library.parent.iterdir() if "restor" in p.name) == []


def test_restore_never_cleans_away_its_own_source(manager):
    manager.config.max_backups = 1
    oldest = manager.create_backup("before_oldest")
    os.utime(oldest, (0, 0))

    assert manager.restore_backup(oldest)
    assert os.path.exists(oldest)


def test_validation_requires_master_db(manager, tmp_path):
    zip_path = manager.backup_base / "before_x.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("x_content/Application Support/settings", "")
        zf.writestr("x_content/backup_metadata.json", json.dumps({"created_by": BACKUP_CREATED_BY}))

    assert not manager.validate_backup(zip_path)


def test_delete_refuses_files_it_did_not_write(manager, tmp_path):
    foreign = manager.backup_base / "photos_backup.zip"
    _zip(foreign)
    outside = tmp_path / "before_elsewhere.zip"
    _zip(outside, {"created_by": BACKUP_CREATED_BY})

    assert not manager.delete_backup(foreign)
    assert not manager.delete_backup(outside)
    assert foreign.exists() and outside.exists()


def _leftovers(root):
    return sorted(p.name for p in root.iterdir() if "." in p.name and "-" in p.name)


def _fail_rename(monkeypatch, name_fragment, exc=OSError("rename failed")):
    real_rename = bm.Path.rename

    def rename(self, target):
        if name_fragment in self.name:
            raise exc
        return real_rename(self, target)

    monkeypatch.setattr(bm.Path, "rename", rename)


def test_failed_swap_puts_the_live_library_back(manager, pioneer, monkeypatch):
    library, _ = pioneer
    backup = manager.create_backup("before_test")
    (library / "rekordbox" / "master.db").write_text("live")

    _fail_rename(monkeypatch, "Pioneer.restoring-")
    assert not manager.restore_backup(backup, create_safety_backup=False)

    assert (library / "rekordbox" / "master.db").read_text() == "live"
    assert _leftovers(library.parent) == []


def test_failure_on_second_folder_rolls_back_the_first(manager, pioneer, monkeypatch):
    library, app_support = pioneer
    backup = manager.create_backup("before_test")
    (library / "rekordbox" / "master.db").write_text("live")
    (app_support / "settings").write_text("live")

    _fail_rename(monkeypatch, "AppSupport.restoring-")
    assert not manager.restore_backup(backup, create_safety_backup=False)

    assert (library / "rekordbox" / "master.db").read_text() == "live"
    assert (app_support / "settings").read_text() == "live"
    assert _leftovers(library.parent) == []


def test_interrupted_staging_leaves_nothing_behind(manager, pioneer, monkeypatch):
    library, _ = pioneer
    backup = manager.create_backup("before_test")
    real_copytree = shutil.copytree

    def copytree(src, dst, *args, **kwargs):
        if "AppSupport" in str(dst):
            raise KeyboardInterrupt
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr(bm.shutil, "copytree", copytree)
    with pytest.raises(KeyboardInterrupt):
        manager.restore_backup(backup, create_safety_backup=False)

    assert (library / "rekordbox" / "master.db").read_text() == "original"
    assert _leftovers(library.parent) == []


def test_restore_refused_while_rekordbox_runs(manager, pioneer, monkeypatch):
    library, _ = pioneer
    backup = manager.create_backup("before_test")
    (library / "rekordbox" / "master.db").write_text("live")
    monkeypatch.setattr(bm, "get_rekordbox_pid", lambda: 4242)

    assert not manager.restore_backup(backup, create_safety_backup=False)
    assert (library / "rekordbox" / "master.db").read_text() == "live"


def test_restore_refused_after_an_unfinished_one(manager, pioneer):
    library, _ = pioneer
    backup = manager.create_backup("before_test")
    (library.parent / "Pioneer.pre-restore-20260101_000000").mkdir()

    assert not manager.restore_backup(backup, create_safety_backup=False)
    assert (library / "rekordbox" / "master.db").read_text() == "original"


def test_restore_refuses_a_symlinked_library(manager, pioneer, tmp_path):
    library, _ = pioneer
    backup = manager.create_backup("before_test")
    external = tmp_path / "external"
    library.rename(external)
    library.symlink_to(external)

    assert not manager.restore_backup(backup, create_safety_backup=False)
    assert library.is_symlink()


def test_restore_refuses_backup_missing_app_support(manager, pioneer):
    library, app_support = pioneer
    zip_path = manager.backup_base / "before_x.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("x_content/Library/rekordbox/master.db", "old")
        zf.writestr("x_content/backup_metadata.json", json.dumps({"created_by": BACKUP_CREATED_BY}))

    assert not manager.restore_backup(zip_path, create_safety_backup=False)
    assert (library / "rekordbox" / "master.db").read_text() == "original"


def test_failed_archive_leaves_no_partial_zip(manager, monkeypatch):
    def broken_archive(source_dir, archive_path):
        archive_path.write_text("half")
        raise OSError("disk full")

    monkeypatch.setattr(manager, "_create_archive", broken_archive)

    assert manager.create_backup("before_test") is None
    assert not list(manager.backup_base.iterdir())
