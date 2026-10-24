import json
import unicodedata
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from rekordbox_smart_playlists.core import name_sync as ns

FIXTURE = Path(__file__).parent / "fixtures" / "name_fields.json"


def track(folder, name, artist="", album="", title="", **kw):
    return SimpleNamespace(
        ID=kw.pop("ID", name),
        FolderPath=str(folder / name),
        FileNameL=name,
        Artist=SimpleNamespace(Name=artist) if artist else None,
        Album=SimpleNamespace(Name=album) if album else None,
        ArtistID=None,
        AlbumID=None,
        Title=title,
        TrackInfoUpdated="3",
        rb_local_deleted=kw.pop("rb_local_deleted", 0),
    )


class FakeAnlz:
    def __init__(self, path):
        self.path = path
        self.saved = []

    def set_path(self, p):
        self.path = p

    def save(self, p):
        Path(p).write_text(self.path)
        self.saved.append(p)


class FakeDb:
    def __init__(self, anlz_dir=None):
        self.anlz_dir = anlz_dir
        self.commits = self.rollbacks = 0
        self.created = []
        self.fail_on_artist: str | None = None

    def get_or_create_artist(self, name):
        if name == self.fail_on_artist:
            raise RuntimeError("boom")
        self.created.append(("artist", name))
        return SimpleNamespace(ID=f"a:{name}")

    def get_or_create_album(self, name):
        self.created.append(("album", name))
        return SimpleNamespace(ID=f"al:{name}")

    def analysis_files(self, content_id):
        if not self.anlz_dir:
            return {}
        p = self.anlz_dir / f"{content_id}.DAT"
        if not p.exists():
            p.write_text("?/old")
        return {p: FakeAnlz("?/old")}

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def apply(db, writes, tmp_path, closed=lambda: None):
    discarded = []
    result = ns.apply_writes(
        db,
        writes,
        tmp_path / "journal",
        create_backup=lambda: tmp_path / "snap.db",
        discard_backup=discarded.append,
        assert_closed=closed,
        landed=lambda _w: False,
        now=lambda: datetime(2026, 10, 24, 12, 0, 0),
    )
    return result, discarded


def test_fields_match_the_shared_fixture():
    for case in json.loads(FIXTURE.read_text()):
        want = ns.Fields(case["artist"], case["album"], case["title"])
        assert ns.fields_from_stem(case["stem"]) == want, case["stem"]


def test_colons_and_stray_spaces_in_the_db_are_drift(tmp_path):
    t = track(
        tmp_path,
        "SPMC - Port Zero Shipment 3 - Hunted.aiff",
        "SP:MC",
        "Port Zero: Shipment 3",
        "Hunted ",
    )
    [drift] = ns.find_drift([t], tmp_path, frozenset()).drifted
    assert drift.changes() == [
        ("artist", "SP:MC", "SPMC"),
        ("album", "Port Zero: Shipment 3", "Port Zero Shipment 3"),
        ("title", "Hunted ", "Hunted"),
    ]


def test_the_same_text_in_another_unicode_form_is_not_drift(tmp_path):
    nfd = unicodedata.normalize("NFD", "dêtre")
    t = track(tmp_path, "dêtre - Lightspeed.mp3", nfd, "", "Lightspeed")
    assert ns.find_drift([t], tmp_path, frozenset()).drifted == []


def test_without_an_album_in_the_name_the_db_album_is_kept_unless_it_repeats(tmp_path):
    kept = track(tmp_path, "Nina - Uno.aiff", "Nina", "Uno Riddim", "Uno")
    repeats = track(tmp_path, "BALLADS - Good Flirts.mp3", "BALLADS", "ballads", "Good Flirts")
    unclean = track(
        tmp_path,
        "Perry Wayne - Ride or Die.mp3",
        "Perry Wayne",
        "Gud Vibrations: Vol 4",
        "Ride or Die",
    )
    report = ns.find_drift([kept, repeats, unclean], tmp_path, frozenset())
    assert {d.stem: d.target.album for d in report.drifted} == {
        "BALLADS - Good Flirts": "",
        "Perry Wayne - Ride or Die": "Gud Vibrations Vol 4",
    }


def test_deleted_rows_other_folders_and_holds_are_left_out(tmp_path):
    deleted = track(tmp_path, "A - B.mp3", "X", "", "B", rb_local_deleted=1)
    nested = track(tmp_path / "sub", "A - B.mp3", "X", "", "B")
    held = track(tmp_path, "C - D.mp3", "X", "", "D")
    report = ns.find_drift([deleted, nested, held], tmp_path, frozenset({"C - D"}))
    assert (report.scanned, report.drifted, [d.stem for d in report.held]) == (1, [], ["C - D"])


def test_name_from_db_builds_a_name_that_reads_back_the_same():
    assert ns.name_from_db(ns.Fields("En:vy", "", "TECC")) == "Envy - TECC"
    assert (
        ns.name_from_db(ns.Fields("CESCO x Drone", "cesco x drone", "El Guapo"))
        == "CESCO x Drone - El Guapo"
    )
    with pytest.raises(ns.SyncError, match="read back"):
        ns.name_from_db(ns.Fields("A - B", "", "T"))
    with pytest.raises(ns.SyncError, match="artist and a title"):
        ns.name_from_db(ns.Fields("", "", "T"))
    with pytest.raises(ns.SyncError, match="usable"):
        ns.name_from_db(ns.Fields("AC/DC", "", "T"))


def test_take_db_refuses_a_taken_name_and_a_shared_path(tmp_path):
    (tmp_path / "Old - T.mp3").write_text("")
    (tmp_path / "New - T.mp3").write_text("")
    t = track(tmp_path, "Old - T.mp3", "New", "", "T")
    with pytest.raises(ns.SyncError, match="already exists"):
        ns.plan_take_db(t, [t])
    twin = track(tmp_path, "Old - T.mp3", "New", "", "T", ID="other")
    with pytest.raises(ns.SyncError, match="share"):
        ns.plan_take_db(t, [t, twin])


def test_take_db_allows_a_case_only_rename_of_the_same_file(tmp_path):
    (tmp_path / "abc - T.mp3").write_text("")
    t = track(tmp_path, "abc - T.mp3", "ABC", "", "T")
    write = ns.plan_take_db(t, [t])
    if (tmp_path / "ABC - T.mp3").exists():  # case-insensitive file system
        assert write.new_path == tmp_path / "ABC - T.mp3"


def test_apply_renames_rewrites_analysis_paths_and_journals(tmp_path):
    (tmp_path / "Old - T.mp3").write_text("audio")
    t = track(tmp_path, "Old - T.mp3", "New", "", "T")
    db = FakeDb(anlz_dir=tmp_path)
    result, discarded = apply(db, [ns.plan_take_db(t, [t])], tmp_path)
    assert (tmp_path / "New - T.mp3").read_text() == "audio"
    assert (t.FileNameL, t.ArtistID, t.AlbumID, t.Title, t.TrackInfoUpdated) == (
        "New - T.mp3",
        "a:New",
        None,
        "T",
        "4",
    )
    assert (tmp_path / "Old - T.mp3.DAT").read_text() == "?/New - T.mp3"
    assert result.journal
    journal = json.loads(result.journal.read_text())
    assert journal["status"] == "committed"
    assert journal["rows"][0]["before"]["FileNameL"] == "Old - T.mp3"
    assert (db.commits, discarded) == (1, [])


def test_a_failure_mid_write_undoes_renames_and_analysis_files(tmp_path):
    (tmp_path / "Old - T.mp3").write_text("audio")
    (tmp_path / "Two - T.mp3").write_text("audio")
    first = track(tmp_path, "Old - T.mp3", "New", "", "T")
    second = track(tmp_path, "Two - T.mp3", "Boom", "", "T")
    db = FakeDb(anlz_dir=tmp_path)
    db.fail_on_artist = "Boom"
    writes = [ns.plan_take_db(first, [first]), ns.Write(second, ns.Fields("Boom", "", "T"))]
    with pytest.raises(RuntimeError):
        apply(db, writes, tmp_path)
    assert (tmp_path / "Old - T.mp3").exists() and not (tmp_path / "New - T.mp3").exists()
    assert (tmp_path / "Old - T.mp3.DAT").read_text() == "?/old"
    assert (db.commits, db.rollbacks) == (0, 1)
    assert (
        json.loads((tmp_path / "journal" / "20261024-120000" / "journal.json").read_text())[
            "status"
        ]
        == "failed"
    )


def test_rekordbox_opened_during_the_write_rolls_back_and_discards_the_snapshot(tmp_path):
    t = track(tmp_path, "A - T.mp3", "B", "", "T")
    calls = []

    def closed():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Rekordbox is running")

    db = FakeDb()
    discarded = []
    with pytest.raises(RuntimeError, match="running"):
        ns.apply_writes(
            db,
            [ns.Write(t, ns.Fields("A", "", "T"))],
            tmp_path / "journal",
            create_backup=lambda: tmp_path / "snap.db",
            discard_backup=discarded.append,
            assert_closed=closed,
            landed=lambda _w: False,
        )
    assert (db.commits, db.rollbacks, discarded) == (0, 1, [tmp_path / "snap.db"])


def test_nothing_to_write_touches_nothing(tmp_path):
    result, _ = apply(FakeDb(), [], tmp_path)
    assert result.journal is None and not (tmp_path / "journal").exists()


def test_a_file_that_appears_after_planning_is_never_overwritten(tmp_path):
    (tmp_path / "Old - T.mp3").write_text("mine")
    t = track(tmp_path, "Old - T.mp3", "New", "", "T")
    write = ns.plan_take_db(t, [t])
    (tmp_path / "New - T.mp3").write_text("someone else's")
    with pytest.raises(ns.SyncError, match="appeared"):
        apply(FakeDb(), [write], tmp_path)
    assert (tmp_path / "New - T.mp3").read_text() == "someone else's"
    assert (tmp_path / "Old - T.mp3").read_text() == "mine"


def test_a_run_in_the_same_second_leaves_the_earlier_journal_alone(tmp_path):
    earlier = tmp_path / "journal" / "20261024-120000" / "journal.json"
    earlier.parent.mkdir(parents=True)
    earlier.write_text(json.dumps({"status": "committed"}))
    t = track(tmp_path, "A - T.mp3", "B", "", "T")
    with pytest.raises(FileExistsError):
        apply(FakeDb(), [ns.Write(t, ns.Fields("A", "", "T"))], tmp_path)
    assert json.loads(earlier.read_text())["status"] == "committed"


def test_a_commit_that_landed_before_failing_keeps_the_renamed_files(tmp_path):
    (tmp_path / "Old - T.mp3").write_text("audio")
    t = track(tmp_path, "Old - T.mp3", "New", "", "T")
    db = FakeDb()

    def commit():
        raise RuntimeError("playlist xml")

    db.commit = commit
    with pytest.raises(RuntimeError, match="xml"):
        ns.apply_writes(
            db,
            [ns.plan_take_db(t, [t])],
            tmp_path / "journal",
            create_backup=lambda: tmp_path / "snap.db",
            discard_backup=lambda _p: None,
            assert_closed=lambda: None,
            landed=lambda _w: True,
            now=lambda: datetime(2026, 10, 24, 12, 0, 0),
        )
    assert (tmp_path / "New - T.mp3").exists()
    journal = tmp_path / "journal" / "20261024-120000" / "journal.json"
    assert json.loads(journal.read_text())["status"] == "committed"


def test_names_differing_only_in_case_count_as_the_same_target(tmp_path):
    a = ns.Write(None, ns.Fields("", "", ""), tmp_path / "Foo - Bar.mp3")
    b = ns.Write(None, ns.Fields("", "", ""), tmp_path / "foo - bar.mp3")
    assert len(ns.duplicate_targets([a, b])) == 1


def test_a_name_that_reads_as_a_flag_or_holds_control_characters_is_refused():
    for artist in ("-rf", "A\x1b[31m"):
        with pytest.raises(ns.SyncError, match="usable"):
            ns.name_from_db(ns.Fields(artist, "", "T"))
