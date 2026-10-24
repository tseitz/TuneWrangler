from argparse import Namespace
from types import SimpleNamespace

import pytest

from rekordbox_smart_playlists.cli import sync_names as cmd
from rekordbox_smart_playlists.core import name_sync as ns
from rekordbox_smart_playlists.core.backup_manager import RekordboxRunningError
from rekordbox_smart_playlists.core.config import Config


def args(**kw):
    base = dict(
        take_file=None,
        take_file_all=False,
        take_db=None,
        hold=None,
        unhold=None,
        yes=False,
        allow_bulk=False,
    )
    return Namespace(**{**base, **kw})


def drifted(folder, n):
    return [
        SimpleNamespace(
            ID=str(i),
            FolderPath=str(folder / f"A{i} - T.mp3"),
            FileNameL=f"A{i} - T.mp3",
            Artist=SimpleNamespace(Name="wrong"),
            Album=None,
            Title="T",
            rb_local_deleted=0,
            ArtistID=None,
            AlbumID=None,
            TrackInfoUpdated="1",
        )
        for i in range(n)
    ]


@pytest.fixture
def setup(monkeypatch, tmp_path):
    collection = tmp_path / "Collection"
    collection.mkdir()
    applied = []

    class FakeDb:
        contents: list = []

        def __init__(self, *_a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def get_content(self):
            return FakeDb.contents

    class FakeManager:
        def __init__(self, *_a):
            pass

        def rotate_snapshots(self, *_a):
            pass

    monkeypatch.setattr(cmd, "RekordboxDatabase", FakeDb)
    monkeypatch.setattr(cmd, "BackupManager", FakeManager)
    monkeypatch.setattr(
        cmd.ns, "apply_writes", lambda _db, writes, *_a, **_kw: applied.append(writes)
    )
    config = Config(collection_path=str(collection), sync_names_dir=str(tmp_path / "sync"))
    return SimpleNamespace(
        collection=collection,
        db=FakeDb,
        applied=applied,
        run=lambda a: cmd.SyncNamesCommand(config).execute(a),
    )


def test_report_prints_the_drift_line(setup, capsys):
    setup.db.contents = drifted(setup.collection, 2)
    assert setup.run(args()) == 0
    out = capsys.readouterr().out
    assert "scanned: 2 tracks\ndrift: 2 tracks (0 held)" in out


def test_no_tracks_under_the_collection_is_an_error_not_a_clean_bill(setup):
    setup.db.contents = drifted(setup.collection / "elsewhere", 2)
    assert setup.run(args()) == 1


def test_an_unplugged_drive_is_try_later(setup):
    setup.collection.rmdir()
    assert setup.run(args()) == cmd.EXIT_TRY_LATER


def test_rekordbox_running_is_try_later(setup, monkeypatch):
    setup.db.contents = drifted(setup.collection, 1)

    def running(*_a, **_kw):
        raise RekordboxRunningError("running")

    monkeypatch.setattr(cmd.ns, "apply_writes", running)
    assert setup.run(args(take_file_all=True, yes=True)) == cmd.EXIT_TRY_LATER


def test_writes_need_yes(setup):
    setup.db.contents = drifted(setup.collection, 1)
    assert setup.run(args(take_file_all=True)) == 0
    assert setup.applied == []


def test_more_than_the_bulk_limit_needs_allow_bulk(setup):
    setup.db.contents = drifted(setup.collection, ns.BULK_LIMIT + 1)
    assert setup.run(args(take_file_all=True, yes=True)) == 1
    assert setup.applied == []


def test_holds_persist_and_leave_the_track_out(setup, capsys):
    setup.db.contents = drifted(setup.collection, 2)
    assert setup.run(args(hold="A0 - T")) == 0
    capsys.readouterr()
    assert setup.run(args()) == 0
    assert "drift: 1 tracks (1 held)" in capsys.readouterr().out
    assert setup.run(args(unhold="A0 - T")) == 0
    assert setup.run(args()) == 0
    assert "drift: 2 tracks (0 held)" in capsys.readouterr().out


def test_a_committed_write_retags_the_touched_files(setup, monkeypatch):
    setup.db.contents = drifted(setup.collection, 1)
    touched = [setup.collection / "A0 - T.mp3"]
    monkeypatch.setattr(
        cmd.ns,
        "apply_writes",
        lambda *_a, **_kw: ns.ApplyResult([], setup.collection / "j.json", touched),
    )
    retagged = []
    monkeypatch.setattr(cmd, "retag", lambda collection, files: retagged.append(files) or 0)
    assert setup.run(args(take_file=["A0 - T"], yes=True)) == 0
    assert retagged == [touched]


def test_an_empty_write_never_reaches_retag(setup, monkeypatch):
    setup.db.contents = drifted(setup.collection, 1)
    setup.db.contents[0].Artist = SimpleNamespace(Name="A0")
    monkeypatch.setattr(cmd, "retag", lambda *_a: pytest.fail("retag ran"))
    assert setup.run(args(take_file_all=True, yes=True)) == 0
    assert setup.applied == []


def test_retag_with_no_names_runs_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(cmd.subprocess, "run", lambda *_a, **_kw: pytest.fail("ran retag"))
    assert cmd.retag(tmp_path, []) == 0


def test_retag_passes_names_as_one_token(tmp_path, monkeypatch):
    (tmp_path / "-x - T.mp3").write_text("")
    calls = []
    monkeypatch.setattr(
        cmd.subprocess, "run", lambda a, **_kw: calls.append(a) or SimpleNamespace(returncode=0)
    )
    assert cmd.retag(tmp_path, [tmp_path / "-x - T.mp3"]) == 0
    assert calls[0][-1] == "--only=-x - T.mp3"


def test_a_held_run_lock_is_try_later(setup, monkeypatch):
    setup.db.contents = drifted(setup.collection, 1)
    class Held:
        def __enter__(self):
            return False

        def __exit__(self, *_a):
            return None

    monkeypatch.setattr(cmd, "run_lock", Held)
    assert setup.run(args(take_file_all=True, yes=True)) == cmd.EXIT_TRY_LATER
    assert setup.applied == []
