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


def _solo_splits(slots):
    lead = slots[:, 0]
    return ev.group_splits(lead.astype(str), [frozenset({str(a)}) for a in lead])[0]


def test_negative_control_passes_on_permuted_labels():
    x, slots, tags, y = _noise_problem()
    aps, prev = ev.negative_control(x, slots, tags, y, 0, 150)
    assert len(aps) == ev.PERMUTATIONS
    assert ev.control_passes(aps, prev)


def test_negative_control_passes_under_grouped_split():
    x, slots, tags, y = _noise_problem()
    aps, prev = ev.negative_control(x, slots, tags, y, 0, 150, grouped_splits=_solo_splits(slots))
    assert ev.control_passes(aps, prev)


def test_negative_control_fails_when_a_leak_is_injected():
    x, slots, tags, y = _noise_problem()
    perm = np.random.default_rng(ev.SEED).permutation(y)
    leaky = np.hstack([x, perm[:, None].astype(float)])
    aps, prev = ev.negative_control(leaky, slots, tags, y, 0, 150)
    assert not ev.control_passes(aps, prev)


def test_negative_control_sees_a_prior_that_leaks_the_rows_own_label(monkeypatch):
    x, slots, tags, y = _noise_problem()
    monkeypatch.setattr(
        ev, "artist_prior", lambda slots, tags, in_train, rows, n_artists, **_: tags[rows]
    )
    aps, prev = ev.negative_control(x, slots, tags, y, 0, 150)
    assert not ev.control_passes(aps, prev)
    aps, prev = ev.negative_control(x, slots, tags, y, 0, 150, grouped_splits=_solo_splits(slots))
    assert not ev.control_passes(aps, prev)


def test_control_tolerance_scales_with_prevalence():
    assert ev.control_passes([0.012] * 3, 0.01)
    assert not ev.control_passes([0.04] * 3, 0.01)
    assert ev.control_passes([0.3] * 3, 0.25)
    assert not ev.control_passes([0.4] * 3, 0.25)


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


def _web(n_solo=60):
    lead = [f"s{i}" for i in range(n_solo)]
    artists = [frozenset({a}) for a in lead]
    for i in range(0, n_solo - 1, 2):
        lead.append(f"s{i}")
        artists.append(frozenset({f"s{i}", f"s{i + 1}"}))
    for i in range(n_solo):
        lead.append(f"hub{i % 3}")
        artists.append(frozenset({f"hub{i % 3}", f"s{i}"}))
    return np.array(lead), artists


def test_purged_split_never_shares_an_artist_across_sides():
    lead = np.array(["a", "a", "b", "b", "c", "d", "e", "f", "g", "h"])
    artists = [frozenset(x) for x in ({"a"}, {"a", "b"}, {"b"}, {"b"}, {"c"}, {"d"}, {"e"}, {"f"}, {"g"}, {"h"})]
    splits, stats = ev.group_splits(lead, artists)
    for (_, tr, te), s in zip(splits, stats, strict=True):
        assert not set().union(*(artists[i] for i in tr)) & set().union(*(artists[i] for i in te))
        assert s["train_after"] == len(tr) <= s["train_before"]
    assert any(s["train_after"] < s["train_before"] for s in stats)


def test_purged_folds_stay_near_a_fifth_on_a_big_collab_web():
    lead, artists = _web()
    splits, stats = ev.group_splits(lead, artists)
    for (_, tr, te), s in zip(splits, stats, strict=True):
        assert 0.1 < len(te) / len(lead) < 0.3
        assert not set().union(*(artists[i] for i in tr)) & set().union(*(artists[i] for i in te))
    assert 0 < ev.purge_fraction(stats) < 1


def test_prior_in_a_purged_fold_sees_only_purged_train_rows():
    lead, artists = _web()
    slots, n_artists = ev.artist_slots([ev_track(a) for a in artists])
    tags = np.ones((len(lead), 1))
    (_, tr, te), *_ = ev.group_splits(lead, artists)[0]
    in_train = np.zeros(len(lead), dtype=bool)
    in_train[tr] = True
    prior = ev.artist_prior(slots, tags, in_train, te, n_artists)
    assert (prior == 0).all()


def ev_track(artists):
    return lib.Track("x", "/m/x", "x", artists, "x", "t", 120.0, 1, frozenset())
