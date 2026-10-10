from types import SimpleNamespace

from rekordbox_smart_playlists.cli import commands
from rekordbox_smart_playlists.core.backup_manager import RekordboxRunningError
from rekordbox_smart_playlists.core.config import Config


def test_rekordbox_running_exits_try_later(monkeypatch):
    def running(self, args):
        raise RekordboxRunningError("Rekordbox is running")

    monkeypatch.setattr(commands.TagCommand, "_apply", running)
    exit_code = commands.TagCommand(Config()).execute(SimpleNamespace(tag_action="apply"))
    assert exit_code == commands.EXIT_TRY_LATER == 75


class _NoDb:
    def __init__(self, *_a):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _apply_with(monkeypatch, tmp_path, log_path):
    rotations = []

    class FakeManager:
        def __init__(self, *_a):
            pass

        def rotate_snapshots(self, prefix, keep):
            rotations.append((prefix, keep))

    result = commands.tag_apply.ApplyResult(log_path=log_path)
    monkeypatch.setattr(commands, "RekordboxDatabase", _NoDb)
    monkeypatch.setattr(commands, "BackupManager", FakeManager)
    monkeypatch.setattr(commands.tag_manifest, "read_manifest", lambda _p: None)
    monkeypatch.setattr(commands.tag_apply, "apply_manifest", lambda *_a, **_kw: result)
    monkeypatch.setattr(commands.TagCommand, "_vocab", lambda self: frozenset())
    args = SimpleNamespace(
        tag_action="apply", manifest=tmp_path / "m.json", limit=None, sample=None, seed=0,
        only=None, yes=True, db_keep=7,
    )
    assert commands.TagCommand(Config()).execute(args) == 0
    return rotations


def test_snapshots_rotate_only_after_a_committed_apply(monkeypatch, tmp_path):
    committed = _apply_with(monkeypatch, tmp_path, tmp_path / "x.applied-1.json")
    assert committed == [(commands.tag_apply.DB_SNAPSHOT_PREFIX, 7)]
    assert _apply_with(monkeypatch, tmp_path, None) == []
