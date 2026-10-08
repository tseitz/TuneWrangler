from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from . import evaluate as ev
from . import manifest as mf
from .library import GENRES, SUB_PARENT, Track, in_training_pool

EXPERIMENTAL_BASS = "Experimental Bass"
HALFTIME = "Halftime"
HALFTIME_STYLE = "Electronic---Halftime"
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
LIQUID = "DnB Liquid"
PARENT_OF_LIQUID = "DnB"
HIPHOP_PREFIX = "Hip Hop"
TOP_STYLES = 3
NOTE = (
    "est_precision assumes the track belongs to one of the lane genres; "
    "Experimental Bass is measured against stand-in labels"
)


class SuggestInputError(RuntimeError):
    pass


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


@dataclass
class TagEstimate:
    score: np.ndarray
    est: np.ndarray
    split: np.ndarray


@dataclass
class Stats:
    candidates: int
    dropped_no_suggestion: int
    hiphop_downgrades: int


def newest_first(tracks: Sequence[Track], limit: int | None) -> list[Track]:
    ordered = sorted(
        tracks,
        key=lambda t: (t.added is None, -(t.added.timestamp() if t.added else 0), t.content_id),
    )
    return ordered[:limit]


def tag_estimates(
    cals: list[Calibrated], candidates: list[Track], pool_artists: frozenset[str]
) -> dict[str, TagEstimate]:
    known = np.array([bool(c.artists & pool_artists) for c in candidates], dtype=bool)
    out: dict[str, TagEstimate] = {}
    for cal in cals:
        out[cal.tag] = TagEstimate(
            np.where(known, cal.cand_random, cal.cand_grouped),
            estimated_precision(cal, candidates, pool_artists),
            np.where(known, "random", "grouped"),
        )
    liquid, parent = out.get(LIQUID), out.get(PARENT_OF_LIQUID)
    if liquid and parent:
        out[LIQUID] = TagEstimate(
            liquid.score, liquid.est * parent.est, np.full(len(candidates), "product")
        )
    return out


def top_styles(
    cache: ev.Cache, rows: Sequence[int] | np.ndarray, n: int = TOP_STYLES
) -> list[list[tuple[str, float]]]:
    result = []
    for r in rows:
        probs = cache.genre[r]
        best = np.argsort(-probs, kind="stable")[:n]
        result.append([(cache.class_names[i], round(float(probs[i]), 3)) for i in best])
    return result


def _is_genre(tag: str) -> bool:
    return tag in GENRES or tag in SUB_PARENT


def _row(est: TagEstimate, i: int) -> tuple[float, float, str]:
    return round(float(est.score[i]), 4), round(float(est.est[i]), 4), str(est.split[i])


def _apply_threshold(tag: str, min_precision: float, new_tag_precision: float | None) -> float:
    if tag == EXPERIMENTAL_BASS and new_tag_precision is not None:
        return new_tag_precision
    return min_precision


def _judge(
    tag: str,
    est: TagEstimate,
    i: int,
    min_precision: float,
    new_tag_precision: float | None,
    is_hiphop: bool,
) -> mf.Suggestion | None:
    score, e, split = _row(est, i)
    if e < REVIEW_PRECISION:
        return None
    threshold = _apply_threshold(tag, min_precision, new_tag_precision)
    apply = e >= threshold and not (is_hiphop and _is_genre(tag))
    return mf.Suggestion(tag, score, e, split, "apply" if apply else "review")


def assemble(
    candidates: Sequence[Track],
    estimates: dict[str, TagEstimate],
    styles: Sequence[list[tuple[str, float]]],
    vocab_hash: str,
    min_precision: float,
    created_at: datetime,
    new_tag_precision: float | None = None,
) -> tuple[mf.Manifest, Stats]:
    entries: list[tuple[float, mf.Entry]] = []
    hiphop = dropped = 0
    for i, track in enumerate(candidates):
        top = styles[i]
        is_hiphop = bool(top) and top[0][0].startswith(HIPHOP_PREFIX)
        eb = estimates.get(EXPERIMENTAL_BASS)
        suggestions: list[mf.Suggestion] = []
        for tag, est in estimates.items():
            if (s := _judge(tag, est, i, min_precision, new_tag_precision, is_hiphop)) is not None:
                suggestions.append(s)
        proposed = [s.tag for s in suggestions if s.decision == "apply"]
        if eb and EXPERIMENTAL_BASS in proposed and top and top[0][0] == HALFTIME_STYLE:
            suggestions.append(mf.Suggestion(HALFTIME, *_row(eb, i), "apply"))
            proposed.append(HALFTIME)
        downgraded = any(
            s.decision == "review"
            and s.est_precision >= _apply_threshold(s.tag, min_precision, new_tag_precision)
            for s in suggestions
        )
        if not suggestions:
            dropped += 1
            continue
        hiphop += downgraded
        best = max(s.est_precision for s in suggestions)
        entries.append(
            (
                best,
                mf.Entry(
                    track.content_id,
                    track.artist,
                    track.title,
                    track.bpm,
                    top,
                    sorted(suggestions, key=lambda s: -s.est_precision),
                    proposed,
                    "apply" if proposed else "review",
                ),
            )
        )
    entries.sort(key=lambda p: (p[1].decision != "apply", -p[0], p[1].content_id))
    manifest = mf.Manifest(
        created_at=created_at.isoformat(timespec="seconds"),
        vocabulary_hash=vocab_hash,
        thresholds={
            "review": REVIEW_PRECISION,
            "apply": min_precision,
            EXPERIMENTAL_BASS: _apply_threshold(
                EXPERIMENTAL_BASS, min_precision, new_tag_precision
            ),
        },
        note=NOTE,
        entries=[e for _, e in entries],
    )
    return manifest, Stats(len(candidates), dropped, hiphop)


def render_summary(
    manifest: mf.Manifest, stats: Stats, untagged_without_embedding: int, path: str
) -> str:
    proposed = Counter(t for e in manifest.entries for t in e.proposed)
    review = Counter(
        s.tag for e in manifest.entries for s in e.suggestions if s.decision == "review"
    )
    per_track = Counter(len(e.proposed) for e in manifest.entries)
    n_apply = sum(e.decision == "apply" for e in manifest.entries)
    lines = [
        f"candidates considered: {stats.candidates}",
        f"entries written: {len(manifest.entries)} ({n_apply} apply, "
        f"{len(manifest.entries) - n_apply} review); {stats.dropped_no_suggestion} had no "
        f"suggestion at or above {REVIEW_PRECISION}",
        f"min-precision: {manifest.thresholds['apply']} "
        f"({EXPERIMENTAL_BASS}: {manifest.thresholds.get(EXPERIMENTAL_BASS)})",
        "proposed per tag: " + (", ".join(f"{t} {n}" for t, n in proposed.most_common()) or "-"),
        "review per tag:   " + (", ".join(f"{t} {n}" for t, n in review.most_common()) or "-"),
        "proposed tags per track: " + ", ".join(f"{k}: {v}" for k, v in sorted(per_track.items())),
        f"hip-hop downgrades (genre tags moved to review): {stats.hiphop_downgrades}",
        f"untagged tracks without an embedding: {untagged_without_embedding}",
        f"manifest: {path}",
    ]
    return "\n".join(lines)


def suggest(
    library: list[Track],
    vocab: frozenset[str],
    cache: ev.Cache,
    min_precision: float,
    limit: int | None,
    created_at: datetime,
    progress: Callable[[str], None] = print,
    new_tag_precision: float | None = None,
) -> tuple[mf.Manifest, Stats, int]:
    tagged = [t for t in library if in_training_pool(t)]
    if not tagged:
        raise SuggestInputError(
            "no tagged tracks with an existing file; is the music drive mounted?"
        )
    pool, x_pool, _ = ev.align_pool(tagged, cache)
    untagged = [t for t in library if not has_lane_tag(t, vocab)]
    usable, _ = ev.usable(untagged, cache)
    cands = newest_first(usable, limit)
    cands, idx = ev.usable(cands, cache)
    x_cand = ev.feature_matrix(cands, cache, idx)
    cals = calibrate(pool, x_pool, cands, x_cand, vocab, progress)
    pool_artists = frozenset(a for t in pool for a in t.artists)
    manifest, stats = assemble(
        cands,
        tag_estimates(cals, cands, pool_artists),
        top_styles(cache, idx),
        mf.vocabulary_hash(vocab),
        min_precision,
        created_at,
        new_tag_precision,
    )
    return manifest, stats, len(untagged) - len(usable)
