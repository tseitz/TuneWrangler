import json
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from joblib import Parallel, delayed
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.model_selection import GroupKFold, RepeatedStratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .library import GENRES, MODIFIERS, SUB_PARENT, Track

MIN_POSITIVES = 30
PARENT_SHARE = 0.15
MAX_MISSING = 0.02
CONTROL_TOLERANCE = 0.05
MODELS = ("artist_prior", "audio", "combined")
SPLITS = ("random", "grouped")
MAX_ITER = 2000
FOLDS = 5
REPEATS = 3
SEED = 0

Split = tuple[int, np.ndarray, np.ndarray]


class PoolGuardError(Exception):
    """Too much of the pool has no usable embedding."""


class ControlError(Exception):
    """A control that must pass did not."""


@dataclass(frozen=True)
class Task:
    name: str
    family: str
    tag: str
    parent: str | None
    universe: np.ndarray
    y: np.ndarray

    @property
    def positives(self) -> int:
        return int(self.y.sum())

    @property
    def prevalence(self) -> float:
        return float(self.y.mean()) if len(self.y) else 0.0

    @property
    def insufficient(self) -> bool:
        return self.positives < MIN_POSITIVES


def make_tasks(pool_tags: list[frozenset[str]], vocab: frozenset[str]) -> list[Task]:
    """Tasks over pool positions. Universes follow the pool definitions in the plan."""
    has = {tag: np.array([tag in t for t in pool_tags]) for tag in vocab}
    all_rows = np.arange(len(pool_tags))
    genre_rows = np.flatnonzero(np.any([has[g] for g in GENRES if g in has], axis=0))

    def task(name: str, family: str, tag: str, parent: str | None, rows: np.ndarray) -> Task:
        return Task(name, family, tag, parent, rows, has[tag][rows])

    tasks: list[Task] = []
    for tag in sorted(GENRES & vocab):
        tasks.append(task(tag, "genre", tag, None, genre_rows))
    for tag, parent in sorted(SUB_PARENT.items()):
        if tag in has and parent in has:
            tasks.append(task(tag, "sub-tag", tag, parent, np.flatnonzero(has[parent])))
    for tag in sorted(MODIFIERS & vocab):
        tasks.append(task(tag, "modifier", tag, None, all_rows))
        total = has[tag].sum()
        for parent in sorted(GENRES & vocab):
            if total and (has[tag] & has[parent]).sum() / total >= PARENT_SHARE:
                tasks.append(
                    task(
                        f"{tag} in {parent}",
                        "modifier-in-parent",
                        tag,
                        parent,
                        np.flatnonzero(has[parent]),
                    )
                )
    return tasks


@dataclass
class Cache:
    ids: list[str]
    effnet: np.ndarray
    genre: np.ndarray
    voice: np.ndarray
    meta: dict[str, Any]


def load_cache(directory: Path, attempts: int = 8, wait: float = 2.0) -> Cache:
    """The embedder rewrites the files every 50 tracks, so a read can land mid-write."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            meta = json.loads((directory / "index.json").read_text())["tracks"]
            with np.load(directory / "embeddings.npz") as arrays:
                return Cache(
                    [str(i) for i in arrays["ids"]],
                    arrays["effnet"],
                    arrays["genre"],
                    arrays["voice"],
                    meta,
                )
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile) as exc:
            last = exc
            time.sleep(wait)
    raise RuntimeError(f"could not read a consistent embedding cache in {directory}: {last}")


def _tag_counts(tracks: list[Track]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in tracks:
        for tag in t.tags:
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def align_pool(pool: list[Track], cache: Cache) -> tuple[list[Track], np.ndarray, str]:
    """Keeps pool tracks with a fresh cached embedding. Returns features and a guard report."""
    row_of = {cid: i for i, cid in enumerate(cache.ids)}
    kept: list[Track] = []
    rows: list[int] = []
    for t in pool:
        meta = cache.meta.get(t.content_id)
        if t.content_id in row_of and meta and (meta["path"], meta["length"]) == (t.path, t.length):
            kept.append(t)
            rows.append(row_of[t.content_id])
    before, after = _tag_counts(pool), _tag_counts(kept)
    lines = [f"pool {len(pool)} tracks, embedded {len(kept)}, missing {len(pool) - len(kept)}"]
    lines += [f"  {tag}: {before[tag]} -> {after.get(tag, 0)}" for tag in sorted(before)]
    missing = (len(pool) - len(kept)) / len(pool) if pool else 0.0
    if missing > MAX_MISSING:
        raise PoolGuardError(
            f"{missing:.1%} of the pool has no usable embedding (limit {MAX_MISSING:.0%}); "
            "finish `tag embed` first.\n" + "\n".join(lines)
        )
    idx = np.array(rows, dtype=int)
    bpm = np.array([t.bpm for t in kept])
    x = np.hstack(
        [
            cache.effnet[idx],
            cache.genre[idx],
            cache.voice[idx][:, None],
            bpm[:, None],
            np.log1p(bpm)[:, None],
        ]
    ).astype(np.float64)
    return kept, x, "\n".join(lines)


def artist_slots(tracks: list[Track]) -> tuple[np.ndarray, int]:
    """(n, K) artist ids per track, -1 padded."""
    ids = {a: i for i, a in enumerate(sorted({a for t in tracks for a in t.artists}))}
    width = max((len(t.artists) for t in tracks), default=1)
    slots = np.full((len(tracks), width), -1, dtype=int)
    for r, t in enumerate(tracks):
        for k, a in enumerate(sorted(t.artists)):
            slots[r, k] = ids[a]
    return slots, len(ids)


def _artist_totals(
    slots: np.ndarray, tags: np.ndarray, in_train: np.ndarray, n_artists: int
) -> tuple[np.ndarray, np.ndarray]:
    counts = np.zeros((n_artists, tags.shape[1]))
    sizes = np.zeros(n_artists)
    train = np.flatnonzero(in_train)
    for k in range(slots.shape[1]):
        rows = train[slots[train, k] >= 0]
        np.add.at(counts, slots[rows, k], tags[rows])
        np.add.at(sizes, slots[rows, k], 1.0)
    return counts, sizes


def artist_prior(
    slots: np.ndarray,
    tags: np.ndarray,
    in_train: np.ndarray,
    rows: np.ndarray,
    n_artists: int,
    leave_one_out: bool = True,
) -> np.ndarray:
    """Per tag, max over a track's artists of the share of that artist's other training tracks
    carrying it. `leave_one_out` drops the track itself when it is a training track."""
    counts, sizes = _artist_totals(slots, tags, in_train, n_artists)
    own = (in_train[rows] & leave_one_out).astype(float)
    out = np.zeros((len(rows), tags.shape[1]))
    for k in range(slots.shape[1]):
        a = slots[rows, k]
        safe = np.where(a >= 0, a, 0)
        den = sizes[safe] - own
        ok = (a >= 0) & (den > 0)
        frac = (counts[safe] - own[:, None] * tags[rows]) / np.maximum(den, 1)[:, None]
        out = np.maximum(out, np.where(ok[:, None], frac, 0.0))
    return out


def random_splits(y: np.ndarray) -> list[Split]:
    cv = RepeatedStratifiedKFold(n_splits=FOLDS, n_repeats=REPEATS, random_state=SEED)
    return [(i // FOLDS, tr, te) for i, (tr, te) in enumerate(cv.split(np.zeros(len(y)), y))]


def group_splits(groups: np.ndarray) -> list[Split]:
    cv = GroupKFold(n_splits=FOLDS)
    return [(0, tr, te) for tr, te in cv.split(np.zeros(len(groups)), groups=groups)]


def _fit_score(
    x_tr: np.ndarray, y_tr: np.ndarray, x_te: np.ndarray, nonconverged: list[int]
) -> np.ndarray:
    if y_tr.min() == y_tr.max():
        return np.full(len(x_te), float(y_tr[0]))
    clf = LogisticRegression(C=1.0, class_weight="balanced", max_iter=MAX_ITER)
    pipe = make_pipeline(StandardScaler(), clf)
    pipe.fit(x_tr, y_tr)
    nonconverged.append(int(clf.n_iter_[0] >= MAX_ITER))
    return pipe.predict_proba(x_te)[:, 1]


def fold_scores(
    x: np.ndarray,
    slots: np.ndarray,
    tags: np.ndarray,
    y: np.ndarray,
    col: int,
    tr: np.ndarray,
    te: np.ndarray,
    n_artists: int,
    models: tuple[str, ...] = MODELS,
) -> tuple[dict[str, np.ndarray], int]:
    in_train = np.zeros(len(y), dtype=bool)
    in_train[tr] = True
    prior_te = artist_prior(slots, tags, in_train, te, n_artists)
    out: dict[str, np.ndarray] = {}
    if "artist_prior" in models:
        out["artist_prior"] = prior_te[:, col]
    bad: list[int] = []
    if "audio" in models:
        out["audio"] = _fit_score(x[tr], y[tr], x[te], bad)
    if "combined" in models:
        prior_tr = artist_prior(slots, tags, in_train, tr, n_artists)
        out["combined"] = _fit_score(
            np.hstack([x[tr], prior_tr]), y[tr], np.hstack([x[te], prior_te]), bad
        )
    return out, sum(bad)


def _best_threshold(y: np.ndarray, scores: np.ndarray) -> float:
    prec, rec, thr = precision_recall_curve(y, scores)
    f1 = 2 * prec[:-1] * rec[:-1] / np.maximum(prec[:-1] + rec[:-1], 1e-12)
    return float(thr[int(np.argmax(f1))])


def summarize(
    y: np.ndarray, repeat_scores: list[np.ndarray]
) -> tuple[dict[str, float], np.ndarray]:
    """AP is the mean over repeats; the threshold and P/R use the repeat-averaged scores."""
    prevalence = float(y.mean())
    pooled = np.mean(repeat_scores, axis=0)
    ap = float(np.mean([average_precision_score(y, s) for s in repeat_scores]))
    thr = _best_threshold(y, pooled)
    pred = pooled >= thr
    tp = float((pred & (y == 1)).sum())
    return {
        "ap": ap,
        "lift": ap / prevalence if prevalence else 0.0,
        "precision": tp / pred.sum() if pred.sum() else 0.0,
        "recall": tp / y.sum() if y.sum() else 0.0,
        "threshold": thr,
    }, pooled


def _run_folds(
    jobs: int,
    x: np.ndarray,
    slots: np.ndarray,
    tags: np.ndarray,
    y: np.ndarray,
    col: int,
    splits: list[Split],
    n_artists: int,
    models: tuple[str, ...] = MODELS,
) -> tuple[list[dict[str, np.ndarray]], int]:
    """Out-of-fold scores per model-repeat: result[r][model] is a full-length vector."""
    results = Parallel(n_jobs=jobs)(
        delayed(fold_scores)(x, slots, tags, y, col, tr, te, n_artists, models)
        for _, tr, te in splits
    )
    n_repeats = max(r for r, _, _ in splits) + 1
    oof: list[dict[str, np.ndarray]] = [
        {m: np.zeros(len(y)) for m in models} for _ in range(n_repeats)
    ]
    bad = 0
    for (repeat, _, te), (scores, nb) in zip(splits, results, strict=True):
        for m, s in scores.items():
            oof[repeat][m][te] = s
        bad += nb
    return oof, bad


def negative_control(
    x: np.ndarray,
    slots: np.ndarray,
    tags: np.ndarray,
    y: np.ndarray,
    col: int,
    n_artists: int,
    jobs: int = 1,
    seed: int = SEED,
) -> tuple[float, float]:
    """(AP, prevalence) of the combined model on permuted labels, one random repeat."""
    y_perm = np.random.default_rng(seed).permutation(y)
    splits = random_splits(y_perm)[:FOLDS]
    oof, _ = _run_folds(jobs, x, slots, tags, y_perm, col, splits, n_artists, ("combined",))
    return float(average_precision_score(y_perm, oof[0]["combined"])), float(y_perm.mean())


def control_passes(ap: float, prevalence: float) -> bool:
    return abs(ap - prevalence) <= CONTROL_TOLERANCE


def evaluate(
    pool: list[Track],
    x: np.ndarray,
    vocab: frozenset[str],
    jobs: int = -1,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    tag_names = sorted(vocab)
    col_of = {t: i for i, t in enumerate(tag_names)}
    tag_matrix = np.array([[t in p.tags for t in tag_names] for p in pool], dtype=float)
    slots, n_artists = artist_slots(pool)
    groups = np.array([p.group for p in pool])
    tasks = make_tasks([p.tags for p in pool], vocab)
    scorable = [t for t in tasks if not t.insufficient]

    def view(task: Task) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        u = task.universe
        return x[u], slots[u], tag_matrix[u]

    controls = []
    for task in (t for t in scorable if t.family == "genre"):
        xu, su, tu = view(task)
        ap, prev = negative_control(xu, su, tu, task.y, col_of[task.tag], n_artists, jobs)
        controls.append(
            {"tag": task.name, "ap": ap, "prevalence": prev, "pass": control_passes(ap, prev)}
        )
        progress(f"negative control {task.name}: AP {ap:.3f} vs prevalence {prev:.3f}")
    failed = [c["tag"] for c in controls if not c["pass"]]
    if failed:
        raise ControlError(
            f"negative control failed for {failed}: permuted labels scored beyond "
            f"prevalence +/-{CONTROL_TOLERANCE}; the folds or the artist prior leak"
        )

    scores_out = np.full((len(pool), len(tasks)), np.nan, dtype=np.float32)
    thresholds = np.full(len(tasks), np.nan)
    nonconverged = 0
    records = []
    for i, task in enumerate(tasks):
        record: dict[str, Any] = {
            "name": task.name,
            "family": task.family,
            "tag": task.tag,
            "parent": task.parent,
            "universe": len(task.universe),
            "support": task.positives,
            "prevalence": task.prevalence,
            "insufficient": task.insufficient,
            "results": {},
        }
        records.append(record)
        if task.insufficient:
            progress(f"[{i + 1}/{len(tasks)}] {task.name}: insufficient ({task.positives})")
            continue
        started = time.monotonic()
        xu, su, tu = view(task)
        col = col_of[task.tag]
        for split_name, splits in (
            ("random", random_splits(task.y)),
            ("grouped", group_splits(groups[task.universe])),
        ):
            oof, bad = _run_folds(jobs, xu, su, tu, task.y, col, splits, n_artists)
            nonconverged += bad
            for model in MODELS:
                stats, pooled = summarize(task.y, [r[model] for r in oof])
                record["results"].setdefault(model, {})[split_name] = stats
                if model == "combined" and split_name == "random":
                    scores_out[task.universe, i] = pooled
                    thresholds[i] = stats["threshold"]
        progress(
            f"[{i + 1}/{len(tasks)}] {task.name}: n={len(task.universe)} pos={task.positives} "
            f"combined AP {record['results']['combined']['random']['ap']:.3f} "
            f"({time.monotonic() - started:.0f}s)"
        )
    return {
        "tasks": records,
        "controls": {"negative": controls},
        "nonconverged_fits": nonconverged,
        "config": {
            "folds": FOLDS,
            "repeats": REPEATS,
            "C": 1.0,
            "max_iter": MAX_ITER,
            "min_positives": MIN_POSITIVES,
        },
        "_oof": {
            "ids": np.array([p.content_id for p in pool]),
            "tasks": np.array([t.name for t in tasks]),
            "scores": scores_out,
            "thresholds": thresholds,
        },
    }


def render_markdown(result: dict[str, Any], guard_report: str) -> str:
    lines = ["# Tag evaluation", "", "```", guard_report, "```", ""]
    cfg = result["config"]
    lines.append(
        f"Logistic regression, C={cfg['C']}, balanced; random split = {cfg['folds']}-fold x "
        f"{cfg['repeats']} repeats, grouped = GroupKFold({cfg['folds']}) on first artist. "
        f"AP is the mean over repeats; P/R at the max-F1 threshold of pooled out-of-fold scores. "
        f"Non-converged fits: {result['nonconverged_fits']}."
    )
    lines += ["", "## Controls", ""]
    for c in result["controls"]["negative"]:
        lines.append(
            f"- negative control {c['tag']}: AP {c['ap']:.3f} vs prevalence "
            f"{c['prevalence']:.3f} ({'pass' if c['pass'] else 'FAIL'})"
        )
    titles = {
        "genre": "Genre tags",
        "sub-tag": "Sub-tags (within parent)",
        "modifier": "Modifiers (all pool tracks)",
        "modifier-in-parent": "Modifiers within a parent genre",
    }
    for family, title in titles.items():
        rows = [t for t in result["tasks"] if t["family"] == family and not t["insufficient"]]
        if not rows:
            continue
        lines += [
            "",
            f"## {title}",
            "",
            "| tag | model | split | support | prevalence | AP | lift | P@thr | R@thr |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for t in rows:
            for model in MODELS:
                for split in SPLITS:
                    r = t["results"][model][split]
                    lines.append(
                        f"| {t['name']} | {model} | {split} | {t['support']} | "
                        f"{t['prevalence']:.3f} | {r['ap']:.3f} | {r['lift']:.1f} | "
                        f"{r['precision']:.2f} | {r['recall']:.2f} |"
                    )
    insufficient = [t for t in result["tasks"] if t["insufficient"]]
    lines += ["", f"## Insufficient (fewer than {cfg['min_positives']} positives)", ""]
    lines += [f"- {t['name']} ({t['support']} of {t['universe']})" for t in insufficient] or [
        "- none"
    ]
    return "\n".join(lines) + "\n"


def write_outputs(result: dict[str, Any], guard_report: str, directory: Path) -> None:
    oof = result.pop("_oof")
    directory.mkdir(parents=True, exist_ok=True)
    np.savez(directory / "oof_scores.npz", **oof)
    (directory / "evaluation.json").write_text(json.dumps(result, indent=2))
    (directory / "evaluation.md").write_text(render_markdown(result, guard_report))


def run_evaluation(
    tracks: list[Track],
    directory: Path,
    vocab: frozenset[str],
    jobs: int = -1,
    progress: Callable[[str], None] = print,
) -> None:
    pool = [t for t in tracks if t.tags]
    cache = load_cache(directory)
    kept, x, guard_report = align_pool(pool, cache)
    progress(guard_report)
    result = evaluate(kept, x, vocab, jobs, progress)
    write_outputs(result, guard_report, directory)
    progress(f"wrote evaluation.md, evaluation.json, oof_scores.npz to {directory}")
