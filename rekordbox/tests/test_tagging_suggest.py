import numpy as np

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
