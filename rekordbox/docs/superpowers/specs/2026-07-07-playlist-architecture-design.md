# Playlist Architecture Redesign

**Date:** 2026-07-07
**Status:** Approved design — ready for implementation planning
**Author:** Tegan (Dane Dubz) + Claude

## Problem

The current playlist system generates **~4,340 smart playlists** across 14 root
"situations." The explosion came from two mistakes, not from the concept:

1. The full genre list (`_base.json`, 16 entries) was injected at **every** node
   of the hierarchy (situation, texture, and nested texture).
2. `PALATE CLEANSER` was materialized **twice** — once at situation level and
   again inside every texture folder.

The result multiplied three axes (Situation × Texture × Genre) into folders,
producing thousands of mostly-empty leaves — the exact "playlist explosion" the
original design set out to prevent.

There is also conceptual muddle: the 14 "situations" are actually three different
*kinds* of thing wearing the same costume (real time/place contexts, curation
pools, and a quality tier).

## Constraints

- **Hardware portability.** Sets are played on a range of gear. The XDJ-RR (and
  similar) have weak live filtering, so **anything browsed must be a real folder**
  — we cannot rely on live My-Tag filtering the way a CDJ-3000 allows.
- **1000-playlist limit is per-sync, not per-library.** Tracks/playlists are
  synced to USB **per gig**. Before a gig, only the relevant slice is exported.
  So the *library* may exceed 1000; any single *sync* must not. A typical gig
  sync is a few contexts (~150–200 playlists).
- **Ratings = energy**, not quality (1 = warmup … 5 = peak). Sortable on all
  hardware, so energy is handled by rating sort, not by folders.
- Tags and categories already exist in Rekordbox as My Tags. This is an
  **organization** problem, not a tagging problem.

## Core model: facets add, they don't multiply

A DJ navigates **at most two axes at once**, and it is almost always
**Situation first, then one lens** (Genre *or* Texture). The third axis is a
*query*, not a *destination* — handled live (CDJ) or simply not materialized.

Therefore: pick a small set of axes to **materialize as folders** (what you
browse) and leave the rest as **live filters** (what you occasionally query).
Facets that are *added* cost `S + T + G`; facets that are *multiplied* cost
`S × T × G`. The redesign adds where it can and multiplies only where the
2-axis browse pattern demands it.

### The two axes we materialize per context

1. **Genre lens** — the intrinsic "what is it" axis. You know a groovy track is
   *specifically* UKG or House and sometimes want to browse that way.
2. **Texture lens** — the cross-genre "how does it sound" axis. Its whole value
   is that it *ignores* genre: every genre can be GROOVY, and all GROOVY mixes.

These are **parallel lenses**, presented side by side, never crossed into a
single folder (crossing them defeats the purpose of each). The one exception is
**texture pairs** (e.g. GROOVY + DEEP), which the user explicitly wants — treated
as a single "blended" move, materialized as a curated `Combos/` subfolder.

## Two concept types

Everything in the library is one of two things:

| Type | Behavior | Treatment |
|---|---|---|
| **Context** | Fixed for the duration of a gig — you navigate *to* it | Gets a destination tree |
| **Caliber** | Slides *within* a gig — you refine a context *with* it | Nested sub-tree inside each context |

**Caliber** is the one genuinely cross-cutting axis, because it is the only thing
you toggle mid-gig ("we're chillin — but give me my S-tier"). It has two levels:

- **My Set** = S-tier ("the songs that represent me / Dane Dubz")
- **The Rotation** = A-tier (reliable floor-movers, a notch below)

All other former "situations" are Contexts (fixed per gig): time, speakers,
format, audience.

## Context inventory & tiers

**Every context uses the identical full anatomy (76 leaves).** There is no
"light" tier — uniformity means every folder looks the same on every USB
regardless of hardware or gig, so muscle memory always works. Caliber nesting
(My Set / The Rotation) is *most* valuable in the set-*creation* contexts
(Missy, B2B, Silent Disco), so it is included everywhere.

| Context | Tier | Notes |
|---|---|---|
| Daytime | Full | time/place |
| Nighttime | Full | time/place |
| Late Night | Full | time/place |
| Sunrise | Full | time/place |
| Chillin | Full | time/place |
| Afterparty | Full | time/place |
| Morningtime Vibes | Full | time/place |
| Pool Party | Full | time/place |
| Crispy Speakers | Full | big-system tracks (first trim lever: drop caliber) |
| Missy | Full | curated B2B pool for wife |
| B2B | Full | general B2B pool |
| Silent Disco | Full | headphone format |
| My Set (global) | Special | situation-independent S-tier browse; full lens, **no** self-caliber nesting |
| Genres (global) | Special | situation-independent genre tree **with sub-styles** (Dub Doubles, DnB Rollers…) |
| Go Through | Utility | QA bucket (Bad Quality / Bad Grid / Jayden), unchanged |

The only non-uniform nodes are the genuinely special ones: **My Set (global)**
(nesting My Set inside My Set is redundant), the **Genres** tree, and the
**Go Through** utility.

Near-identical time-situations (Sunrise/Morningtime/Chillin/Afterparty) are all
kept because per-gig sync means their overlap costs nothing at play time, and
they are narratively distinct to the user.

## Structure: anatomy of a full context

Every leaf is `<Context tag> AND <lens tag(s)>`, with a global
`negativeConditions: ["Archive"]`.

```
Nighttime/
├── All                                    [Nighttime]
├── Flow/                                   ← set-position lens (top level only)
│    └── Openers · Beginning · Middle · End · Closers      (5)
├── Genre/                                  ← all-caliber genre lens
│    └── House · Dub · DnB · UKG · Jungle · Riddim ·
│        Dubstep · Beats · Feels · Vibes · Weapons        (11)
├── Texture/                                ← all-caliber texture lens
│    ├── Groovy · Deep · Heavy · Organic · Vocals · Weird (6 singles)
│    ├── Palate Cleanser
│    └── Combos/  Groovy+Deep · Deep+Organic · …          (~10 curated)
├── My Set/                                 ← S-tier caliber sub-tree (FULL)
│    ├── All
│    ├── Genre/    (11)
│    └── Texture/  (6 + Palate + Combos ~10)
└── The Rotation/                           ← A-tier caliber sub-tree (LIGHT)
     ├── All
     ├── Genre/    (11)
     └── Texture/  (6 singles)
```

Three parallel caliber views (own pool / S-tier / A-tier), each branchable by
genre or texture, so Dubstep and House never mix within any of them.

All 12 contexts (time-situations, Crispy Speakers, Missy, B2B, Silent Disco)
use this identical anatomy.

### Special: My Set (global), full lens, no self-caliber

```
My Set/                                     ← global S-tier browse
├── All
├── Genre/    (11)
└── Texture/  (6 + Palate + Combos ~10)
```

## Reusable blocks

| Block | Contents | Leaves |
|---|---|---|
| **F** — Flow lens | Openers · Beginning · Middle · End · Closers | 5 |
| **G** — Genre lens | 11 genres | 11 |
| **TF** — Texture full | 6 singles + Palate Cleanser + ~10 combos | 17 |
| **TL** — Texture light | 6 singles + Palate Cleanser | 7 |

- **Full context** = `All(1) + F(5) + G(11) + TF(17) + MySet[1+G+TF=29] + Rotation[1+G+TL=19]` = **82**
- **My Set (global)** = `All(1) + F(5) + G(11) + TF(17)` = **34**

Flow is a top-level lens only — it is *not* nested inside the caliber sub-trees.

## Budget

| Piece | Each | Count | Leaves |
|---|---|---|---|
| Uniform contexts (82 leaves each) | 82 | 15 | 1,230 |
| My Set (global base) | 34 | 1 | 34 |
| Global Genres (sub-styles only) | 20 | 1 | 20 |
| Light standalone folders (texture-light, 8 each) | 8 | 6 | 48 |
| Recent Additions (date-based utility) | 4 | 1 | 4 |
| Go Through | 3 | 1 | 3 |
| `Clean/` augmentation (Pool Party, Chillin) | 8 | 2 | 16 |
| **Library total** | | | **1,355 (as built)** |

> **`Clean/` augmentation:** Pool Party and Chillin carry an opt-in `Clean/` folder
> (All + texture singles, excluding the `Dirty` tag) so they resolve to 90 leaves,
> not 82. This is an *allowed augmentation* — `audit.py`'s `AUGMENTABLE_SUBTREES`
> excludes `Clean/` from the uniformity check, so all 15 contexts still share an
> identical 82-leaf core. See the glossary's `Dirty` entry.

> **As-built note (updated 2026-07-08):** the implementation lands at **1,335
> leaves**, verified by `python -m rekordbox_smart_playlists.audit playlist-data`.
> - **15 uniform contexts** (the original 12 + `Franky's Beach`, `Ketamine Music`,
>   `Franky's After`), each 82 leaves and structurally identical.
> - **6 light standalone folders** (`Party Hits`, `Trippin`, `LR Friends`,
>   `New Years`, `Halloween`, `SHADES`) — a *texture-light* tier (`All` + 7 texture
>   singles = 8 each), built from `helpers/_texture-singles.json`. The "light" tier
>   was reintroduced deliberately for niche/themed collections that don't warrant
>   the full anatomy and are rarely synced.
> - The Genres tree came in at 20 (not the ~66 estimate) because only Dub (6) and
>   DnB (4) have sub-styles defined; every other genre has just `All`.
> - `Weapons` is intentionally a genre-*lens* filter only, excluded from the
>   sub-style Genres tree, so that tree has 10 genres vs. the lens's 11.
>
> See `docs/playlist-glossary.md` for the meaning of every context/tag.

Folder nodes push the raw total slightly higher, so the full library sits just
over the 1000 mark — acceptable because the 1000 limit is **per-sync, not
per-library**. A representative gig sync (e.g. Late Night + Crispy Speakers +
My Set global) is ~200 playlists.

### Trim levers (not needed now)

- **Rotation = one lens** (genre *or* texture): full context 76 → ~70.
- **Drop caliber nesting from Crispy Speakers**: saves ~47.
- **Merge the warm/low time cluster** (Sunrise/Morningtime/Chillin/Afterparty).

## Mapping to the existing JSON tooling

The current generator already supports the primitives we need — `mainConditions`
(ANDed tags), `contains`, `negativeConditions`, `base` injection, folder `link`s,
and operators. The redesign is mostly a **data restructure**, not a code rewrite:

- **Stop** injecting the full mixed `_base.json` (genres + flow + weapons) at
  every node. Split it into a **genre-only base** (the 11 genres = block **G**)
  reused wherever a Genre lens appears.
- **Texture** becomes its own reusable definition producing block **TF/TL**
  (singles + curated `Combos/`), materialized once and linked, not re-expanded
  per genre.
- **Caliber** (My Set / The Rotation) is expressed by adding the caliber tag to
  `mainConditions` of a nested sub-tree that itself reuses **G** and **TF/TL**.
- **PALATE CLEANSER** appears once inside the texture block, never doubled.

## Resolved decisions (during planning, 2026-07-08)

1. **Flow-position tags** → **Flow lens per context**, top level only (parallel
   to Genre/Texture), *not* nested in caliber sub-trees. Block **F** (5 leaves).
2. **Global Genres depth** → **sub-styles only** (genre → its sub-styles; genres
   with none get just `All`). No texture drill-down in the Genres tree.

## Open details still to resolve during implementation

1. **Exact curated `Combos/` list** — which texture pairs are worth materializing
   (not all 15). Start from the pairs actually reached for.
2. **Genre sub-style content** — port from existing `genres/*.json`
   (e.g. Dub Doubles/Wobblers/Sound System/Slimzee/Reggae). Genres with no
   defined sub-styles get just `All`.
3. **`_order.json` / ordering** — top-level context ordering for the Rekordbox
   sidebar (My Set first, time-situations by arc, then Crispy/Missy/B2B/Silent
   Disco, then Genres, then Go Through).
4. **Cleanup** — delete now-unreferenced legacy files: old texture helpers
   (`helpers/deep.json` etc.), old mixed `helpers/_base.json`, top-level
   `rotation.json` (Rotation is now nested caliber), `templates/show.json`
   (dead), and the texture-mirror `genres/_base.json`. `old/` is left as-is
   (not processed — directory glob is non-recursive).

## Non-goals

- No changes to tagging workflow or My Tag definitions (tags already exist).
- No metadata/sync tooling changes.
- No attempt to materialize the full 3-axis cross-product as folders — the third
  axis stays a live query.
