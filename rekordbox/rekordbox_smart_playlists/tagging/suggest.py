from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from . import evaluate as ev
from .library import GENRES, Track

EXPERIMENTAL_BASS = "Experimental Bass"
HALFTIME = "Halftime"
WEIRD = "WEIRD"
SCORED_TAGS = (
    "House",
    "Dub",
    "DnB",
    "GROOVY",
    "Dubstep",
    "Riddim",
    "Jungle",
    "DnB Liquid",
    "HEAVY",
)
LANE_EXTRAS = frozenset({EXPERIMENTAL_BASS})
REVIEW_PRECISION = 0.5
DEFAULT_APPLY_PRECISION = 0.8
MIN_SUPPORT = 20


@dataclass
class Calibrated:
    tag: str
    parent: str | None
    pool_y: np.ndarray
    pool_random: np.ndarray
    pool_grouped: np.ndarray
    cand_random: np.ndarray
    cand_grouped: np.ndarray


def has_lane_tag(track: Track, vocab: frozenset[str]) -> bool:
    return bool(track.raw_tags & (vocab | LANE_EXTRAS))


def experimental_bass_task(pool: list[Track]) -> ev.Task:
    """Stand-in labels: WEIRD with no genre but Halftime is positive; genre-tagged without WEIRD
    is negative. Halftime-only tracks are left out because they could be either."""
    other_genres = GENRES - {HALFTIME}
    rows: list[int] = []
    y: list[bool] = []
    for i, t in enumerate(pool):
        if WEIRD in t.tags and not t.tags & other_genres:
            rows.append(i)
            y.append(True)
        elif t.tags & GENRES and WEIRD not in t.tags and HALFTIME not in t.tags:
            rows.append(i)
            y.append(False)
    return ev.Task(
        EXPERIMENTAL_BASS, "stand-in", EXPERIMENTAL_BASS, None, np.array(rows), np.array(y)
    )


def precision_curve(scores: np.ndarray, y: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """Estimated precision of tagging everything scoring >= s, never decreasing in s, and never
    resting on fewer than MIN_SUPPORT out-of-fold tracks."""
    order = np.argsort(-scores, kind="stable")
    sorted_scores = scores[order]
    hits = np.cumsum(y[order])
    k = np.arange(1, len(scores) + 1)
    precision = hits / k
    floor = min(MIN_SUPPORT, len(scores)) - 1
    precision = np.maximum.accumulate(precision[::-1])[::-1]

    def lookup(s: np.ndarray) -> np.ndarray:
        above = np.searchsorted(-sorted_scores, -np.asarray(s), side="right")
        return precision[np.clip(above, floor + 1, len(scores)) - 1]

    return lookup


def _score(
    task: ev.Task,
    pool: list[Track],
    candidates: list[Track],
    x_all: np.ndarray,
    slots: np.ndarray,
    tag_matrix: np.ndarray,
    col: int,
    n_artists: int,
    splits: list[ev.Split],
) -> tuple[np.ndarray, np.ndarray]:
    n_pool = len(pool)
    cand = n_pool + np.arange(len(candidates))
    rows = np.concatenate([task.universe, cand])
    y = np.concatenate([task.y.astype(float), np.zeros(len(candidates))])
    n_u = len(task.universe)
    oof = np.full(n_u, np.nan)
    cand_sum = np.zeros(len(candidates))
    for _, tr, te in splits:
        test = np.concatenate([te, np.arange(n_u, len(rows))])
        out, _ = ev.fold_scores(
            x_all[rows], slots[rows], tag_matrix[rows], y, col, tr, test, n_artists, ("combined",)
        )
        oof[te] = out["combined"][: len(te)]
        cand_sum += out["combined"][len(te) :]
    return oof, cand_sum / len(splits)


def calibrate(
    pool: list[Track],
    x_pool: np.ndarray,
    candidates: list[Track],
    x_cand: np.ndarray,
    vocab: frozenset[str],
    progress: Callable[[str], None] = print,
) -> list[Calibrated]:
    tag_names = sorted(vocab)
    col_of = {t: i for i, t in enumerate(tag_names)}
    everyone = pool + candidates
    slots, n_artists = ev.artist_slots(everyone)
    tag_matrix = np.zeros((len(everyone), len(tag_names)))
    tag_matrix[: len(pool)] = [[t in p.tags for t in tag_names] for p in pool]
    x_all = np.vstack([x_pool, x_cand])
    tasks = {t.name: t for t in ev.make_tasks([p.tags for p in pool], vocab)}
    wanted = [tasks[n] for n in SCORED_TAGS if n in tasks] + [experimental_bass_task(pool)]
    results: list[Calibrated] = []
    for task in wanted:
        uni = [pool[i] for i in task.universe]
        random = ev.random_splits(task.y)[: ev.FOLDS]
        grouped, _ = ev.group_splits(np.array([t.lead for t in uni]), [t.artists for t in uni])
        col = col_of.get(task.tag, 0)
        args = (task, pool, candidates, x_all, slots, tag_matrix, col, n_artists)
        pool_r, cand_r = _score(*args, random)
        pool_g, cand_g = _score(*args, grouped)
        results.append(Calibrated(task.tag, task.parent, task.y, pool_r, pool_g, cand_r, cand_g))
        progress(f"  {task.tag}: universe {len(task.universe)}, positives {int(task.y.sum())}")
    return results


def estimated_precision(
    cal: Calibrated, candidates: list[Track], pool_artists: frozenset[str]
) -> np.ndarray:
    """Candidates sharing an artist with the pool read the random-split curve; the rest read the
    stricter artist-grouped one."""
    known = np.array([bool(c.artists & pool_artists) for c in candidates])
    rand = precision_curve(cal.pool_random, cal.pool_y)(cal.cand_random)
    grp = precision_curve(cal.pool_grouped, cal.pool_y)(cal.cand_grouped)
    return np.where(known, rand, grp)
