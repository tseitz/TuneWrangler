import os
from types import SimpleNamespace

import numpy as np
import pytest

from rekordbox_smart_playlists.tagging import embed as emb
from rekordbox_smart_playlists.tagging import library as lib
from rekordbox_smart_playlists.tagging import models

LANES = {
    "data": {
        "playlists": [
            {"name": "All", "contains": []},
            {"name": "House", "contains": ["House"]},
            {"name": "Dub Groovy", "contains": ["Dub", "GROOVY"]},
            {"name": "Weapons", "contains": ["Weapons"]},
            {"name": "Hits", "contains": ["Party Hits", "Dub Trippy/Interesting"]},
        ]
    }
}


class FakeDb:
    def __init__(self, rows):
        self.rows = rows

    def get_content(self):
        return self.rows


def row(id_, path="/m/a.aiff", artist="A", tags=(), deleted=0, length=100, bpm=12800):
    return SimpleNamespace(
        ID=id_,
        FolderPath=path,
        ArtistName=artist,
        Title="T",
        BPM=bpm,
        Length=length,
        MyTagNames=list(tags),
        rb_local_deleted=deleted,
    )


def test_vocabulary_drops_excluded_and_empty():
    assert lib.vocabulary(LANES) == {"House", "Dub", "GROOVY", "Dub Trippy/Interesting"}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Café Del Mar", ["cafe del mar"]),
        ("A, B & C", ["a", "b", "c"]),
        ("A x B", ["a", "b"]),
        ("A feat. B", ["a", "b"]),
        ("A ft. B", ["a", "b"]),
        ("Max", ["max"]),
        ("", []),
        (None, []),
    ],
)
def test_split_artists(name, expected):
    assert lib.split_artists(name) == expected


def test_load_library_filters_and_copies_fields():
    vocab = lib.vocabulary(LANES)
    rows = [
        row(1, tags=["House", "Weapons", "Other"], artist="Zed & Amy"),
        row(2, tags=["House", "Archive"]),
        row(3, path="/m/gone.aiff"),
        row(4, path="/Users/x/Music/rekordbox/Sampler/kick.wav"),
        row(5, deleted=1),
        row(6, artist=""),
    ]
    tracks = lib.load_library(FakeDb(rows), vocab, exists=lambda p: "gone" not in p)
    assert [t.content_id for t in tracks] == ["1", "6"]
    first, blank = tracks
    assert first.tags == {"House"}
    assert first.artists == {"zed", "amy"}
    assert first.group == "zed"
    assert first.bpm == 128.0
    assert blank.group == "__none__6"
    assert blank.artists == {"__none__6"}


def track(content_id="1", path="/m/a.aiff", length=100):
    return lib.Track(content_id, path, "A", frozenset({"a"}), "a", "T", 128.0, length, frozenset())


CLASSES = [f"style{i}" for i in range(emb.N_STYLES)]


def fake_embed(calls):
    def embed(path):
        calls.append(path)
        if "bad" in path:
            raise RuntimeError("decode failed")
        return np.ones(emb.EFFNET_DIM), np.full(emb.N_STYLES, 0.5), 0.25

    return embed


def test_cache_skips_cached_then_invalidates_on_path_or_length(tmp_path):
    calls: list[str] = []
    cache = emb.EmbeddingCache(tmp_path, CLASSES)
    summary = emb.run_embed([track()], cache, fake_embed(calls))
    assert (summary.embedded, summary.cached) == (1, 0)

    reloaded = emb.EmbeddingCache(tmp_path, CLASSES)
    summary = emb.run_embed([track()], reloaded, fake_embed(calls))
    assert (summary.embedded, summary.cached) == (0, 1)
    assert len(calls) == 1
    assert reloaded.entries["1"].voice == 0.25

    emb.run_embed([track(length=101)], reloaded, fake_embed(calls))
    emb.run_embed([track(length=101, path="/m/b.aiff")], reloaded, fake_embed(calls))
    assert len(calls) == 3


def test_mtime_change_does_not_invalidate(tmp_path):
    audio = tmp_path / "a.aiff"
    audio.write_bytes(b"x")
    calls: list[str] = []
    cache = emb.EmbeddingCache(tmp_path / "cache", CLASSES)
    t = track(path=str(audio))
    emb.run_embed([t], cache, fake_embed(calls))
    audio.write_bytes(b"much longer rewritten tags")
    os.utime(audio, (1, 1))
    summary = emb.run_embed([t], cache, fake_embed(calls))
    assert summary.cached == 1 and len(calls) == 1


def test_failures_recorded_not_retried_and_counted_by_extension(tmp_path):
    calls: list[str] = []
    bad = track("2", "/m/bad.m4a")
    cache = emb.EmbeddingCache(tmp_path, CLASSES)
    summary = emb.run_embed([track(), bad], cache, fake_embed(calls))
    assert summary.failed == 1
    assert summary.failures_by_extension() == {".m4a": 1}
    assert ".m4a: 1" in summary.render()

    cache = emb.EmbeddingCache(tmp_path, CLASSES)
    assert cache.entries["2"].error == "RuntimeError: decode failed"
    summary = emb.run_embed([track(), bad], cache, fake_embed(calls))
    assert (summary.cached, summary.failed) == (2, 0)
    summary = emb.run_embed([track(), bad], cache, fake_embed(calls), retry_failed=True)
    assert summary.failed == 1 and summary.cached == 1


def test_limit_considers_first_n_tracks(tmp_path):
    cache = emb.EmbeddingCache(tmp_path, CLASSES)
    tracks = [track(str(i), f"/m/{i}.aiff") for i in range(5)]
    summary = emb.run_embed(tracks, cache, fake_embed([]), limit=2)
    assert (summary.total, summary.embedded) == (2, 2)


def test_class_name_mismatch_fails_loudly(tmp_path):
    emb.run_embed([track()], emb.EmbeddingCache(tmp_path, CLASSES), fake_embed([]))
    with pytest.raises(emb.ClassNameMismatchError):
        emb.EmbeddingCache(tmp_path, [*CLASSES[:-1], "other"])
    with pytest.raises(emb.ClassNameMismatchError):
        emb.EmbeddingCache(tmp_path, CLASSES[:10])


def test_model_hash_mismatch_fails_loudly(tmp_path):
    (tmp_path / models.GENRE_META.name).write_text("tampered")
    with pytest.raises(models.ModelIntegrityError):
        models.verify(tmp_path / models.GENRE_META.name, models.GENRE_META)
