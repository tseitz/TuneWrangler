"""Offline resolver + audit for playlist-data JSON configs.

Mirrors PlaylistManager's resolution semantics (base injection, folder links,
mainConditions accumulation) WITHOUT touching the Rekordbox database, so playlist
structure, leaf counts, and broken links can be verified in isolation.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Contexts expected to resolve to an identical structural shape. This module is
# the acceptance oracle for later tasks, so any drift between these contexts
# (differing shapes, or an expected file gone missing) is a structural
# regression that must fail the audit.
UNIFORM_CONTEXTS: tuple[str, ...] = (
    "daytime",
    "nighttime",
    "late-night",
    "sunrise",
    "chillin",
    "afterparty",
    "morningtime-vibes",
    "pool-party",
    "crispy-speakers",
    "missy",
    "b2b",
    "silent-disco",
    "frankys-beach",
    "ketamine-music",
    "frankys-after",
)

# Top-level folders that MAY optionally augment a context (e.g. a Clean/ view on
# kid-friendly contexts) without breaking the uniform-core guarantee. Leaves under
# these are excluded when comparing contexts for structural uniformity.
AUGMENTABLE_SUBTREES: tuple[str, ...] = ("Clean",)


@dataclass(frozen=True)
class Leaf:
    """A resolved smart playlist (leaf node)."""

    path: tuple[str, ...]  # folder chain from root context to this leaf's parent
    name: str
    conditions: frozenset[str]  # ANDed MyTag CONTAINS conditions
    negatives: frozenset[str]  # NOT-CONTAINS conditions


@dataclass
class AuditResult:
    leaves: list[Leaf] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _load(path: Path) -> dict[str, Any]:
    """Read and parse a JSON file. Raises on malformed or unreadable input."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_load(path: Path, errors: list[str]) -> dict[str, Any] | None:
    """Load JSON, recording any read/parse failure as an error string.

    Mirrors how the real generator tolerates bad files (core/playlist_manager.py
    lines 525, 560-563): a malformed or unreadable file is reported, not raised.
    """
    try:
        return _load(path)
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"Failed to read {path.name}: {e}")
        return None


def _resolve_base(
    category: dict[str, Any], base_dir: Path, errors: list[str]
) -> list[dict[str, Any]]:
    base_ref = category.get("base")
    if not base_ref:
        return []
    base_path = base_dir / base_ref
    if not base_path.exists():
        errors.append(f"Missing base file: {base_ref}")
        return []
    loaded = _safe_load(base_path, errors)
    if loaded is None:
        return []
    return list(loaded.get("data", {}).get("playlists", []))


def _process_category(
    category: dict[str, Any],
    base_dir: Path,
    inherited_main: frozenset[str],
    inherited_neg: frozenset[str],
    folder_path: tuple[str, ...],
    out: AuditResult,
) -> None:
    main = inherited_main | set(category.get("mainConditions", []))
    neg = inherited_neg | set(category.get("negativeConditions", []))
    playlists = _resolve_base(category, base_dir, out.errors) + list(category.get("playlists", []))

    for pl in playlists:
        if pl.get("playlistType") == "folder":
            name = pl.get("name", "")
            link = pl.get("link")
            here = "/".join(folder_path)
            if not link:
                out.errors.append(f"Folder '{name}' missing link (in {here})")
                continue
            link_path = base_dir / link
            if not link_path.exists():
                out.errors.append(f"Broken link: {link} (in {here}/{name})")
                continue
            loaded = _safe_load(link_path, out.errors)
            if loaded is None:
                continue
            child_path = folder_path + (name,)
            linked = loaded.get("data", [])
            categories = linked if isinstance(linked, list) else [linked]
            for sub in categories:
                _process_category(sub, base_dir, main, neg, child_path, out)
        else:
            conditions = main | set(pl.get("contains", []))
            negatives = neg | set(pl.get("doesNotContain", []))
            out.leaves.append(
                Leaf(folder_path, pl.get("name", ""), frozenset(conditions), frozenset(negatives))
            )


def resolve_context(path: Path, base_dir: Path) -> AuditResult:
    """Resolve a single top-level context file into its leaf playlists.

    A malformed or unreadable context file is recorded in ``errors`` and yields
    no leaves, rather than raising, so a single bad file cannot abort an audit.
    """
    out = AuditResult()
    loaded = _safe_load(path, out.errors)
    if loaded is None:
        return out
    data = loaded.get("data", [])
    categories = data if isinstance(data, list) else [data]
    for cat in categories:
        parent = cat.get("parent", "")
        _process_category(cat, base_dir, frozenset(), frozenset(), (parent,), out)
    return out


# --- CLI -------------------------------------------------------------------


def _context_files(directory: Path) -> list[Path]:
    return sorted(
        f
        for f in directory.glob("*.json")
        if not f.name.startswith(".") and not f.name.startswith("_")
    )


def _signature(leaves: list[Leaf], ignore: tuple[str, ...] = ()) -> tuple:
    """Structural fingerprint ignoring the root context name (path[0]).

    Leaves whose first sub-folder is in ``ignore`` are dropped, so optional
    augmentations (see ``AUGMENTABLE_SUBTREES``) don't count against uniformity.
    """
    return tuple(
        sorted(
            (leaf.path[1:], leaf.name)
            for leaf in leaves
            if not (len(leaf.path) > 1 and leaf.path[1] in ignore)
        )
    )


def _check_uniformity(sigs: dict[str, tuple], errors: list[str]) -> None:
    """Verify the UNIFORM_CONTEXTS resolve to one identical shape.

    The check is skipped when none of them are present (e.g. an unrelated
    directory). Otherwise, either a differing shape or a missing expected file
    is recorded as an error so it drives a non-zero exit code.
    """
    present = {name: sigs[name] for name in UNIFORM_CONTEXTS if name in sigs}
    if not present:
        return
    missing = [name for name in UNIFORM_CONTEXTS if name not in sigs]
    distinct = set(present.values())
    if not missing and len(distinct) == 1:
        print(f"Uniformity: OK ({len(UNIFORM_CONTEXTS)} contexts share an identical core)")
        return
    parts = []
    if len(distinct) > 1:
        parts.append(f"{len(distinct)} distinct shapes among {len(present)} present")
    if missing:
        parts.append(f"missing {', '.join(missing)}")
    detail = "; ".join(parts)
    print(f"Uniformity: MISMATCH ({detail})")
    errors.append(f"Uniformity MISMATCH: {detail}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    directory = Path(argv[0]) if argv else Path("playlist-data")

    total = 0
    errors: list[str] = []
    sigs: dict[str, tuple] = {}
    for f in _context_files(directory):
        res = resolve_context(f, directory)
        total += len(res.leaves)
        errors.extend(res.errors)
        sigs[f.stem] = _signature(res.leaves, ignore=AUGMENTABLE_SUBTREES)
        print(f"{f.name:28s} {len(res.leaves):5d} leaves")

    print("-" * 36)
    print(f"{'TOTAL':28s} {total:5d} leaves")

    _check_uniformity(sigs, errors)

    if errors:
        print("\nERRORS:")
        for e in errors:
            print("  -", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
