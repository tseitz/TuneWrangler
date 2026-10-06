import json
import os
import zipfile

from rekordbox_smart_playlists.core.backup_manager import BACKUP_CREATED_BY, BackupManager
from rekordbox_smart_playlists.core.config import Config


def _zip(path, metadata=None, mtime=0):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("x_content/Library/placeholder", "")
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
