import numpy as np
import pytest

from rekordbox_smart_playlists.tagging import embed as emb
from rekordbox_smart_playlists.tagging import evaluate as ev
from rekordbox_smart_playlists.tagging import report as rp
from rekordbox_smart_playlists.tagging.library import Track

STYLES = np.array(["A", "A", "A", "B", "B", "C"])
HAS = {"x": np.array([1, 1, 0, 1, 0, 0], dtype=bool), "y": np.array([0, 0, 1, 0, 1, 1], dtype=bool)}


def test_top1_assignment_and_label_stripping():
    genre = np.array([[0.1, 0.9, 0.2], [0.7, 0.1, 0.6]])
    labels = [rp.style_label(n) for n in ["Electronic---Dub", "Reggae---Dub", "Electronic---House"]]
    assert labels == ["Dub", "Reggae---Dub", "House"]
    assert list(rp.top1_styles(genre, labels)) == ["Reggae---Dub", "Dub"]
    top = rp.top_styles(genre, labels, 2)
    assert [s for s, _ in top[1]] == ["Dub", "House"]


def test_tag_to_styles_share_and_lift():
    rows = {r[0]: r for r in rp.tag_to_styles(STYLES, HAS)["x"]}
    style, count, share, library, lift = rows["A"]
    assert (count, share) == (2, pytest.approx(2 / 3))
    assert library == pytest.approx(3 / 6)
    assert lift == pytest.approx((2 / 3) / (3 / 6))
    assert rows["B"][4] == pytest.approx((1 / 3) / (2 / 6))
    assert "C" not in rows


def test_style_to_tags_respects_minimum_and_lift():
    out = rp.style_to_tags(STYLES, HAS, min_tracks=2)
    assert set(out) == {"A", "B"}
    x = {r[0]: r for r in out["A"]}["x"]
    assert x[2] == pytest.approx(2 / 3)
    assert x[4] == pytest.approx((2 / 3) / (3 / 6))


def test_bpm_histogram_bins_of_five():
    hist = rp.bpm_histogram(np.array([128.0, 129.9, 130.0, 140.0, 0.0]))
    assert hist == [(125, 2), (130, 1), (135, 0), (140, 1)]


def _aligned(n_per=40, seed=0):
    rng = np.random.default_rng(seed)
    genre = rng.random((3 * n_per, 4)) * 0.1
    genre[:n_per, 1] = 0.9
    genre[n_per : 2 * n_per, 2] = 0.9
    genre[2 * n_per :, 0] = 0.9
    labels = ["x", "Drum n Bass", "Dubstep", "y"]
    idx = np.arange(3 * n_per)
    has = {"DnB": idx < n_per, "Dubstep": (idx >= n_per) & (idx < 2 * n_per)}
    return genre, labels, has


def test_positive_control_passes_aligned_and_fails_shuffled_classes():
    genre, labels, has = _aligned()
    styles = rp.top1_styles(genre, labels)
    results = rp.positive_control(styles, has)
    assert all(lift > 2 for _, _, lift in results)
    rp.check_positive_control(results)

    shuffled = rp.top1_styles(genre, [labels[i] for i in [3, 2, 1, 0]])
    with pytest.raises(ev.ControlError, match="misaligned"):
        rp.check_positive_control(rp.positive_control(shuffled, has))


def test_cluster_group_is_seeded_and_lists_nearest():
    rng = np.random.default_rng(1)
    emb_ = np.vstack([rng.normal(c, 0.1, (30, 5)) for c in (0, 5, 10, 15)])
    bpm = np.linspace(120, 160, len(emb_))
    styles = np.array(["s"] * len(emb_))
    result = rp.cluster_group(emb_, bpm, styles, {"s": 1.0})
    again = rp.cluster_group(emb_, bpm, styles, {"s": 1.0})
    assert result is not None and again is not None
    assert result.k == 4
    assert sorted(c.size for c in result.clusters) == [30] * 4
    assert all(len(c.nearest) == rp.NEAREST for c in result.clusters)
    assert [c.nearest for c in result.clusters] == [c.nearest for c in again.clusters]
    assert rp.cluster_group(emb_[:3], bpm[:3], styles[:3], {"s": 1.0}) is None


def _track(cid, artist, tags):
    return Track(cid, f"/m/{cid}", artist, frozenset({artist}), artist, "T", 128.0, 100, tags)


def _lane_fixture():
    rng = np.random.default_rng(3)
    n = 80
    signal = np.repeat([0.0, 1.0], n // 2)
    x = rng.normal(0, 1, (n, 6))
    x[:, 0] += 4 * (signal - 0.5)
    pool = [
        _track(str(i), f"a{i}", frozenset({"House" if signal[i] else "Dub"})) for i in range(n)
    ]
    untagged = [_track("u0", "new0", frozenset()), _track("u1", "new1", frozenset())]
    x_new = rng.normal(0, 1, (2, 6))
    x_new[0, 0] += 2
    x_new[1, 0] -= 2
    vocab = frozenset({"House", "Dub"})
    tasks = ev.make_tasks([p.tags for p in pool], vocab)
    oof = {
        "ids": np.array([p.content_id for p in pool]),
        "tasks": np.array([t.name for t in tasks]),
        "scores": np.full((n, len(tasks)), -7.0, dtype=np.float32),
        "thresholds": np.full(len(tasks), 0.5),
    }
    return pool, x, untagged, x_new, vocab, oof


def test_lane_fit_pool_rows_are_oof_and_untagged_rows_use_full_model():
    pool, x, untagged, x_new, vocab, oof = _lane_fixture()
    names, thr, pool_scores, new_scores = rp.lane_fit(pool, x, untagged, x_new, vocab, oof)
    assert names == ["Dub", "House"]
    assert (pool_scores == -7.0).all()
    assert new_scores.shape == (2, 2)
    assert not np.isnan(new_scores).any()
    house = names.index("House")
    assert new_scores[0, house] > 0.5 > new_scores[1, house]
    assert (new_scores > -7.0).all() and (new_scores <= 1.0).all()


def test_lane_fit_rejects_oof_from_another_library():
    pool, x, untagged, x_new, vocab, oof = _lane_fixture()
    oof["tasks"] = np.array(["Nope"])
    with pytest.raises(rp.ReportInputError):
        rp.lane_fit(pool, x, untagged, x_new, vocab, oof)


def test_sub_tag_blank_for_untagged_unless_parent_clears_threshold():
    rng = np.random.default_rng(5)
    n = 120
    parent = np.arange(n) < 60
    sub = np.arange(n) < 40
    x = rng.normal(0, 1, (n, 4))
    x[:, 0] += 4 * (parent - 0.5)
    x[:, 1] += 4 * (sub - 0.5)
    pool = []
    for i in range(n):
        tags = {"Dub"} if parent[i] else {"House"}
        if sub[i]:
            tags.add("Dub Wobblers")
        pool.append(_track(str(i), f"a{i}", frozenset(tags)))
    untagged = [_track("u0", "n0", frozenset()), _track("u1", "n1", frozenset())]
    x_new = np.array([[2.0, 2.0, 0, 0], [-2.0, 2.0, 0, 0]])
    vocab = frozenset({"Dub", "House", "Dub Wobblers"})
    tasks = ev.make_tasks([p.tags for p in pool], vocab)
    oof = {
        "ids": np.array([p.content_id for p in pool]),
        "tasks": np.array([t.name for t in tasks]),
        "scores": np.full((n, len(tasks)), np.nan, dtype=np.float32),
        "thresholds": np.full(len(tasks), 0.5),
    }
    names, _, _, new_scores = rp.lane_fit(pool, x, untagged, x_new, vocab, oof)
    col = names.index("Dub Wobblers")
    assert not np.isnan(new_scores[0, col])
    assert np.isnan(new_scores[1, col])


def test_run_report_end_to_end_on_temp_dir(tmp_path, monkeypatch):
    pool, x, untagged, x_new, vocab, oof = _lane_fixture()
    tracks = pool + untagged
    rng = np.random.default_rng(9)
    ids = [t.content_id for t in tracks]
    genre = rng.random((len(ids), emb.N_STYLES)).astype(np.float32) * 0.1
    genre[:, 5] = 0.5
    effnet = np.zeros((len(ids), emb.EFFNET_DIM), dtype=np.float32)
    effnet[: len(pool), :6] = x
    effnet[len(pool) :, :6] = x_new
    names = [f"Electronic---S{i}" for i in range(emb.N_STYLES)]
    names[5], names[6], names[7] = "Electronic---Drum n Bass", "Electronic---Dubstep", "Reggae---Dub"
    meta = {t.content_id: {"path": t.path, "length": t.length, "row": i} for i, t in enumerate(tracks)}
    np.savez(
        tmp_path / "embeddings.npz",
        ids=np.array(ids),
        effnet=effnet,
        genre=genre,
        voice=np.zeros(len(ids), dtype=np.float32),
        class_names=np.array(names),
    )
    (tmp_path / "index.json").write_text(__import__("json").dumps({"tracks": meta}))
    np.savez(tmp_path / "oof_scores.npz", **oof)
    with pytest.raises(ev.ControlError):
        rp.run_report(tracks, tmp_path, vocab, progress=lambda _: None)
    assert not (tmp_path / "tracks.csv").exists()

    monkeypatch.setattr(rp, "check_positive_control", lambda results: None)
    rp.run_report(tracks, tmp_path, vocab, progress=lambda _: None)
    lines = (tmp_path / "tracks.csv").read_text().splitlines()
    assert lines[0].startswith("artist,title,bpm")
    assert lines[1].split(",")[0] in {"new0", "new1"} and lines[1].endswith(",yes")
    assert "Drum n Bass (0.50)" in lines[1]
    assert "(c) Fuzzy tags" in (tmp_path / "crosstab.md").read_text()


def test_missing_oof_scores_asks_for_evaluate(tmp_path):
    with pytest.raises(rp.ReportInputError, match="tag evaluate"):
        rp.read_oof(tmp_path)
