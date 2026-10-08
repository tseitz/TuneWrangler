import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from rekordbox_smart_playlists.tagging import apply as ap
from rekordbox_smart_playlists.tagging import manifest as mf

VOCAB = frozenset({"Dub", "House", "WEIRD", "GROOVY", "Halftime"})
TAGS = {"Dub": "1", "House": "2", "Experimental Bass": "3", "Halftime": "4", "Autotagged": "9"}


class FakeDb:
    def __init__(self, contents):
        self.contents = contents
        self.rows: dict[str, SimpleNamespace] = {}
        self.pending: list[SimpleNamespace] = []
        self.deleted: list[str] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_on_add = False

    def get_tags(self, Name):  # noqa: N803
        return [SimpleNamespace(ID=TAGS[Name], Attribute=0)] if Name in TAGS else []

    def get_track(self, content_id):
        return self.contents.get(content_id)

    def add_song_tag(self, content_id, tag_id):
        if self.fail_on_add:
            raise RuntimeError("boom")
        row = SimpleNamespace(
            ID=f"r{len(self.rows) + len(self.pending)}",
            ContentID=content_id,
            MyTagID=tag_id,
            rb_local_deleted=0,
        )
        self.pending.append(row)
        return row.ID

    def mark_track_info_updated(self, content_id):
        c = self.contents[content_id]
        c.TrackInfoUpdated = str(int(c.TrackInfoUpdated) + 1)

    def commit(self):
        if getattr(self, "fail_on_commit", False):
            raise RuntimeError("commit failed")
        self.commits += 1
        self.rows.update({r.ID: r for r in self.pending})
        self.pending.clear()

    def rollback(self):
        self.rollbacks += 1
        self.pending.clear()

    def get_song_tag(self, row_id):
        return self.rows.get(row_id)

    def delete_song_tag(self, row):
        self.deleted.append(row.ID)
        del self.rows[row.ID]


def _content(tags=(), deleted=0):
    return SimpleNamespace(MyTagNames=list(tags), rb_local_deleted=deleted, TrackInfoUpdated="3")


def _entry(cid, proposed, decision="apply"):
    return mf.Entry(cid, "a", "t", 140.0, [], [], list(proposed), decision)


def _manifest(entries, vocab=VOCAB):
    return mf.Manifest("2026-10-08T00:00:00", mf.vocabulary_hash(vocab), {}, "note", entries)


def _run(db, manifest, tmp_path, *, dry_run=False, selection=None, backup="ok", closed=None):
    path = tmp_path / "tag-manifest-x.json"
    calls = []

    def assert_closed():
        calls.append("closed")
        if closed:
            closed()

    result = ap.apply_manifest(
        db,
        manifest,
        path,
        VOCAB,
        selection or ap.Selection(),
        create_backup=lambda: calls.append("backup") or backup,
        assert_closed=assert_closed,
        dry_run=dry_run,
        now=lambda: datetime(2026, 10, 8, 12, 0, 0),
    )
    return result, calls


def test_apply_adds_proposed_tags_and_marker_then_logs_row_ids(tmp_path):
    db = FakeDb({"1": _content(["Daytime"])})
    result, calls = _run(db, _manifest([_entry("1", ["Dub", "Experimental Bass"])]), tmp_path)
    assert calls == ["closed", "backup", "closed"]
    assert db.commits == 1
    assert sorted((r.MyTagID for r in db.rows.values())) == ["1", "3", "9"]
    assert db.contents["1"].TrackInfoUpdated == "4"
    log = json.loads(result.log_path.read_text())
    assert {r["tag"] for r in log["rows"]} == {"Dub", "Experimental Bass", "Autotagged"}
    assert {r["id"] for r in log["rows"]} == set(db.rows)


def test_tracks_tagged_since_suggest_archived_or_deleted_are_skipped(tmp_path):
    db = FakeDb(
        {
            "lane": _content(["GROOVY"]),
            "eb": _content(["Experimental Bass"]),
            "arch": _content(["Archive"]),
            "weapon": _content(["Weapons"]),
            "auto": _content(["Autotagged"]),
            "gone": _content(deleted=1),
        }
    )
    entries = [
        _entry(c, ["Dub"]) for c in ("lane", "eb", "arch", "weapon", "auto", "gone", "missing")
    ]
    result, _ = _run(db, _manifest(entries), tmp_path)
    assert result.writes == []
    assert dict(result.skipped) == {
        "lane": "has lane tags now",
        "eb": "has lane tags now",
        "arch": "archived or curated since suggest",
        "weapon": "archived or curated since suggest",
        "auto": "already autotagged",
        "gone": "track missing",
        "missing": "track missing",
    }
    assert db.commits == 0


def test_validation_refuses_before_any_write(tmp_path):
    db = FakeDb({"1": _content()})
    with pytest.raises(ap.ApplyError, match="may not write"):
        _run(db, _manifest([_entry("1", ["WEIRD"])]), tmp_path)
    with pytest.raises(ap.ApplyError, match="lane tags changed"):
        _run(db, _manifest([_entry("1", ["Dub"])], vocab=VOCAB | {"Feels"}), tmp_path)
    with pytest.raises(ap.ApplyError, match="matches 0 tags"):
        _run(db, _manifest([_entry("1", ["Riddim"])]), tmp_path)
    assert db.pending == [] and db.commits == 0


def test_failure_mid_write_rolls_back(tmp_path):
    db = FakeDb({"1": _content()})
    db.fail_on_add = True
    with pytest.raises(RuntimeError):
        _run(db, _manifest([_entry("1", ["Dub"])]), tmp_path)
    assert db.rollbacks == 1 and db.commits == 0 and db.rows == {}


def test_rekordbox_opened_during_backup_rolls_back(tmp_path):
    db = FakeDb({"1": _content()})
    state = {"n": 0}

    def closed():
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("Rekordbox is running")

    with pytest.raises(RuntimeError, match="running"):
        _run(db, _manifest([_entry("1", ["Dub"])]), tmp_path, closed=closed)
    assert db.commits == 0 and db.rollbacks == 1


def test_backup_failure_aborts(tmp_path):
    db = FakeDb({"1": _content()})
    with pytest.raises(ap.ApplyError, match="backup failed"):
        _run(db, _manifest([_entry("1", ["Dub"])]), tmp_path, backup=None)
    assert db.pending == [] and db.commits == 0


def test_dry_run_writes_nothing(tmp_path):
    db = FakeDb({"1": _content()})
    result, calls = _run(db, _manifest([_entry("1", ["Dub"])]), tmp_path, dry_run=True)
    assert result.writes == [("1", ["Dub", "Autotagged"])]
    assert calls == [] and db.pending == [] and db.commits == 0 and result.log_path is None


def test_selection_sample_is_seeded_and_only_picks_ids(tmp_path):
    entries = [_entry(str(i), ["Dub"]) for i in range(20)] + [_entry("r", ["Dub"], "review")]
    m = _manifest(entries)
    a = ap.select_entries(m, ap.Selection(sample=5, seed=1))
    b = ap.select_entries(m, ap.Selection(sample=5, seed=1))
    assert [e.content_id for e in a] == [e.content_id for e in b]
    assert len(a) == 5 and "r" not in {e.content_id for e in a}
    assert [e.content_id for e in ap.select_entries(m, ap.Selection(only=frozenset({"3"})))] == [
        "3"
    ]
    with pytest.raises(ap.ApplyError, match="not apply entries"):
        ap.select_entries(m, ap.Selection(only=frozenset({"r"})))


def test_undo_removes_exactly_logged_rows_still_unchanged(tmp_path):
    db = FakeDb({"1": _content(), "2": _content()})
    result, _ = _run(db, _manifest([_entry("1", ["Dub"]), _entry("2", ["House"])]), tmp_path)
    log = json.loads(result.log_path.read_text())
    user_row = SimpleNamespace(ID="user", ContentID="1", MyTagID="2", rb_local_deleted=0)
    db.rows["user"] = user_row
    dub_row = next(r for r in log["rows"] if r["tag"] == "Dub")
    db.rows[dub_row["id"]].MyTagID = "4"
    removed, gone = ap.undo(
        db,
        result.log_path,
        create_backup=lambda: "ok",
        assert_closed=lambda: None,
        dry_run=False,
    )
    assert set(removed) == {r["id"] for r in log["rows"]} - {dub_row["id"]}
    assert gone == [(dub_row["id"], "row changed since apply")]
    assert "user" in db.rows and db.commits == 2


def test_log_exists_before_commit_so_a_failed_commit_leaves_a_pending_log(tmp_path):
    db = FakeDb({"1": _content()})
    db.fail_on_commit = True
    with pytest.raises(RuntimeError, match="commit failed"):
        _run(db, _manifest([_entry("1", ["Dub"])]), tmp_path)
    logs = list(tmp_path.glob("*.applied-*.json"))
    assert len(logs) == 1
    log = json.loads(logs[0].read_text())
    assert log["status"] == "pending" and {r["tag"] for r in log["rows"]} == {"Dub", "Autotagged"}


def test_undo_leaves_reviewed_tracks_unless_forced(tmp_path):
    db = FakeDb({"1": _content(), "2": _content()})
    result, _ = _run(db, _manifest([_entry("1", ["Dub"]), _entry("2", ["House"])]), tmp_path)
    log = json.loads(result.log_path.read_text())
    marker_1 = next(r for r in log["rows"] if r["content_id"] == "1" and r["tag"] == "Autotagged")
    del db.rows[marker_1["id"]]

    def run(force):
        return ap.undo(
            db,
            result.log_path,
            create_backup=lambda: "ok",
            assert_closed=lambda: None,
            dry_run=True,
            force=force,
        )

    removed, gone = run(False)
    kept_dub = next(r["id"] for r in log["rows"] if r["content_id"] == "1" and r["tag"] == "Dub")
    assert kept_dub not in removed
    assert (kept_dub, "track reviewed since apply (marker removed)") in gone
    assert kept_dub in run(True)[0]


def test_malformed_undo_log_is_a_clear_error(tmp_path):
    bad = tmp_path / "x.applied-1.json"
    bad.write_text('{"rows": [{"id": "1"}]}')
    with pytest.raises(ap.ApplyError, match="not a readable apply log"):
        ap.undo(
            FakeDb({}), bad, create_backup=lambda: "ok", assert_closed=lambda: None, dry_run=True
        )
