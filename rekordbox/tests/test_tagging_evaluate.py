from types import SimpleNamespace

import numpy as np
import pytest

from rekordbox_smart_playlists.tagging import evaluate as ev
from rekordbox_smart_playlists.tagging import library as lib


def test_artist_prior_excludes_self_and_uses_training_only():
    slots = np.array([[0], [0], [0], [1], [0]])
    tags = np.array([[1.0], [1.0], [0.0], [1.0], [1.0]])
    in_train = np.array([True, True, True, True, False])
    rows = np.arange(5)
    prior = ev.artist_prior(slots, tags, in_train, rows, n_artists=2)
    assert prior[0, 0] == pytest.approx(0.5)
    assert prior[2, 0] == pytest.approx(1.0)
    assert prior[3, 0] == 0.0
    assert prior[4, 0] == pytest.approx(2 / 3)
    leaky = ev.artist_prior(slots, tags, in_train, rows, n_artists=2, leave_one_out=False)
    assert leaky[3, 0] == 1.0


def test_artist_prior_takes_max_over_collab_artists():
    slots = np.array([[0, -1], [1, -1], [0, 1]])
    tags = np.array([[1.0], [0.0], [0.0]])
    in_train = np.array([True, True, False])
    prior = ev.artist_prior(slots, tags, in_train, np.array([2]), n_artists=2)
    assert prior[0, 0] == 1.0


def _row(id_, artist):
    return SimpleNamespace(
        ID=id_,
        FolderPath=f"/m/{id_}.aiff",
        ArtistName=artist,
        Title="T",
        BPM=12000,
        Length=100,
        MyTagNames=["House"],
        rb_local_deleted=0,
    )


def test_group_split_keeps_artist_on_one_side_and_collabs_use_first_artist():
    rows = []
    for i in range(40):
        rows.append(_row(i, f"Solo{i % 10}"))
    rows.append(_row(100, "Solo3 & Other"))
    rows.append(_row(101, "Solo3 feat. Someone"))
    db = SimpleNamespace(get_content=lambda: rows)
    tracks = lib.load_library(db, frozenset({"House"}), exists=lambda p: True)
    groups = np.array([t.group for t in tracks])
    assert {t.group for t in tracks if t.content_id in {"100", "101"}} == {"solo3"}
    for _, train, test in ev.group_splits(groups):
        assert not set(groups[train]) & set(groups[test])


def _tags(spec):
    return [frozenset(s) for s in spec]


def test_insufficient_threshold_and_universes():
    pool = _tags(
        [{"Dub", "WEIRD"}] * 29
        + [{"Dub Reggae", "Dub"}] * 30
        + [{"House"}] * 40
        + [{"GROOVY"}] * 10
    )
    vocab = frozenset({"Dub", "Dub Reggae", "House", "WEIRD", "GROOVY"})
    tasks = {t.name: t for t in ev.make_tasks(pool, vocab)}
    assert tasks["Dub"].positives == 59
    assert len(tasks["Dub"].universe) == 99
    assert not tasks["Dub"].insufficient
    assert tasks["WEIRD"].insufficient
    assert tasks["WEIRD"].positives == 29
    assert len(tasks["WEIRD"].universe) == len(pool)
    assert len(tasks["Dub Reggae"].universe) == 59
    assert "WEIRD in Dub" in tasks
    assert tasks["WEIRD in Dub"].positives == 29
    assert tasks["GROOVY"].positives == 10
    assert tasks["GROOVY"].insufficient


def _noise_problem(n=600, seed=1):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 12))
    y = rng.random(n) < 0.25
    slots = rng.integers(0, 150, size=(n, 1))
    tags = y[:, None].astype(float)
    return x, slots, tags, y


def test_negative_control_passes_on_permuted_labels():
    x, slots, tags, y = _noise_problem()
    ap, prev = ev.negative_control(x, slots, tags, y, 0, 150)
    assert ev.control_passes(ap, prev)


def test_negative_control_fails_when_a_leak_is_injected():
    x, slots, tags, y = _noise_problem()
    perm = np.random.default_rng(ev.SEED).permutation(y)
    leaky = np.hstack([x, perm[:, None].astype(float)])
    ap, prev = ev.negative_control(leaky, slots, tags, y, 0, 150)
    assert not ev.control_passes(ap, prev)


def test_pool_guard_aborts_when_embeddings_missing():
    pool = [
        lib.Track(str(i), f"/m/{i}", "a", frozenset({"a"}), "a", "t", 120.0, 100, frozenset({"House"}))
        for i in range(10)
    ]
    cache = ev.Cache(
        ["0"], np.zeros((1, 1280)), np.zeros((1, 400)), np.zeros(1), {"0": {"path": "/m/0", "length": 100}}
    )
    with pytest.raises(ev.PoolGuardError, match="House: 10 -> 1"):
        ev.align_pool(pool, cache)
