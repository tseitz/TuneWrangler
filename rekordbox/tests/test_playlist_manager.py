import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rekordbox_smart_playlists.cli import commands
from rekordbox_smart_playlists.core.config import Config
from rekordbox_smart_playlists.core.database import (
    DatabaseError,
    DatabaseQueryError,
    RegularPlaylistInTreeError,
    RekordboxDatabase,
)
from rekordbox_smart_playlists.core.playlist_manager import (
    PlaylistCreationResult,
    PlaylistManager,
)

TAG, CATEGORY = 0, 1


def _tag(tag_id: int, name: str, attribute: int = TAG) -> SimpleNamespace:
    return SimpleNamespace(ID=str(tag_id), Name=name, Attribute=attribute)


class FakeDb:
    def __init__(self, tags, counts=None):
        self.tags = tags
        self.counts = counts or {}
        self.created: list[str] = []

    def get_tags(self):
        return self.tags

    def get_playlist_by_name(self, name, parent_id=None):
        return SimpleNamespace(ID="root", Name=name) if parent_id is None else None

    def create_playlist_folder(self, name, parent, sequence=None):
        return SimpleNamespace(ID=name, Name=name)

    def count_smart_list(self, smart_list):
        return self.counts.get(len(smart_list.conditions), 0)

    def create_smart_playlist(self, name, smart_list, parent):
        self.created.append(name)
        return SimpleNamespace(Name=name)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _root(parent, main, **extra):
    return {
        "data": [
            {
                "parent": parent,
                "mainConditions": main,
                "negativeConditions": ["Archive"],
                "base": "helpers/_lanes.json",
                "playlists": [],
                **extra,
            }
        ]
    }


def _lanes(*playlists):
    return {"data": {"playlists": list(playlists)}}


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    _write(
        tmp_path / "helpers/_lanes.json",
        _lanes(
            {"name": "All", "operator": 1, "contains": []},
            {
                "name": "Dub Deep",
                "operator": 1,
                "contains": ["Dub"],
                "doesNotContain": ["GROOVY"],
                "minTracks": 10,
            },
        ),
    )
    _write(tmp_path / "daytime.json", _root("Daytime", ["Daytime"]))
    return tmp_path


def _manager(data_dir: Path, tags, counts=None) -> tuple[PlaylistManager, FakeDb]:
    db = FakeDb(tags, counts)
    config = Config(playlist_data_path=str(data_dir))
    return PlaylistManager(db, config), db  # ty: ignore[invalid-argument-type]


ALL_TAGS = [
    _tag(1, "Daytime"),
    _tag(2, "Archive"),
    _tag(3, "Dub"),
    _tag(4, "GROOVY"),
    _tag(5, "Weapons"),
]


def test_preflight_passes_on_known_tags(data_dir):
    assert _manager(data_dir, ALL_TAGS)[0].preflight() == []


def test_preflight_reports_unknown_tag(data_dir):
    tags = [t for t in ALL_TAGS if t.Name != "GROOVY"]

    assert _manager(data_dir, tags)[0].preflight() == ["Tag not found: GROOVY"]


def test_preflight_ignores_category_rows_and_flags_duplicate_tags(data_dir):
    tags = [*ALL_TAGS, _tag(9, "Dub", CATEGORY), _tag(10, "GROOVY")]

    assert _manager(data_dir, tags)[0].preflight() == [
        "Tag name matches more than one tag: GROOVY"
    ]


def test_preflight_validates_base_file_items(data_dir):
    _write(
        data_dir / "helpers/_lanes.json",
        _lanes({"name": "Dub", "operator": 2, "contains": ["Dub"], "doesNotContain": ["GROOVY"]}),
    )

    errors = _manager(data_dir, ALL_TAGS)[0].preflight()

    assert any("'doesNotContain' needs operator 1" in e for e in errors)


def test_preflight_reports_missing_base(data_dir):
    (data_dir / "helpers/_lanes.json").unlink()

    errors = _manager(data_dir, ALL_TAGS)[0].preflight()

    assert any("Missing base file" in e for e in errors)


def _create(manager: PlaylistManager, data_dir: Path, name: str) -> list[PlaylistCreationResult]:
    return manager.create_playlists_from_file(data_dir / name)


def test_lane_below_min_tracks_is_skipped(data_dir):
    # Daytime + Dub + NOT Archive + NOT GROOVY = 4 conditions
    manager, db = _manager(data_dir, ALL_TAGS, counts={4: 9})

    results = _create(manager, data_dir, "daytime.json")

    lane = next(r for r in results if r.playlist_name == "Dub Deep")
    assert lane.success and lane.skipped
    assert lane.skip_reason == "Daytime: 9 tracks < minTracks 10"
    assert db.created == ["All"]


def test_lane_at_min_tracks_is_created(data_dir):
    manager, db = _manager(data_dir, ALL_TAGS, counts={4: 10})

    _create(manager, data_dir, "daytime.json")

    assert db.created == ["All", "Dub Deep"]


def test_root_min_tracks_overrides_the_lane(data_dir):
    _write(data_dir / "daytime.json", _root("Daytime", ["Daytime"], minTracks=1))
    manager, db = _manager(data_dir, ALL_TAGS, counts={4: 2})

    _create(manager, data_dir, "daytime.json")

    assert db.created == ["All", "Dub Deep"]


def test_lane_matching_the_root_tag_is_skipped(data_dir):
    _write(
        data_dir / "helpers/_lanes.json",
        _lanes(
            {"name": "All", "operator": 1, "contains": []},
            {"name": "Weapons", "operator": 1, "contains": ["Weapons"]},
        ),
    )
    _write(data_dir / "weapons.json", _root("Weapons", ["Weapons"]))
    manager, db = _manager(data_dir, ALL_TAGS)

    results = _create(manager, data_dir, "weapons.json")

    assert db.created == ["All"]
    assert any(r.skip_reason == "Weapons: same tracks as All" for r in results)


class FakePyrekordbox:
    def __init__(self, children):
        self.children = children
        self.deleted: list[str] = []

    def delete_playlist(self, playlist):
        self.deleted.append(playlist.Name)


def _wrapper(children) -> tuple[RekordboxDatabase, FakePyrekordbox]:
    fake = FakePyrekordbox(children)
    db = object.__new__(RekordboxDatabase)
    db._db = fake  # ty: ignore[invalid-assignment]
    db._is_connected = True
    db.get_children_playlists = lambda parent_id: children.get(parent_id, [])  # ty: ignore[invalid-assignment]
    db.get_playlists = lambda ParentID: children.get(ParentID, [])  # ty: ignore[invalid-assignment]
    return db, fake


def _pl(pid: str, name: str, attribute: int) -> SimpleNamespace:
    return SimpleNamespace(ID=pid, Name=name, Attribute=attribute)


def test_delete_refuses_a_tree_holding_a_regular_playlist():
    root = _pl("1", "Daytime", 1)
    db, fake = _wrapper({"1": [_pl("2", "All", 4), _pl("3", "Hand Picked", 0)]})

    with pytest.raises(RegularPlaylistInTreeError, match="Hand Picked"):
        db.delete_playlist_recursive(root)
    assert fake.deleted == []


def test_delete_removes_a_generated_tree_in_one_call():
    root = _pl("1", "Daytime", 1)
    db, fake = _wrapper({"1": [_pl("2", "All", 4), _pl("3", "Lane", 4)]})

    assert db.delete_playlist_recursive(root) == 3
    assert fake.deleted == ["Daytime"]


def test_a_failed_delete_raises_instead_of_returning_quietly():
    root = _pl("1", "Daytime", 1)
    db, fake = _wrapper({"1": []})

    def boom(playlist):
        raise RuntimeError("locked")

    fake.delete_playlist = boom  # ty: ignore[invalid-assignment]

    with pytest.raises(DatabaseError, match="locked"):
        db.delete_playlist_recursive(root)


def test_guard_refuses_when_it_cannot_read_the_tree():
    root = _pl("1", "Daytime", 1)
    db, fake = _wrapper({"1": []})

    def unreadable(ParentID):
        raise DatabaseQueryError("locked")

    db.get_playlists = unreadable  # ty: ignore[invalid-assignment]

    with pytest.raises(DatabaseQueryError):
        db.delete_playlist_recursive(root)
    assert fake.deleted == []


class FakeSession:
    def __init__(self):
        self.calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self):
        self.calls.append("commit")

    def rollback(self):
        self.calls.append("rollback")


def _run_create(monkeypatch, results, preflight_errors=()):
    session = FakeSession()
    manager = SimpleNamespace(
        existing_strategy=None,
        preflight=lambda config_file: list(preflight_errors),
        find_existing_root_folders=lambda config_file: [],
        create_playlists_from_directory=lambda directory: results,
    )
    monkeypatch.setattr(commands, "RekordboxDatabase", lambda config: session)
    monkeypatch.setattr(commands, "PlaylistManager", lambda db, config: manager)
    command = commands.PlaylistCommand(Config(backup_before_changes=False))
    args = argparse.Namespace(file=None, skip_backup=True, existing="overwrite")
    return command._create_playlists(args), session.calls


def test_any_failed_playlist_rolls_back_the_run(monkeypatch):
    results = [
        PlaylistCreationResult(success=True, playlist_name="All"),
        PlaylistCreationResult(success=False, playlist_name="Dub Deep", error_message="boom"),
    ]

    code, calls = _run_create(monkeypatch, results)

    assert code == 1
    assert calls == ["rollback"]


def test_clean_run_commits(monkeypatch):
    code, calls = _run_create(monkeypatch, [PlaylistCreationResult(True, "All")])

    assert code == 0
    assert calls == ["commit"]


def test_preflight_failure_stops_before_any_change(monkeypatch):
    code, calls = _run_create(monkeypatch, [], preflight_errors=["Tag not found: X"])

    assert code == 1
    assert calls == []
