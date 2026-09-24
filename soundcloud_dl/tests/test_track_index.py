"""The index of what SoundCloud reported for each downloaded file."""

import json
import unicodedata

from soundcloud_dl import track_index

FIELDS = {
    "url": "https://soundcloud.com/mousai/ball-so-hard",
    "title": "BALL SO HARD (Mousai & UrBoiN8)",
    "uploader": "MOUSAI",
    "metadata_artist": "MOUSAI & Urboin8",
    "label_name": None,
}


def _read() -> dict:
    return json.loads(track_index.get_track_index_file().read_text(encoding="utf-8"))


def test_a_track_is_recorded_under_its_filename() -> None:
    track_index.record_track("MOUSAI - BALL SO HARD (Mousai & UrBoiN8)", **FIELDS)
    assert _read() == {"MOUSAI - BALL SO HARD (Mousai & UrBoiN8)": FIELDS}


def test_recording_again_replaces_the_entry_and_keeps_the_others() -> None:
    track_index.record_track("A - One", **FIELDS)
    track_index.record_track("B - Two", **FIELDS)
    track_index.record_track("A - One", **{**FIELDS, "label_name": "Label"})
    data = _read()
    assert set(data) == {"A - One", "B - Two"}
    assert data["A - One"]["label_name"] == "Label"


def test_the_key_is_nfc_so_a_decomposed_name_finds_it() -> None:
    track_index.record_track(unicodedata.normalize("NFD", "Dr. Ushūu - Long Goodbye"), **FIELDS)
    assert list(_read()) == [unicodedata.normalize("NFC", "Dr. Ushūu - Long Goodbye")]


def test_an_unreadable_index_is_moved_aside_not_overwritten() -> None:
    path = track_index.get_track_index_file()
    path.write_text("{half written", encoding="utf-8")
    track_index.record_track("A - One", **FIELDS)
    assert list(_read()) == ["A - One"]
    aside = list(path.parent.glob("track_index.corrupt-*.json"))
    assert len(aside) == 1
    assert aside[0].read_text(encoding="utf-8") == "{half written"


def test_an_unusable_log_dir_does_not_raise(monkeypatch) -> None:
    def _boom():
        raise PermissionError("read-only")

    monkeypatch.setattr(track_index, "get_track_index_file", _boom)
    track_index.record_track("A - One", **FIELDS)
