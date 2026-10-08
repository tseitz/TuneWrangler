from types import SimpleNamespace

from rekordbox_smart_playlists.core.database import RekordboxDatabase
from rekordbox_smart_playlists.tagging.library import AUTOTAG_MARKER, Track, in_training_pool


class RealShapedDb:
    """Mirrors pyrekordbox: filtering by ID returns the row or None, never a query."""

    def __init__(self):
        self.content = {"7": SimpleNamespace(ID="7", TrackInfoUpdated="3")}
        self.song_tags = {"r1": SimpleNamespace(ID="r1")}
        self.added = []

    def get_content(self, **kw):
        return self.content.get(kw["ID"])

    def get_my_tag_songs(self, **kw):
        return self.song_tags.get(kw["ID"])

    def add(self, row):
        self.added.append(row)


def _db():
    db = RekordboxDatabase.__new__(RekordboxDatabase)
    db._db = RealShapedDb()
    db._is_connected = True
    return db


def test_get_track_and_get_song_tag_handle_row_or_none():
    db = _db()
    assert db.get_track("7").ID == "7"
    assert db.get_track("nope") is None
    assert db.get_song_tag("r1").ID == "r1"
    assert db.get_song_tag("nope") is None


def test_mark_track_info_updated_increments_the_varchar_counter():
    db = _db()
    db.mark_track_info_updated("7")
    assert db._db.content["7"].TrackInfoUpdated == "4"


def test_add_song_tag_goes_through_pyrekordbox_add():
    db = _db()
    row_id = db.add_song_tag("7", "123")
    (row,) = db._db.added
    assert row.ID == row_id and row.ContentID == "7" and row.MyTagID == "123"
    assert row.TrackNo is None and row.UUID != row.ID


def _track(tags, raw):
    return Track("1", "/m/1", "a", frozenset({"a"}), "a", "t", 140.0, 1, frozenset(tags), "a",
                 frozenset(raw))


def test_unreviewed_autotagged_tracks_stay_out_of_training():
    assert in_training_pool(_track({"Dub"}, {"Dub"}))
    assert not in_training_pool(_track({"Dub"}, {"Dub", AUTOTAG_MARKER}))
    assert not in_training_pool(_track(set(), {"Daytime"}))
