# Playlist Architecture Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ~4,340-playlist "situation × texture × genre" explosion with a uniform, DRY, ~1,090-leaf structure (Situation-first, one-lens-second) driven by reusable JSON helper files.

**Architecture:** This is a **data restructure**, not a code rewrite. The existing generator (`playlist_manager.py`) already accumulates `mainConditions` across folder `link`s and prepends `base` playlists, which is exactly what the design needs. We add **one new module** — a pure, DB-free resolver/auditor (`audit.py`) — as the TDD-able verification backbone, then rebuild the `playlist-data/*.json` files around reusable lens (`Flow`/`Genre`/`Texture`) and caliber (`My Set`/`The Rotation`) helpers.

**Tech Stack:** Python 3.10, pytest 8.4.1 (in `venv/`), stdlib `json`/`pathlib`, pyrekordbox (only for the optional final DB dry-run).

**Design spec:** `docs/superpowers/specs/2026-07-07-playlist-architecture-design.md`

**Conventions used throughout:**
- Run everything inside the venv: prefix commands with `source venv/bin/activate &&` (shown once per task).
- Genre tags (11): `Beats, DnB, Dub, Dubstep, Feels, House, Jungle, Riddim, UKG, Vibes, Weapons`
- Texture tags (6 core + palate): `GROOVY (The Pocket)`, `DEEP (The Head)`, `HEAVY (The Face)`, `ORGANIC (The Soul)`, `WEIRD (The Brain)`, `VOCALS`, `PALATE CLEANSER`
- Flow tags (5): `Openers, Beginning, Middle, End, Closers`
- Caliber tags: `My Set`, `The Rotation`
- Every context carries `"negativeConditions": ["Archive"]`.

---

## File Structure

**New Python (verification backbone):**
- Create `rekordbox_smart_playlists/audit.py` — pure resolver mirroring `PlaylistManager` semantics + `main()` CLI.
- Create `tests/__init__.py` and `tests/test_audit.py` — unit tests for the resolver.

**New reusable helpers (`playlist-data/helpers/`):**
- `_genres.json` — dict-style base: 11 genre playlists.
- `lens-genre.json` — Genre folder body (injects `_genres.json`).
- `lens-flow.json` — Flow folder body (5 flow playlists).
- `lens-texture.json` — full Texture folder body (6 singles + Palate + `Combos/` link).
- `lens-texture-combos.json` — curated texture pairs (~10).
- `lens-texture-lite.json` — singles + Palate only (for Rotation).
- `caliber-my-set.json` — My Set sub-tree (All + Genre + Texture-full), tag `My Set`.
- `caliber-rotation.json` — The Rotation sub-tree (All + Genre + Texture-lite), tag `The Rotation`.

**Rebuilt context files (`playlist-data/`):** 12 uniform contexts + 1 global My Set, all from one template:
`daytime, nighttime, late-night, sunrise, chillin, afterparty, morningtime-vibes, pool-party, crispy-speakers, missy, b2b, silent-disco` (uniform) + `my-set` (global, no caliber).

**Rebuilt global Genres tree:** `genres.json` + `genres/*.json` (sub-styles only; drop the texture-mirror base).

**Updated:** `_order.json`.

**Deleted (now unreferenced):** `rotation.json`, `helpers/deep.json`, `helpers/groovy.json`, `helpers/heavy.json`, `helpers/organic.json`, `helpers/weird.json`, `helpers/vocal.json`, `helpers/palate_cleanser.json`, `helpers/_base.json`, `templates/show.json`, `genres/_base.json`.

**Left as-is:** `old/` (not processed — directory glob is non-recursive), `go-through.json`.

---

## Task 1: Offline resolver + audit tool (TDD)

**Files:**
- Create: `rekordbox_smart_playlists/audit.py`
- Create: `tests/__init__.py`
- Test: `tests/test_audit.py`

- [ ] **Step 1: Create the empty test package**

```bash
mkdir -p tests
printf '' > tests/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_audit.py`:

```python
import json
from pathlib import Path

from rekordbox_smart_playlists.audit import resolve_context, Leaf


def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_top_level_conditions_and_base(tmp_path: Path):
    # base file (dict-style) with two genre playlists
    _write(tmp_path / "_genres.json", {
        "data": {"playlists": [
            {"name": "Dub", "operator": 1, "contains": ["Dub"]},
            {"name": "House", "operator": 1, "contains": ["House"]},
        ]}
    })
    # a Genre lens that injects the base
    _write(tmp_path / "lens-genre.json", {
        "data": [{"mainConditions": [], "base": "_genres.json", "playlists": []}]
    })
    # context linking to the Genre folder + a direct "All"
    _write(tmp_path / "nighttime.json", {
        "data": [{
            "parent": "Nighttime",
            "mainConditions": ["Nighttime"],
            "negativeConditions": ["Archive"],
            "playlists": [
                {"name": "All", "operator": 1, "contains": []},
                {"name": "Genre", "operator": 1, "playlistType": "folder",
                 "link": "lens-genre.json"},
            ],
        }]
    })

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.errors == []
    by_name = {leaf.name: leaf for leaf in result.leaves}
    # 1 "All" + 2 injected genres
    assert set(by_name) == {"All", "Dub", "House"}
    # "All" lives directly under the context, carries only the context tag
    assert by_name["All"].path == ("Nighttime",)
    assert by_name["All"].conditions == frozenset({"Nighttime"})
    assert by_name["All"].negatives == frozenset({"Archive"})
    # genres live under Nighttime/Genre and AND the context tag
    assert by_name["Dub"].path == ("Nighttime", "Genre")
    assert by_name["Dub"].conditions == frozenset({"Nighttime", "Dub"})


def test_mainconditions_accumulate_across_nested_links(tmp_path: Path):
    _write(tmp_path / "_genres.json", {
        "data": {"playlists": [{"name": "Dub", "operator": 1, "contains": ["Dub"]}]}
    })
    _write(tmp_path / "lens-genre.json", {
        "data": [{"mainConditions": [], "base": "_genres.json", "playlists": []}]
    })
    # caliber sub-tree that adds "My Set" and re-links the Genre lens
    _write(tmp_path / "caliber-my-set.json", {
        "data": [{"mainConditions": ["My Set"], "playlists": [
            {"name": "Genre", "operator": 1, "playlistType": "folder",
             "link": "lens-genre.json"},
        ]}]
    })
    _write(tmp_path / "nighttime.json", {
        "data": [{
            "parent": "Nighttime", "mainConditions": ["Nighttime"],
            "negativeConditions": ["Archive"],
            "playlists": [
                {"name": "My Set", "operator": 1, "playlistType": "folder",
                 "link": "caliber-my-set.json"},
            ],
        }]
    })

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.errors == []
    assert len(result.leaves) == 1
    dub = result.leaves[0]
    assert dub.name == "Dub"
    assert dub.path == ("Nighttime", "My Set", "Genre")
    assert dub.conditions == frozenset({"Nighttime", "My Set", "Dub"})


def test_broken_link_is_reported_not_raised(tmp_path: Path):
    _write(tmp_path / "nighttime.json", {
        "data": [{
            "parent": "Nighttime", "mainConditions": ["Nighttime"],
            "playlists": [
                {"name": "Genre", "operator": 1, "playlistType": "folder",
                 "link": "does-not-exist.json"},
            ],
        }]
    })

    result = resolve_context(tmp_path / "nighttime.json", tmp_path)

    assert result.leaves == []
    assert len(result.errors) == 1
    assert "does-not-exist.json" in result.errors[0]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `source venv/bin/activate && pytest tests/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rekordbox_smart_playlists.audit'`

- [ ] **Step 4: Write the resolver implementation**

Create `rekordbox_smart_playlists/audit.py`:

```python
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
from typing import List, Tuple


@dataclass(frozen=True)
class Leaf:
    """A resolved smart playlist (leaf node)."""

    path: Tuple[str, ...]          # folder chain from root context to this leaf's parent
    name: str
    conditions: frozenset          # ANDed MyTag CONTAINS conditions
    negatives: frozenset           # NOT-CONTAINS conditions


@dataclass
class AuditResult:
    leaves: List[Leaf] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_base(category: dict, base_dir: Path, errors: List[str]) -> List[dict]:
    base_ref = category.get("base")
    if not base_ref:
        return []
    base_path = base_dir / base_ref
    if not base_path.exists():
        errors.append(f"Missing base file: {base_ref}")
        return []
    data = _load(base_path).get("data", {})
    return list(data.get("playlists", []))


def _process_category(
    category: dict,
    base_dir: Path,
    inherited_main: frozenset,
    inherited_neg: frozenset,
    folder_path: Tuple[str, ...],
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
            child_path = folder_path + (name,)
            linked = _load(link_path).get("data", [])
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
    """Resolve a single top-level context file into its leaf playlists."""
    out = AuditResult()
    data = _load(path).get("data", [])
    categories = data if isinstance(data, list) else [data]
    for cat in categories:
        parent = cat.get("parent", "")
        _process_category(cat, base_dir, frozenset(), frozenset(), (parent,), out)
    return out


# --- CLI -------------------------------------------------------------------

def _context_files(directory: Path) -> List[Path]:
    return sorted(
        f for f in directory.glob("*.json")
        if not f.name.startswith(".") and not f.name.startswith("_")
    )


def _signature(leaves: List[Leaf]) -> Tuple:
    """Structural fingerprint ignoring the root context name (path[0])."""
    return tuple(sorted((leaf.path[1:], leaf.name) for leaf in leaves))


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    directory = Path(argv[0]) if argv else Path("playlist-data")

    total = 0
    errors: List[str] = []
    sigs = {}
    for f in _context_files(directory):
        res = resolve_context(f, directory)
        total += len(res.leaves)
        errors.extend(res.errors)
        sigs[f.stem] = _signature(res.leaves)
        print(f"{f.name:28s} {len(res.leaves):5d} leaves")

    print("-" * 36)
    print(f"{'TOTAL':28s} {total:5d} leaves")

    # Uniformity: the 12 uniform contexts must share one structural signature.
    uniform = [
        "daytime", "nighttime", "late-night", "sunrise", "chillin", "afterparty",
        "morningtime-vibes", "pool-party", "crispy-speakers", "missy", "b2b",
        "silent-disco",
    ]
    present = {name: sigs[name] for name in uniform if name in sigs}
    distinct = set(present.values())
    if len(present) == len(uniform) and len(distinct) == 1:
        print(f"Uniformity: OK ({len(uniform)} contexts identical)")
    elif present:
        print(f"Uniformity: MISMATCH ({len(distinct)} distinct shapes among "
              f"{len(present)}/{len(uniform)} present)")

    if errors:
        print("\nERRORS:")
        for e in errors:
            print("  -", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source venv/bin/activate && pytest tests/test_audit.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add rekordbox_smart_playlists/audit.py tests/__init__.py tests/test_audit.py
git commit -m "feat(audit): add offline playlist resolver and audit CLI"
```

---

## Task 2: Genre base + Genre lens

**Files:**
- Create: `playlist-data/helpers/_genres.json`
- Create: `playlist-data/helpers/lens-genre.json`

- [ ] **Step 1: Write the genre base**

Create `playlist-data/helpers/_genres.json`:

```json
{
  "data": {
    "playlists": [
      { "name": "Beats", "operator": 1, "contains": ["Beats"] },
      { "name": "DnB", "operator": 1, "contains": ["DnB"] },
      { "name": "Dub", "operator": 1, "contains": ["Dub"] },
      { "name": "Dubstep", "operator": 1, "contains": ["Dubstep"] },
      { "name": "Feels", "operator": 1, "contains": ["Feels"] },
      { "name": "House", "operator": 1, "contains": ["House"] },
      { "name": "Jungle", "operator": 1, "contains": ["Jungle"] },
      { "name": "Riddim", "operator": 1, "contains": ["Riddim"] },
      { "name": "UKG", "operator": 1, "contains": ["UKG"] },
      { "name": "Vibes", "operator": 1, "contains": ["Vibes"] },
      { "name": "Weapons", "operator": 1, "contains": ["Weapons"] }
    ]
  }
}
```

- [ ] **Step 2: Write the Genre lens body**

Create `playlist-data/helpers/lens-genre.json`:

```json
{
  "data": [
    {
      "parent": "Genre",
      "mainConditions": [],
      "base": "helpers/_genres.json",
      "playlists": []
    }
  ]
}
```

- [ ] **Step 3: Verify the lens resolves to 11 genres**

Run:
```bash
source venv/bin/activate && python -c "
from pathlib import Path
from rekordbox_smart_playlists.audit import resolve_context
r = resolve_context(Path('playlist-data/helpers/lens-genre.json'), Path('playlist-data'))
print('leaves:', len(r.leaves), 'errors:', r.errors)
print(sorted(l.name for l in r.leaves))
"
```
Expected: `leaves: 11 errors: []` and the 11 genre names.

- [ ] **Step 4: Commit**

```bash
git add playlist-data/helpers/_genres.json playlist-data/helpers/lens-genre.json
git commit -m "feat(playlists): add genre base and genre lens helpers"
```

---

## Task 3: Texture lens helpers (full, combos, lite)

**Files:**
- Create: `playlist-data/helpers/lens-texture-combos.json`
- Create: `playlist-data/helpers/lens-texture.json`
- Create: `playlist-data/helpers/lens-texture-lite.json`

- [ ] **Step 1: Write the curated combos**

Create `playlist-data/helpers/lens-texture-combos.json` (10 curated pairs — adjust list later as desired):

```json
{
  "data": [
    {
      "parent": "Combos",
      "mainConditions": [],
      "playlists": [
        { "name": "Groovy + Deep", "operator": 1, "contains": ["GROOVY (The Pocket)", "DEEP (The Head)"] },
        { "name": "Groovy + Heavy", "operator": 1, "contains": ["GROOVY (The Pocket)", "HEAVY (The Face)"] },
        { "name": "Groovy + Organic", "operator": 1, "contains": ["GROOVY (The Pocket)", "ORGANIC (The Soul)"] },
        { "name": "Groovy + Vocals", "operator": 1, "contains": ["GROOVY (The Pocket)", "VOCALS"] },
        { "name": "Deep + Organic", "operator": 1, "contains": ["DEEP (The Head)", "ORGANIC (The Soul)"] },
        { "name": "Deep + Heavy", "operator": 1, "contains": ["DEEP (The Head)", "HEAVY (The Face)"] },
        { "name": "Deep + Weird", "operator": 1, "contains": ["DEEP (The Head)", "WEIRD (The Brain)"] },
        { "name": "Heavy + Weird", "operator": 1, "contains": ["HEAVY (The Face)", "WEIRD (The Brain)"] },
        { "name": "Heavy + Vocals", "operator": 1, "contains": ["HEAVY (The Face)", "VOCALS"] },
        { "name": "Organic + Vocals", "operator": 1, "contains": ["ORGANIC (The Soul)", "VOCALS"] }
      ]
    }
  ]
}
```

- [ ] **Step 2: Write the full Texture lens (singles + Palate + Combos folder)**

Create `playlist-data/helpers/lens-texture.json`:

```json
{
  "data": [
    {
      "parent": "Texture",
      "mainConditions": [],
      "playlists": [
        { "name": "Groovy", "operator": 1, "contains": ["GROOVY (The Pocket)"] },
        { "name": "Deep", "operator": 1, "contains": ["DEEP (The Head)"] },
        { "name": "Heavy", "operator": 1, "contains": ["HEAVY (The Face)"] },
        { "name": "Organic", "operator": 1, "contains": ["ORGANIC (The Soul)"] },
        { "name": "Vocals", "operator": 1, "contains": ["VOCALS"] },
        { "name": "Weird", "operator": 1, "contains": ["WEIRD (The Brain)"] },
        { "name": "Palate Cleanser", "operator": 1, "contains": ["PALATE CLEANSER"] },
        { "name": "Combos", "operator": 1, "playlistType": "folder", "link": "helpers/lens-texture-combos.json" }
      ]
    }
  ]
}
```

- [ ] **Step 3: Write the lite Texture lens (singles + Palate, no combos)**

Create `playlist-data/helpers/lens-texture-lite.json`:

```json
{
  "data": [
    {
      "parent": "Texture",
      "mainConditions": [],
      "playlists": [
        { "name": "Groovy", "operator": 1, "contains": ["GROOVY (The Pocket)"] },
        { "name": "Deep", "operator": 1, "contains": ["DEEP (The Head)"] },
        { "name": "Heavy", "operator": 1, "contains": ["HEAVY (The Face)"] },
        { "name": "Organic", "operator": 1, "contains": ["ORGANIC (The Soul)"] },
        { "name": "Vocals", "operator": 1, "contains": ["VOCALS"] },
        { "name": "Weird", "operator": 1, "contains": ["WEIRD (The Brain)"] },
        { "name": "Palate Cleanser", "operator": 1, "contains": ["PALATE CLEANSER"] }
      ]
    }
  ]
}
```

- [ ] **Step 4: Verify texture lens resolves to 17 (7 singles + 10 combos) and lite to 7**

Run:
```bash
source venv/bin/activate && python -c "
from pathlib import Path
from rekordbox_smart_playlists.audit import resolve_context
base = Path('playlist-data')
full = resolve_context(base / 'helpers/lens-texture.json', base)
lite = resolve_context(base / 'helpers/lens-texture-lite.json', base)
print('full:', len(full.leaves), 'errors:', full.errors)
print('lite:', len(lite.leaves), 'errors:', lite.errors)
"
```
Expected: `full: 17 errors: []` and `lite: 7 errors: []`.

- [ ] **Step 5: Commit**

```bash
git add playlist-data/helpers/lens-texture.json playlist-data/helpers/lens-texture-lite.json playlist-data/helpers/lens-texture-combos.json
git commit -m "feat(playlists): add texture lens helpers (full, lite, combos)"
```

---

## Task 4: Flow lens helper

**Files:**
- Create: `playlist-data/helpers/lens-flow.json`

- [ ] **Step 1: Write the Flow lens**

Create `playlist-data/helpers/lens-flow.json`:

```json
{
  "data": [
    {
      "parent": "Flow",
      "mainConditions": [],
      "playlists": [
        { "name": "Openers", "operator": 1, "contains": ["Openers"] },
        { "name": "Beginning", "operator": 1, "contains": ["Beginning"] },
        { "name": "Middle", "operator": 1, "contains": ["Middle"] },
        { "name": "End", "operator": 1, "contains": ["End"] },
        { "name": "Closers", "operator": 1, "contains": ["Closers"] }
      ]
    }
  ]
}
```

- [ ] **Step 2: Verify it resolves to 5**

Run:
```bash
source venv/bin/activate && python -c "
from pathlib import Path
from rekordbox_smart_playlists.audit import resolve_context
r = resolve_context(Path('playlist-data/helpers/lens-flow.json'), Path('playlist-data'))
print('leaves:', len(r.leaves), 'errors:', r.errors)
"
```
Expected: `leaves: 5 errors: []`

- [ ] **Step 3: Commit**

```bash
git add playlist-data/helpers/lens-flow.json
git commit -m "feat(playlists): add flow lens helper"
```

---

## Task 5: Caliber helpers (My Set, The Rotation)

**Files:**
- Create: `playlist-data/helpers/caliber-my-set.json`
- Create: `playlist-data/helpers/caliber-rotation.json`

- [ ] **Step 1: Write the My Set caliber sub-tree (full)**

Create `playlist-data/helpers/caliber-my-set.json`:

```json
{
  "data": [
    {
      "parent": "My Set",
      "mainConditions": ["My Set"],
      "playlists": [
        { "name": "All", "operator": 1, "contains": [] },
        { "name": "Genre", "operator": 1, "playlistType": "folder", "link": "helpers/lens-genre.json" },
        { "name": "Texture", "operator": 1, "playlistType": "folder", "link": "helpers/lens-texture.json" }
      ]
    }
  ]
}
```

- [ ] **Step 2: Write the Rotation caliber sub-tree (lite texture)**

Create `playlist-data/helpers/caliber-rotation.json`:

```json
{
  "data": [
    {
      "parent": "The Rotation",
      "mainConditions": ["The Rotation"],
      "playlists": [
        { "name": "All", "operator": 1, "contains": [] },
        { "name": "Genre", "operator": 1, "playlistType": "folder", "link": "helpers/lens-genre.json" },
        { "name": "Texture", "operator": 1, "playlistType": "folder", "link": "helpers/lens-texture-lite.json" }
      ]
    }
  ]
}
```

- [ ] **Step 3: Verify caliber sub-trees resolve (My Set = 29, Rotation = 19) with accumulated tags**

Run:
```bash
source venv/bin/activate && python -c "
from pathlib import Path
from rekordbox_smart_playlists.audit import resolve_context
base = Path('playlist-data')
ms = resolve_context(base / 'helpers/caliber-my-set.json', base)
rot = resolve_context(base / 'helpers/caliber-rotation.json', base)
print('my-set:', len(ms.leaves), 'errors:', ms.errors)
print('rotation:', len(rot.leaves), 'errors:', rot.errors)
# every my-set leaf must carry the My Set tag
print('all carry My Set:', all('My Set' in l.conditions for l in ms.leaves))
print('all carry The Rotation:', all('The Rotation' in l.conditions for l in rot.leaves))
"
```
Expected: `my-set: 29 errors: []`, `rotation: 19 errors: []`, both `all carry ...: True`.

- [ ] **Step 4: Commit**

```bash
git add playlist-data/helpers/caliber-my-set.json playlist-data/helpers/caliber-rotation.json
git commit -m "feat(playlists): add My Set and Rotation caliber sub-trees"
```

---

## Task 6: Canonical context template (Nighttime)

Rebuild ONE context first, verify its shape (82 leaves), and lock the template
before rolling it out.

**Files:**
- Modify (overwrite): `playlist-data/nighttime.json`

- [ ] **Step 1: Overwrite `nighttime.json` with the uniform template**

Replace the entire contents of `playlist-data/nighttime.json`:

```json
{
  "data": [
    {
      "parent": "Nighttime",
      "mainConditions": ["Nighttime"],
      "negativeConditions": ["Archive"],
      "playlists": [
        { "name": "All", "operator": 1, "contains": [] },
        { "name": "Flow", "operator": 1, "playlistType": "folder", "link": "helpers/lens-flow.json" },
        { "name": "Genre", "operator": 1, "playlistType": "folder", "link": "helpers/lens-genre.json" },
        { "name": "Texture", "operator": 1, "playlistType": "folder", "link": "helpers/lens-texture.json" },
        { "name": "My Set", "operator": 1, "playlistType": "folder", "link": "helpers/caliber-my-set.json" },
        { "name": "The Rotation", "operator": 1, "playlistType": "folder", "link": "helpers/caliber-rotation.json" }
      ]
    }
  ]
}
```

- [ ] **Step 2: Verify the full context resolves to 82 leaves with no errors**

Run:
```bash
source venv/bin/activate && python -c "
from pathlib import Path
from rekordbox_smart_playlists.audit import resolve_context
r = resolve_context(Path('playlist-data/nighttime.json'), Path('playlist-data'))
print('leaves:', len(r.leaves), 'errors:', r.errors)
# every leaf must carry the context tag; none may be empty-named
print('all carry Nighttime:', all('Nighttime' in l.conditions for l in r.leaves))
print('all Archive-excluded:', all('Archive' in l.negatives for l in r.leaves))
"
```
Expected: `leaves: 82 errors: []`, `all carry Nighttime: True`, `all Archive-excluded: True`.

- [ ] **Step 3: Commit**

```bash
git add playlist-data/nighttime.json
git commit -m "feat(playlists): rebuild Nighttime as canonical uniform context"
```

---

## Task 7: Roll the template to all 12 uniform contexts

Generate the remaining 11 uniform contexts from the same template. Using a
one-shot script guarantees they are byte-identical except `parent`/tag.

**Files:**
- Modify (overwrite): `daytime, late-night, sunrise, chillin, afterparty, morningtime-vibes, pool-party, crispy-speakers, missy, b2b, silent-disco` (`.json` each, in `playlist-data/`)

- [ ] **Step 1: Write the 11 context files from the template**

Run this exact script:

```bash
source venv/bin/activate && python -c "
import json
from pathlib import Path

base = Path('playlist-data')
# (filename stem, parent folder name, situation tag)
contexts = [
    ('daytime', 'Daytime', 'Daytime'),
    ('late-night', 'Late Night', 'Late Night'),
    ('sunrise', 'Sunrise', 'Sunrise'),
    ('chillin', 'Chillin', 'Chillin'),
    ('afterparty', 'Afterparty', 'Afterparty'),
    ('morningtime-vibes', 'Morningtime Vibes', 'Morningtime Vibes'),
    ('pool-party', 'Pool Party', 'Pool Party'),
    ('crispy-speakers', 'Crispy Speakers', 'Crispy Speakers'),
    ('missy', 'Missy', 'Missy'),
    ('b2b', 'B2B', 'B2B'),
    ('silent-disco', 'Silent Disco', 'Silent Disco'),
]

def template(parent, tag):
    return {'data': [{
        'parent': parent,
        'mainConditions': [tag],
        'negativeConditions': ['Archive'],
        'playlists': [
            {'name': 'All', 'operator': 1, 'contains': []},
            {'name': 'Flow', 'operator': 1, 'playlistType': 'folder', 'link': 'helpers/lens-flow.json'},
            {'name': 'Genre', 'operator': 1, 'playlistType': 'folder', 'link': 'helpers/lens-genre.json'},
            {'name': 'Texture', 'operator': 1, 'playlistType': 'folder', 'link': 'helpers/lens-texture.json'},
            {'name': 'My Set', 'operator': 1, 'playlistType': 'folder', 'link': 'helpers/caliber-my-set.json'},
            {'name': 'The Rotation', 'operator': 1, 'playlistType': 'folder', 'link': 'helpers/caliber-rotation.json'},
        ],
    }]}

for stem, parent, tag in contexts:
    (base / f'{stem}.json').write_text(json.dumps(template(parent, tag), indent=2) + '\n', encoding='utf-8')
    print('wrote', stem)
"
```

- [ ] **Step 2: Verify all 12 uniform contexts are structurally identical**

Run:
```bash
source venv/bin/activate && python -m rekordbox_smart_playlists.audit playlist-data
```
Expected: each of the 12 uniform contexts shows `82 leaves`, and the output line `Uniformity: OK (12 contexts identical)`. (Non-uniform files like `my-set.json`/`genres.json` are still the OLD versions at this point — they are rebuilt in Tasks 8–9. That is fine; only the 12 uniform contexts are asserted here.)

- [ ] **Step 3: Commit**

```bash
git add playlist-data/daytime.json playlist-data/late-night.json playlist-data/sunrise.json playlist-data/chillin.json playlist-data/afterparty.json playlist-data/morningtime-vibes.json playlist-data/pool-party.json playlist-data/crispy-speakers.json playlist-data/missy.json playlist-data/b2b.json playlist-data/silent-disco.json
git commit -m "feat(playlists): roll uniform template to all 12 contexts"
```

---

## Task 8: Global My Set context

`My Set` global is the situation-independent S-tier browse — full lens, **no**
caliber nesting (nesting My Set inside My Set is redundant).

**Files:**
- Modify (overwrite): `playlist-data/my-set.json`

- [ ] **Step 1: Overwrite `my-set.json`**

Replace the entire contents of `playlist-data/my-set.json`:

```json
{
  "data": [
    {
      "parent": "My Set",
      "mainConditions": ["My Set"],
      "negativeConditions": ["Archive"],
      "playlists": [
        { "name": "All", "operator": 1, "contains": [] },
        { "name": "Flow", "operator": 1, "playlistType": "folder", "link": "helpers/lens-flow.json" },
        { "name": "Genre", "operator": 1, "playlistType": "folder", "link": "helpers/lens-genre.json" },
        { "name": "Texture", "operator": 1, "playlistType": "folder", "link": "helpers/lens-texture.json" }
      ]
    }
  ]
}
```

- [ ] **Step 2: Verify My Set global resolves to 34**

Run:
```bash
source venv/bin/activate && python -c "
from pathlib import Path
from rekordbox_smart_playlists.audit import resolve_context
r = resolve_context(Path('playlist-data/my-set.json'), Path('playlist-data'))
print('leaves:', len(r.leaves), 'errors:', r.errors)
print('all carry My Set:', all('My Set' in l.conditions for l in r.leaves))
"
```
Expected: `leaves: 34 errors: []`, `all carry My Set: True`.

- [ ] **Step 3: Commit**

```bash
git add playlist-data/my-set.json
git commit -m "feat(playlists): rebuild global My Set context (full lens, no caliber)"
```

---

## Task 9: Global Genres tree (sub-styles only)

Rebuild the genre-first browser: `Genres/<genre>/{All + sub-styles}`. Drop the
old texture-mirror base (`genres/_base.json`). Port existing sub-styles from the
current `genres/dub.json` and `genres/dnb.json`; every other genre gets just
`All`.

**Files:**
- Modify (overwrite): `playlist-data/genres.json`
- Modify (overwrite): `playlist-data/genres/dub.json`, `playlist-data/genres/dnb.json`, `playlist-data/genres/beats.json`, `playlist-data/genres/dubstep.json`, `playlist-data/genres/feels.json`, `playlist-data/genres/house.json`, `playlist-data/genres/jungle.json`, `playlist-data/genres/riddim.json`, `playlist-data/genres/ukg.json`, `playlist-data/genres/vibes.json`

- [ ] **Step 1: Overwrite `genres.json` (drop Weapons folder — it has no genre file; keep 10 genre folders + add All at top)**

Replace the entire contents of `playlist-data/genres.json`:

```json
{
  "data": [
    {
      "parent": "Genres",
      "mainConditions": [],
      "negativeConditions": ["Archive"],
      "playlists": [
        { "name": "Dub", "operator": 1, "playlistType": "folder", "link": "genres/dub.json" },
        { "name": "DnB", "operator": 1, "playlistType": "folder", "link": "genres/dnb.json" },
        { "name": "UKG", "operator": 1, "playlistType": "folder", "link": "genres/ukg.json" },
        { "name": "House", "operator": 1, "playlistType": "folder", "link": "genres/house.json" },
        { "name": "Jungle", "operator": 1, "playlistType": "folder", "link": "genres/jungle.json" },
        { "name": "Riddim", "operator": 1, "playlistType": "folder", "link": "genres/riddim.json" },
        { "name": "Dubstep", "operator": 1, "playlistType": "folder", "link": "genres/dubstep.json" },
        { "name": "Beats", "operator": 1, "playlistType": "folder", "link": "genres/beats.json" },
        { "name": "Feels", "operator": 1, "playlistType": "folder", "link": "genres/feels.json" },
        { "name": "Vibes", "operator": 1, "playlistType": "folder", "link": "genres/vibes.json" }
      ]
    }
  ]
}
```

- [ ] **Step 2: Overwrite `genres/dub.json` (has sub-styles) — `All` + ported sub-styles, no base**

Replace the entire contents of `playlist-data/genres/dub.json`:

```json
{
  "data": [
    {
      "parent": "Dub",
      "mainConditions": ["Dub"],
      "negativeConditions": ["Archive"],
      "playlists": [
        { "name": "All", "operator": 1, "contains": [] },
        { "name": "Dub Doubles", "operator": 1, "contains": ["Dub Doubles"] },
        { "name": "Dub Wobblers", "operator": 1, "contains": ["Dub Wobblers"] },
        { "name": "Dub Sound System", "operator": 1, "contains": ["Dub Sound System"] },
        { "name": "Dub Slimzee", "operator": 1, "contains": ["Dub Slimzee"] },
        { "name": "Dub Trippy/Interesting", "operator": 1, "contains": ["Dub Trippy/Interesting"] },
        { "name": "Dub Reggae", "operator": 1, "contains": ["Dub Reggae"] }
      ]
    }
  ]
}
```

- [ ] **Step 3: Overwrite `genres/dnb.json` — inspect the old file, port its sub-style tags the same way**

First read the current sub-styles (they inform the port):
```bash
cat playlist-data/genres/dnb.json
```
Then replace the entire contents of `playlist-data/genres/dnb.json` with `All` + each `contains` sub-style found (drop the `"base"` field). Template:

```json
{
  "data": [
    {
      "parent": "DnB",
      "mainConditions": ["DnB"],
      "negativeConditions": ["Archive"],
      "playlists": [
        { "name": "All", "operator": 1, "contains": [] }
      ]
    }
  ]
}
```
Add one `{ "name": "<sub>", "operator": 1, "contains": ["<sub>"] }` entry for every sub-style playlist present in the old `dnb.json` (e.g. `DnB Rollers`, `DnB Jump Up`, `DnB Liquid`, `DnB Deep Vibes`, `DnB Dancefloor` if present).

- [ ] **Step 4: Overwrite the remaining 8 genre files with an `All`-only body**

Run this exact script (writes `All`-only bodies for genres with no ported sub-styles):

```bash
source venv/bin/activate && python -c "
import json
from pathlib import Path
base = Path('playlist-data/genres')
# (file stem, parent, tag) — genres with no sub-styles get just All
plain = [
    ('beats', 'Beats', 'Beats'),
    ('dubstep', 'Dubstep', 'Dubstep'),
    ('feels', 'Feels', 'Feels'),
    ('house', 'House', 'House'),
    ('jungle', 'Jungle', 'Jungle'),
    ('riddim', 'Riddim', 'Riddim'),
    ('ukg', 'UKG', 'UKG'),
    ('vibes', 'Vibes', 'Vibes'),
]
for stem, parent, tag in plain:
    body = {'data': [{
        'parent': parent,
        'mainConditions': [tag],
        'negativeConditions': ['Archive'],
        'playlists': [{'name': 'All', 'operator': 1, 'contains': []}],
    }]}
    (base / f'{stem}.json').write_text(json.dumps(body, indent=2) + '\n', encoding='utf-8')
    print('wrote', stem)
"
```

- [ ] **Step 5: Verify the Genres tree resolves with no errors and a sane count**

Run:
```bash
source venv/bin/activate && python -c "
from pathlib import Path
from rekordbox_smart_playlists.audit import resolve_context
r = resolve_context(Path('playlist-data/genres.json'), Path('playlist-data'))
print('leaves:', len(r.leaves), 'errors:', r.errors)
# spot-check accumulation: a Dub sub-style ANDs the Dub tag
dub_doubles = [l for l in r.leaves if l.name == 'Dub Doubles']
print('Dub Doubles conditions:', dub_doubles[0].conditions if dub_doubles else 'MISSING')
"
```
Expected: `errors: []`; `Dub Doubles conditions: frozenset({'Dub', 'Dub Doubles'})`; leaf count in the ~25–35 range (10 `All` + Dub's 6 + DnB's ported subs).

- [ ] **Step 6: Commit**

```bash
git add playlist-data/genres.json playlist-data/genres/
git commit -m "feat(playlists): rebuild global Genres tree with sub-styles only"
```

---

## Task 10: Ordering + legacy cleanup

**Files:**
- Modify (overwrite): `playlist-data/_order.json`
- Delete: `playlist-data/rotation.json`, `playlist-data/helpers/deep.json`, `playlist-data/helpers/groovy.json`, `playlist-data/helpers/heavy.json`, `playlist-data/helpers/organic.json`, `playlist-data/helpers/weird.json`, `playlist-data/helpers/vocal.json`, `playlist-data/helpers/palate_cleanser.json`, `playlist-data/helpers/_base.json`, `playlist-data/templates/show.json`, `playlist-data/genres/_base.json`

- [ ] **Step 1: Overwrite `_order.json` with the new sidebar order**

Replace the entire contents of `playlist-data/_order.json`:

```json
{
  "first": [
    "my-set.json",
    "daytime.json",
    "pool-party.json",
    "morningtime-vibes.json",
    "sunrise.json",
    "chillin.json",
    "nighttime.json",
    "late-night.json",
    "afterparty.json",
    "silent-disco.json",
    "crispy-speakers.json",
    "missy.json",
    "b2b.json"
  ],
  "last": [
    "genres.json",
    "go-through.json"
  ]
}
```

- [ ] **Step 2: Delete the now-unreferenced legacy files**

```bash
git rm playlist-data/rotation.json \
  playlist-data/helpers/deep.json playlist-data/helpers/groovy.json \
  playlist-data/helpers/heavy.json playlist-data/helpers/organic.json \
  playlist-data/helpers/weird.json playlist-data/helpers/vocal.json \
  playlist-data/helpers/palate_cleanser.json playlist-data/helpers/_base.json \
  playlist-data/templates/show.json playlist-data/genres/_base.json
```

- [ ] **Step 3: Verify nothing references the deleted files (no broken links across the whole directory)**

Run:
```bash
source venv/bin/activate && python -m rekordbox_smart_playlists.audit playlist-data
```
Expected: exit code 0, `Uniformity: OK (12 contexts identical)`, and **no** `ERRORS:` section.

Also grep for stale links to be safe:
```bash
grep -rEl "helpers/(deep|groovy|heavy|organic|weird|vocal|palate_cleanser|_base)\.json|genres/_base\.json" playlist-data || echo "no stale references"
```
Expected: `no stale references`.

- [ ] **Step 4: Commit**

```bash
git add playlist-data/_order.json
git commit -m "chore(playlists): update ordering and remove legacy playlist files"
```

---

## Task 11: Full audit + optional live dry-run

**Files:**
- Test: `tests/test_audit.py` (add a data-integrity test over the real `playlist-data/`)

- [ ] **Step 1: Add a failing integration test asserting the real library is clean and uniform**

Append to `tests/test_audit.py`:

```python
import pytest

from rekordbox_smart_playlists.audit import _context_files, _signature, resolve_context


PLAYLIST_DATA = Path(__file__).resolve().parents[1] / "playlist-data"

UNIFORM_CONTEXTS = [
    "daytime", "nighttime", "late-night", "sunrise", "chillin", "afterparty",
    "morningtime-vibes", "pool-party", "crispy-speakers", "missy", "b2b",
    "silent-disco",
]


@pytest.mark.integration
def test_real_library_has_no_broken_links():
    errors = []
    for f in _context_files(PLAYLIST_DATA):
        errors.extend(resolve_context(f, PLAYLIST_DATA).errors)
    assert errors == [], f"resolution errors: {errors}"


@pytest.mark.integration
def test_uniform_contexts_are_identical_and_sized():
    sigs = {}
    for stem in UNIFORM_CONTEXTS:
        res = resolve_context(PLAYLIST_DATA / f"{stem}.json", PLAYLIST_DATA)
        assert len(res.leaves) == 82, f"{stem} has {len(res.leaves)} leaves, expected 82"
        sigs[stem] = _signature(res.leaves)
    assert len(set(sigs.values())) == 1, "uniform contexts are not structurally identical"


@pytest.mark.integration
def test_library_total_is_within_expected_range():
    total = sum(len(resolve_context(f, PLAYLIST_DATA).leaves)
                for f in _context_files(PLAYLIST_DATA))
    # 12*82 + My Set 34 + Genres (~30) + Go Through (3) ≈ 1090
    assert 1050 <= total <= 1150, f"unexpected library total: {total}"
```

- [ ] **Step 2: Run the full test suite**

Run: `source venv/bin/activate && pytest tests/ -v`
Expected: all tests PASS (unit + the 3 integration tests). If `test_library_total_is_within_expected_range` fails, print the actual total with the audit CLI and reconcile against the spec budget before adjusting the bound.

- [ ] **Step 3: Print the final human-readable audit**

Run: `source venv/bin/activate && python -m rekordbox_smart_playlists.audit playlist-data`
Expected: per-file counts, `TOTAL` ≈ 1090, `Uniformity: OK (12 contexts identical)`, no errors.

- [ ] **Step 4: (Optional, requires Rekordbox CLOSED) live dry-run against the DB**

This validates that every referenced My Tag actually exists in the Rekordbox
database (the offline resolver cannot check tag existence).

Run:
```bash
source venv/bin/activate && rekordbox-smart-playlists --dry-run --verbose playlist create --all 2>&1 | tee /tmp/rekordbox-dryrun.log
grep -i "Tag not found" /tmp/rekordbox-dryrun.log || echo "all referenced tags exist"
```
Expected: `all referenced tags exist`. If any `Tag not found` lines appear, either create the My Tag in Rekordbox or fix the tag name in the relevant helper JSON, then re-run.

- [ ] **Step 5: Commit**

```bash
git add tests/test_audit.py
git commit -m "test(audit): assert real library is clean, uniform, and within budget"
```

---

## Self-Review Notes

**Spec coverage check:**
- Situation-first / one-lens-second, RR-safe folders → Tasks 6–7 (context template with folder lenses). ✓
- Context vs Caliber; 12 uniform contexts w/ nested My Set + Rotation → Tasks 5–7. ✓
- Genre & Texture parallel lenses, curated combos → Tasks 2–3. ✓
- Flow lens per context (decision 1) → Task 4 + template. ✓
- Global Genres, sub-styles only (decision 2) → Task 9. ✓
- My Set global special-case → Task 8. ✓
- Budget ~1,090 / uniformity → Tasks 7, 11. ✓
- Ordering + legacy cleanup (open items 3–4) → Task 10. ✓
- Curated combos list (open item 1) → Task 3 (concrete 10-pair list, adjustable). ✓
- Genre sub-style content (open item 2) → Task 9 (Dub + DnB ported, rest `All`). ✓

**Type consistency:** `resolve_context`, `AuditResult(.leaves/.errors)`, `Leaf(path/name/conditions/negatives)`, `_context_files`, `_signature` are defined in Task 1 and used identically in Tasks 2–11. ✓

**No placeholders:** every JSON body and command is complete. The only intentionally
open-ended step is Task 9 Step 3 (porting DnB sub-styles), which is bounded by the
actual contents of the existing `genres/dnb.json` and includes the exact template. ✓

## Notes / Risks

- **Tag existence** is the one thing the offline resolver cannot verify — covered by the optional Task 11 Step 4 dry-run. Referenced tags assume the My Tags already exist in Rekordbox (per spec: this is an organization problem, not a tagging one).
- **`operator` values** are all `1` (ALL/AND); combos rely on AND of two texture tags, matching `_build_smart_list`.
- **`old/` is intentionally left untouched** — `create_playlists_from_directory` globs `*.json` non-recursively, so it is never processed.
- **Applying for real** (dropping `--dry-run`) will prompt per existing folder unless `--overwrite`/strategy flags are used; that is a run-time choice, out of scope for this plan.
