import dataclasses
import json

import pytest

from rekordbox_smart_playlists.tagging import manifest as mf


def _entry(cid="1", **kw):
    base = dict(
        content_id=cid,
        artist="A",
        title="T",
        bpm=140.0,
        top_styles=[("Halftime", 0.5)],
        suggestions=[mf.Suggestion("House", 0.9, 0.85, "random", "apply")],
        proposed=["House"],
        decision="apply",
    )
    return mf.Entry(**{**base, **kw})


def _manifest(entries=None, **kw):
    base = dict(
        created_at="2026-10-08T10:00:00",
        vocabulary_hash=mf.vocabulary_hash(frozenset({"House", "Dub"})),
        thresholds={"review": 0.5, "apply": 0.8},
        note="n",
        entries=entries if entries is not None else [_entry()],
    )
    return mf.Manifest(**{**base, **kw})


def test_round_trip(tmp_path):
    m = _manifest([_entry("1"), _entry("2", proposed=[], decision="review")])
    path = tmp_path / "sub" / "m.json"
    mf.write_manifest(m, path)
    assert mf.read_manifest(path) == m


def test_vocabulary_hash_ignores_order_and_tracks_content():
    assert mf.vocabulary_hash(frozenset({"a", "b"})) == mf.vocabulary_hash(frozenset({"b", "a"}))
    assert mf.vocabulary_hash(frozenset({"a"})) != mf.vocabulary_hash(frozenset({"a", "b"}))


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (_manifest(version=2), "version"),
        (_manifest([_entry("1"), _entry("1")]), "duplicate content_id"),
        (_manifest([_entry(decision="maybe")]), "decision"),
        (_manifest([_entry(proposed=["House", "House"])]), "duplicate tags"),
        (_manifest(vocabulary_hash=""), "vocabulary_hash"),
        (
            _manifest([_entry(suggestions=[mf.Suggestion("House", 1, 1, "random", "later")])]),
            "suggestion",
        ),
        (
            _manifest([_entry(suggestions=[mf.Suggestion("House", 1, 1, "weird", "apply")])]),
            "split",
        ),
    ],
)
def test_validation_errors(manifest, message):
    with pytest.raises(mf.ManifestError, match=message):
        mf.validate(manifest)


def test_read_rejects_violations_and_malformed_files(tmp_path):
    good = tmp_path / "good.json"
    mf.write_manifest(_manifest(), good)
    raw = json.loads(good.read_text())

    raw["version"] = 9
    bad_version = tmp_path / "v.json"
    bad_version.write_text(json.dumps(raw))
    with pytest.raises(mf.ManifestError, match="version"):
        mf.read_manifest(bad_version)

    raw["version"] = 1
    raw["entries"].append(raw["entries"][0])
    dup = tmp_path / "d.json"
    dup.write_text(json.dumps(raw))
    with pytest.raises(mf.ManifestError, match="duplicate content_id"):
        mf.read_manifest(dup)

    del raw["entries"][0]["title"]
    missing = tmp_path / "m.json"
    missing.write_text(json.dumps(raw))
    with pytest.raises(mf.ManifestError, match="malformed"):
        mf.read_manifest(missing)

    garbage = tmp_path / "g.json"
    garbage.write_text("{nope")
    with pytest.raises(mf.ManifestError, match="malformed"):
        mf.read_manifest(garbage)


def test_write_refuses_invalid_manifest(tmp_path):
    path = tmp_path / "x.json"
    with pytest.raises(mf.ManifestError):
        mf.write_manifest(dataclasses.replace(_manifest(), version=0), path)
    assert not path.exists()
