import dataclasses
from datetime import datetime

import numpy as np
import pytest

from rekordbox_smart_playlists.tagging import manifest as mf
from rekordbox_smart_playlists.tagging import suggest as sg
from rekordbox_smart_playlists.tagging.library import Track

VOCAB = frozenset({"Dub", "Dubstep", "House", "Halftime", "WEIRD", "GROOVY"})


def _track(cid, tags, raw=None, artist="a"):
    tags = frozenset(tags)
    return Track(
        cid,
        f"/m/{cid}",
        artist,
        frozenset({artist}),
        artist,
        "T",
        140.0,
        100,
        tags & VOCAB,
        artist,
        frozenset(raw) if raw is not None else tags,
    )


def test_has_lane_tag_reads_raw_tags_including_experimental_bass():
    assert not sg.has_lane_tag(_track("1", [], raw=["Daytime", "Hip Hop"]), VOCAB)
    assert sg.has_lane_tag(_track("2", [], raw=["Experimental Bass"]), VOCAB)
    assert sg.has_lane_tag(_track("3", ["GROOVY"]), VOCAB)


def test_experimental_bass_stand_in_labels():
    pool = [
        _track("weird", ["WEIRD"]),
        _track("weird-halftime", ["WEIRD", "Halftime"]),
        _track("weird-dub", ["WEIRD", "Dub"]),
        _track("dub", ["Dub"]),
        _track("halftime", ["Halftime"]),
        _track("groovy-only", ["GROOVY"]),
    ]
    task = sg.experimental_bass_task(pool)
    labels = {pool[i].content_id: bool(y) for i, y in zip(task.universe, task.y, strict=True)}
    assert labels == {"weird": True, "weird-halftime": True, "dub": False}


def test_precision_curve_is_monotone_and_needs_min_support():
    rng = np.random.default_rng(0)
    scores = rng.random(200)
    y = scores + rng.normal(0, 0.3, 200) > 0.6
    y[np.argmax(scores)] = False
    curve = sg.precision_curve(scores, y)
    grid = np.linspace(-0.1, 1.1, 50)
    est = curve(grid)
    assert np.all(np.diff(est) >= -1e-12)
    top = np.sort(scores)[::-1]
    floor_value = y[np.argsort(-scores)][: sg.MIN_SUPPORT].mean()
    assert curve(np.array([np.inf]))[0] >= floor_value - 1e-12
    assert curve(np.array([top[0]]))[0] == curve(np.array([top[sg.MIN_SUPPORT - 1]]))[0]


def test_precision_curve_hand_example():
    scores = np.arange(40, 0, -1, dtype=float)
    y = np.array([True] * 30 + [False] * 10)
    curve = sg.precision_curve(scores, y)
    assert curve(np.array([40.0]))[0] == 1.0
    assert curve(np.array([1.0]))[0] == 0.75
    assert curve(np.array([0.0]))[0] == 0.75


def test_precision_curve_ignores_a_lucky_handful_at_the_top():
    scores = np.arange(100, 0, -1, dtype=float)
    y = np.array([True] * 5 + [False] * 95)
    curve = sg.precision_curve(scores, y)
    assert curve(np.array([100.0]))[0] == 5 / sg.MIN_SUPPORT


def _est(values, split="random"):
    v = np.array(values, dtype=float)
    return sg.TagEstimate(v, v, np.full(len(v), split))


def _assemble(tracks, estimates, styles, min_precision=0.8):
    return sg.assemble(
        tracks, estimates, styles, "h", min_precision, datetime(2026, 10, 8, 10, 0, 0)
    )


def _by_id(manifest):
    return {e.content_id: e for e in manifest.entries}


def test_min_precision_gates_proposed_and_review_band():
    tracks = [_track("hi", []), _track("mid", []), _track("lo", [])]
    est = {"House": _est([0.9, 0.6, 0.3])}
    styles = [[("House", 0.9)]] * 3
    manifest, stats = _assemble(tracks, est, styles)
    entries = _by_id(manifest)
    assert entries["hi"].proposed == ["House"] and entries["hi"].decision == "apply"
    assert entries["mid"].proposed == [] and entries["mid"].decision == "review"
    assert entries["mid"].suggestions[0].decision == "review"
    assert "lo" not in entries and stats.dropped_no_suggestion == 1

    manifest, _ = _assemble(tracks, est, styles, min_precision=0.5)
    assert _by_id(manifest)["mid"].proposed == ["House"]


def test_halftime_needs_experimental_bass_and_halftime_top_style():
    tracks = [_track(c, []) for c in ("both", "eb-only", "ht-only")]
    est = {sg.EXPERIMENTAL_BASS: _est([0.7, 0.7, 0.2])}
    styles = [[("Halftime", 0.5)], [("Dubstep", 0.5)], [("Halftime", 0.5)]]
    manifest, _ = _assemble(tracks, est, styles, min_precision=0.65)
    entries = _by_id(manifest)
    assert entries["both"].proposed == [sg.EXPERIMENTAL_BASS, sg.HALFTIME]
    assert entries["eb-only"].proposed == [sg.EXPERIMENTAL_BASS]
    assert "ht-only" not in entries


def test_halftime_not_added_when_experimental_bass_is_only_review():
    manifest, _ = _assemble(
        [_track("a", [])],
        {sg.EXPERIMENTAL_BASS: _est([0.6])},
        [[("Halftime", 0.5)]],
    )
    entry = _by_id(manifest)["a"]
    assert entry.proposed == []
    assert sg.HALFTIME not in {s.tag for s in entry.suggestions}


def test_hip_hop_top_style_sends_genre_tags_to_review():
    tracks = [_track("hh", []), _track("plain", [])]
    est = {"Dub": _est([0.95, 0.95]), "GROOVY": _est([0.9, 0.9])}
    styles = [[("Hip Hop---Trap", 0.6)], [("Reggae---Dub", 0.6)]]
    manifest, stats = _assemble(tracks, est, styles)
    entries = _by_id(manifest)
    assert entries["hh"].proposed == ["GROOVY"]
    assert {s.tag: s.decision for s in entries["hh"].suggestions} == {
        "Dub": "review",
        "GROOVY": "apply",
    }
    assert entries["plain"].proposed == ["Dub", "GROOVY"]
    assert stats.hiphop_downgrades == 1


def test_hip_hop_downgrade_leaves_entry_in_review_when_nothing_else_applies():
    manifest, _ = _assemble([_track("hh", [])], {"Dub": _est([0.95])}, [[("Hip Hop---Rap", 1)]])
    entry = _by_id(manifest)["hh"]
    assert entry.proposed == [] and entry.decision == "review"


def test_dnb_liquid_estimate_is_product_with_dnb():
    tracks = [_track("a", [], artist="a"), _track("b", [], artist="b")]
    pool_artists = frozenset({"a"})
    n = 40
    y = np.arange(n) % 2 == 0
    scores = np.linspace(0, 1, n)
    cals = [
        sg.Calibrated(tag, parent, y, scores, scores, np.array([0.5, 0.5]), np.array([0.5, 0.5]))
        for tag, parent in (("DnB", None), ("DnB Liquid", "DnB"))
    ]
    est = sg.tag_estimates(cals, tracks, pool_artists)
    dnb = est["DnB"].est
    assert np.allclose(est["DnB Liquid"].est, dnb * dnb)
    assert set(est["DnB Liquid"].split) == {"product"}
    assert est["DnB"].split.tolist() == ["random", "grouped"]


def test_candidate_without_pool_artist_reads_grouped_curve():
    n = 40
    y = np.arange(n) % 2 == 0
    pool_random = np.where(y, 1.0, 0.0)
    pool_grouped = np.linspace(0, 1, n)
    cal = sg.Calibrated(
        "House", None, y, pool_random, pool_grouped, np.array([0.99, 0.99]), np.array([0.99, 0.99])
    )
    tracks = [_track("known", [], artist="a"), _track("new", [], artist="z")]
    est = sg.estimated_precision(cal, tracks, frozenset({"a"}))
    assert est[0] == 1.0 and est[1] < 1.0


def test_newest_first_orders_by_added_with_missing_last():
    def at(cid, added):
        return dataclasses.replace(_track(cid, []), added=added)

    tracks = [
        at("old", datetime(2020, 1, 1)),
        at("none", None),
        at("new", datetime(2026, 1, 1)),
        at("mid", datetime(2023, 1, 1)),
    ]
    assert [t.content_id for t in sg.newest_first(tracks, None)] == ["new", "mid", "old", "none"]
    assert [t.content_id for t in sg.newest_first(tracks, 2)] == ["new", "mid"]


def test_experimental_bass_only_track_is_never_a_candidate():
    tracks = [_track("eb", [], raw=["Experimental Bass"]), _track("bare", [], raw=["Daytime"])]
    untagged = [t for t in tracks if not sg.has_lane_tag(t, VOCAB)]
    assert [t.content_id for t in untagged] == ["bare"]


def test_proposed_is_deduplicated_and_entries_sorted_apply_first():
    tracks = [_track("rev", []), _track("low", []), _track("top", [])]
    est = {"House": _est([0.6, 0.85, 0.95]), "GROOVY": _est([0.55, 0.85, 0.95])}
    manifest, _ = _assemble(tracks, est, [[("House", 1)]] * 3)
    assert [e.content_id for e in manifest.entries] == ["top", "low", "rev"]
    assert all(len(set(e.proposed)) == len(e.proposed) for e in manifest.entries)
    mf.validate(manifest)


def test_suggest_refuses_an_empty_library():
    with pytest.raises(sg.SuggestInputError, match="drive"):
        sg.suggest([], VOCAB, None, 0.5, 100, datetime(2026, 10, 8))
