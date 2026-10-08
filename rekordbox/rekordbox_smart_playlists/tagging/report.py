import csv
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from . import evaluate as ev
from .embed import EFFNET_DIM
from .library import GENRES, Track, in_training_pool

STYLE_PREFIX = "Electronic---"
TOP_STYLES = 3
TOP_PER_TAG = 8
MIN_STYLE_TRACKS = 20
CLUSTER_KS = (4, 5, 6)
NEAREST = 8
MIN_CLUSTER_STYLE = 3
BPM_BIN = 5
SEED = 0
POSITIVE_CONTROLS = (("DnB", "Drum n Bass"), ("Dubstep", "Dubstep"))
CONTROL_MIN_LIFT = 2.0
CONTROL_MAX_SHARE = 0.4
CONTROL_MIN_TAG_SHARE = 0.3


class ReportInputError(Exception):
    """An input the report needs is missing or no longer matches the library."""


def style_label(class_name: str) -> str:
    return class_name.removeprefix(STYLE_PREFIX)


def load_class_names(directory: Path) -> list[str]:
    with np.load(directory / "embeddings.npz") as arrays:
        return [str(n) for n in arrays["class_names"]]


def top_styles(genre: np.ndarray, labels: list[str], n: int = TOP_STYLES) -> list[list[tuple]]:
    order = np.argsort(-genre, axis=1)[:, :n]
    return [[(labels[j], float(genre[i, j])) for j in row] for i, row in enumerate(order)]


def top1_styles(genre: np.ndarray, labels: list[str]) -> np.ndarray:
    return np.array([labels[j] for j in np.argmax(genre, axis=1)])


def _ratio(share: float, base: float) -> float:
    return share / base if base else 0.0


def tag_to_styles(
    styles: np.ndarray, has: dict[str, np.ndarray], top: int = TOP_PER_TAG
) -> dict[str, list[tuple[str, int, float, float, float]]]:
    """Per tag, rows of (style, count, share of the tag, share of the library, lift)."""
    library = Counter(styles.tolist())
    out = {}
    for tag, mask in has.items():
        total = int(mask.sum())
        if not total:
            continue
        counts = Counter(styles[mask].tolist())
        out[tag] = [
            (s, c, c / total, library[s] / len(styles), _ratio(c / total, library[s] / len(styles)))
            for s, c in counts.most_common(top)
        ]
    return out


def style_to_tags(
    styles: np.ndarray,
    has: dict[str, np.ndarray],
    min_tracks: int = MIN_STYLE_TRACKS,
    top: int = TOP_PER_TAG,
) -> dict[str, list[tuple[str, int, float, float, float]]]:
    """Per style, rows of (tag, count, share of the style, share of the library, lift)."""
    out = {}
    for style, count in Counter(styles.tolist()).most_common():
        if count < min_tracks:
            continue
        in_style = styles == style
        rows = []
        for tag, mask in has.items():
            k = int((mask & in_style).sum())
            if k:
                base = float(mask.mean())
                rows.append((tag, k, k / count, base, _ratio(k / count, base)))
        out[style] = sorted(rows, key=lambda r: -r[2])[:top]
    return out


def style_lift(styles: np.ndarray, mask: np.ndarray, style: str) -> float:
    if not mask.any():
        return 0.0
    share = float((styles[mask] == style).mean())
    return _ratio(share, float((styles == style).mean()))


def positive_control(
    styles: np.ndarray, has: dict[str, np.ndarray]
) -> list[tuple[str, str, str, float]]:
    """(tag, style, check, value). Lift saturates when the style is a big share of the library,
    so those fall back to the share of the tag's tracks that land in the style."""
    out = []
    for tag, style in POSITIVE_CONTROLS:
        mask = has.get(tag)
        if mask is None or not mask.any():
            out.append((tag, style, "lift", 0.0))
        elif float((styles == style).mean()) < CONTROL_MAX_SHARE:
            out.append((tag, style, "lift", style_lift(styles, mask, style)))
        else:
            out.append((tag, style, "share", float((styles[mask] == style).mean())))
    return out


def control_ok(check: str, value: float) -> bool:
    return value > CONTROL_MIN_LIFT if check == "lift" else value >= CONTROL_MIN_TAG_SHARE


def check_positive_control(results: list[tuple[str, str, str, float]]) -> None:
    bad = [f"{t} -> {s}: {c} {v:.2f}" for t, s, c, v in results if not control_ok(c, v)]
    if bad:
        raise ev.ControlError(
            f"positive control failed (lift must exceed {CONTROL_MIN_LIFT}, or the tag's share "
            f"in the style reach {CONTROL_MIN_TAG_SHARE}): {'; '.join(bad)}. "
            "The genre class index is probably misaligned with its names."
        )


def bpm_histogram(bpm: np.ndarray, width: int = BPM_BIN) -> list[tuple[int, int]]:
    valid = bpm[bpm > 0]
    if not len(valid):
        return []
    bins = (valid // width).astype(int)
    counts = Counter(bins.tolist())
    return [(b * width, counts.get(b, 0)) for b in range(min(counts), max(counts) + 1)]


@dataclass(frozen=True)
class Cluster:
    size: int
    median_bpm: float
    styles: list[tuple[str, int, float]]
    nearest: list[int]


@dataclass(frozen=True)
class Clustering:
    k: int
    silhouette: float
    clusters: list[Cluster]


def cluster_group(
    emb: np.ndarray,
    bpm: np.ndarray,
    styles: np.ndarray,
    library_share: dict[str, float],
    ks: tuple[int, ...] = CLUSTER_KS,
) -> Clustering | None:
    usable = [k for k in ks if k < len(emb)]
    if not usable:
        return None
    z = StandardScaler().fit_transform(emb)
    best: tuple[float, int, KMeans] | None = None
    for k in usable:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(z)
        score = float(silhouette_score(z, km.labels_))
        if best is None or score > best[0]:
            best = (score, k, km)
    assert best is not None
    score, k, km = best
    clusters = []
    for c in range(k):
        members = np.flatnonzero(km.labels_ == c)
        dist = np.linalg.norm(z[members] - km.cluster_centers_[c], axis=1)
        counts = Counter(styles[members].tolist())
        ranked = sorted(
            (
                (s, n, _ratio(n / len(members), library_share[s]))
                for s, n in counts.items()
                if n >= MIN_CLUSTER_STYLE
            ),
            key=lambda r: -r[2],
        )[:TOP_STYLES]
        clusters.append(
            Cluster(
                len(members),
                float(np.median(bpm[members])),
                ranked,
                members[np.argsort(dist)[:NEAREST]].tolist(),
            )
        )
    return Clustering(k, score, clusters)


def lane_fit(
    pool: list[Track],
    x_pool: np.ndarray,
    untagged: list[Track],
    x_untagged: np.ndarray,
    vocab: frozenset[str],
    oof: dict[str, np.ndarray],
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray]:
    """Base-tag scores: pool rows from out-of-fold, untagged rows from the full-pool model."""
    tasks = ev.make_tasks([p.tags for p in pool], vocab)
    if [t.name for t in tasks] != [str(n) for n in oof["tasks"]]:
        raise ReportInputError(
            "oof_scores.npz tasks differ from the current library; re-run evaluate"
        )
    tag_names = sorted(vocab)
    col_of = {t: i for i, t in enumerate(tag_names)}
    everyone = pool + untagged
    slots, n_artists = ev.artist_slots(everyone)
    tag_matrix = np.zeros((len(everyone), len(tag_names)))
    tag_matrix[: len(pool)] = [[t in p.tags for t in tag_names] for p in pool]
    x_all = np.vstack([x_pool, x_untagged])
    base = [i for i, t in enumerate(tasks) if t.family != "modifier-in-parent"]
    names = [tasks[i].name for i in base]
    thresholds = np.asarray(oof["thresholds"])[base]
    pool_scores = np.asarray(oof["scores"])[:, base]
    new_scores = np.full((len(untagged), len(base)), np.nan, dtype=np.float32)
    for j, i in enumerate(base):
        task = tasks[i]
        if task.insufficient:
            continue
        if task.parent is None:
            gate = np.ones(len(untagged), dtype=bool)
        else:
            p = names.index(task.parent)
            gate = new_scores[:, p] >= thresholds[p]
        pick = np.flatnonzero(gate)
        if not len(pick):
            continue
        n_train = len(task.universe)
        rows = np.concatenate([task.universe, len(pool) + pick])
        y = np.concatenate([task.y, np.zeros(len(pick))])
        out, _ = ev.fold_scores(
            x_all[rows],
            slots[rows],
            tag_matrix[rows],
            y,
            col_of[task.tag],
            np.arange(n_train),
            np.arange(n_train, len(rows)),
            n_artists,
            ("combined",),
        )
        new_scores[pick, j] = out["combined"]
    return names, thresholds, pool_scores, new_scores


def _fmt_styles(items: list[tuple]) -> str:
    return "; ".join(f"{s} ({p:.2f})" for s, p in items)


def _fmt_lane(names: list[str], thresholds: np.ndarray, scores: np.ndarray) -> str:
    hits = [
        (names[j], float(s)) for j, s in enumerate(scores) if not np.isnan(s) and s >= thresholds[j]
    ]
    hits.sort(key=lambda h: -h[1])
    return "; ".join(f"{n} ({s:.2f})" for n, s in hits)


def tracks_rows(
    tracks: list[Track],
    styles: list[list[tuple] | None],
    lane: list[str],
    untagged: list[bool],
    embedded: list[bool],
) -> list[list[Any]]:
    rows = [
        [
            t.artist,
            t.title,
            f"{t.bpm:.1f}",
            "; ".join(sorted(t.tags)),
            _fmt_styles(s) if s else "",
            lf,
            "yes" if u else "",
            "yes" if e else "no",
        ]
        for t, s, lf, u, e in zip(tracks, styles, lane, untagged, embedded, strict=True)
    ]
    return sorted(rows, key=lambda r: r[6] != "yes")


def write_tracks_csv(path: Path, rows: list[list[Any]]) -> None:
    header = [
        "artist",
        "title",
        "bpm",
        "current_tags",
        "top_styles",
        "lane_fit",
        "untagged",
        "embedded",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
        *("| " + " | ".join(r) + " |" for r in rows),
    ]


def render_crosstab(
    control: list[tuple[str, str, str, float]],
    by_tag: dict[str, list[tuple]],
    by_style: dict[str, list[tuple]],
    fuzzy: list[tuple[str, np.ndarray, list[str], Clustering | None]],
    n_tracks: int,
) -> str:
    lines = [
        "# Tag and Discogs style crosstab",
        "",
        f"{n_tracks} tagged tracks with an embedding. Style = each track's top-1 Discogs style. "
        "Library share is the style's share of those same tracks. Lift = share / library share.",
        "",
        "## Positive control",
        "",
    ]
    lines += [
        f"- {t} tracks in {s}: {c} {v:.2f} ({'pass' if control_ok(c, v) else 'FAIL'})"
        for t, s, c, v in control
    ]
    lines += ["", "## (a) Styles per tag"]
    for tag, rows in by_tag.items():
        lines += ["", f"### {tag}", ""]
        lines += _table(
            ["style", "tracks", "share", "library", "lift"],
            [[s, str(c), f"{sh:.2f}", f"{lb:.3f}", f"{lf:.1f}"] for s, c, sh, lb, lf in rows],
        )
    lines += ["", f"## (b) Tags per style (at least {MIN_STYLE_TRACKS} tracks)"]
    for style, rows in by_style.items():
        lines += ["", f"### {style}", ""]
        lines += _table(
            ["tag", "tracks", "share", "library", "lift"],
            [[t, str(c), f"{sh:.2f}", f"{lb:.3f}", f"{lf:.1f}"] for t, c, sh, lb, lf in rows],
        )
    lines += ["", "## (c) Fuzzy tags"]
    for name, bpm, nearest_names, clustering in fuzzy:
        lines += ["", f"### {name} ({len(bpm)} tracks)", "", "BPM, 5-wide bins:", "", "```"]
        hist = bpm_histogram(bpm)
        top = max((c for _, c in hist), default=1)
        lines += [
            f"{lo:>3}-{lo + BPM_BIN - 1:<3} {c:>4} {'#' * round(40 * c / top)}" for lo, c in hist
        ]
        lines.append("```")
        if clustering is None:
            lines += ["", "Too few tracks to cluster."]
            continue
        lines += [
            "",
            f"k-means on standardized effnet embeddings: k={clustering.k} "
            f"(silhouette {clustering.silhouette:.3f}).",
        ]
        for n, c in enumerate(clustering.clusters):
            lines += [
                "",
                f"**Cluster {n + 1}**: {c.size} tracks, median BPM {c.median_bpm:.0f}",
                "",
                "Top styles by lift: "
                + (", ".join(f"{s} ({k}, {lf:.1f}x)" for s, k, lf in c.styles) or "none"),
                "",
                "Nearest the centroid:",
                "",
                *(f"- {nearest_names[i]}" for i in c.nearest),
            ]
    return "\n".join(lines) + "\n"


def read_oof(directory: Path) -> dict[str, np.ndarray]:
    path = directory / "oof_scores.npz"
    if not path.exists():
        raise ReportInputError(f"{path} not found; run `tag evaluate` first")
    with np.load(path) as arrays:
        return {k: arrays[k] for k in arrays.files}


def check_oof_fresh(pool: list[Track], vocab: frozenset[str], oof: dict[str, np.ndarray]) -> None:
    tasks = ev.make_tasks([p.tags for p in pool], vocab)
    support = [t.positives for t in tasks]
    stored = oof.get("support")
    fingerprint = oof.get("fingerprint")
    if (
        stored is None
        or fingerprint is None
        or [int(n) for n in stored] != support
        or str(fingerprint) != ev.pool_fingerprint(pool, vocab)
    ):
        raise ReportInputError("tags changed since evaluate; re-run evaluate")


def run_report(
    tracks: list[Track],
    directory: Path,
    vocab: frozenset[str],
    progress: Callable[[str], None] = print,
) -> None:
    oof = read_oof(directory)
    cache = ev.load_cache(directory)
    labels = [style_label(n) for n in load_class_names(directory)]

    by_id = {t.content_id: t for t in tracks if in_training_pool(t)}
    try:
        pool_all = [by_id[str(i)] for i in oof["ids"]]
    except KeyError as exc:
        raise ReportInputError(
            f"track {exc} in oof_scores.npz is no longer a pool track; re-run evaluate"
        ) from exc
    pool, pool_idx = ev.usable(pool_all, cache)
    if len(pool) != len(pool_all):
        raise ReportInputError(
            "embeddings changed since oof_scores.npz was written; re-run evaluate"
        )
    check_oof_fresh(pool, vocab, oof)
    x_pool = ev.feature_matrix(pool, cache, pool_idx)

    fresh, fresh_idx = ev.usable([t for t in tracks if not t.tags], cache)
    unembedded = sum(1 for t in tracks if not t.tags) - len(fresh)
    x_new = ev.feature_matrix(fresh, cache, fresh_idx)
    progress(f"{len(pool)} pool tracks, {len(fresh)} untagged ({unembedded} without embedding)")

    names, thresholds, pool_scores, new_scores = lane_fit(pool, x_pool, fresh, x_new, vocab, oof)

    pool_styles = top1_styles(cache.genre[pool_idx], labels)
    has = {tag: np.array([tag in t.tags for t in pool]) for tag in sorted(vocab)}
    control = positive_control(pool_styles, has)
    for tag, style, check, value in control:
        progress(f"positive control: {tag} in {style} {check} {value:.2f}")
    check_positive_control(control)

    library_share = {s: float(c) / len(pool) for s, c in Counter(pool_styles.tolist()).items()}
    genre_mask = np.any([has[g] for g in GENRES if g in has], axis=0)
    emb = x_pool[:, :EFFNET_DIM]
    bpm = np.array([t.bpm for t in pool])
    pool_names = [f"{t.artist} - {t.title}" for t in pool]
    none = np.zeros(len(pool), dtype=bool)
    weird, halftime = has.get("WEIRD", none), has.get("Halftime", none)
    groups = [
        ("WEIRD", weird),
        ("WEIRD without a genre tag", weird & ~genre_mask),
        ("Halftime", halftime),
    ]
    fuzzy = []
    for name, mask in groups:
        sel = np.flatnonzero(mask)
        clustering = cluster_group(emb[sel], bpm[sel], pool_styles[sel], library_share)
        fuzzy.append((name, bpm[sel], [pool_names[i] for i in sel], clustering))

    crosstab = render_crosstab(
        control,
        tag_to_styles(pool_styles, has),
        style_to_tags(pool_styles, has),
        fuzzy,
        len(pool),
    )

    pool_top = top_styles(cache.genre[pool_idx], labels)
    new_top = top_styles(cache.genre[fresh_idx], labels)
    lane = [_fmt_lane(names, thresholds, s) for s in (*pool_scores, *new_scores)]
    embedded = {t.content_id for t in fresh}
    bare = [t for t in tracks if not t.tags and t.content_id not in embedded]
    rows = tracks_rows(
        pool + fresh + bare,
        [*pool_top, *new_top, *([None] * len(bare))],
        [*lane, *([""] * len(bare))],
        [False] * len(pool) + [True] * (len(fresh) + len(bare)),
        [True] * (len(pool) + len(fresh)) + [False] * len(bare),
    )

    directory.mkdir(parents=True, exist_ok=True)
    write_tracks_csv(directory / "tracks.csv", rows)
    (directory / "crosstab.md").write_text(crosstab)
    progress(f"wrote tracks.csv ({len(rows)} rows) and crosstab.md to {directory}")
