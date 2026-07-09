# Playlist & Tag Glossary

The authoritative "what does each playlist/tag mean and why does it exist" reference.
Structure/counts live in the [architecture spec](superpowers/specs/2026-07-07-playlist-architecture-design.md);
this doc is about **meaning and intent**, so future sessions don't have to re-ask.

**DJ:** Tegan, aka **Dane Dubz**. Plays a genre-diverse bass/underground library across
many settings and hardware types (laptop Rekordbox, CDJ-3000, and notably the **XDJ-RR**,
which has weak live filtering — hence folder-navigable structure). Builds his own sound
systems.

**Legend:** ✅ confirmed with the DJ · ❓ inferred/unknown — **please confirm or correct.**

---

## The two organizing concepts

- **Context** — *fixed for the duration of a gig; you navigate TO it.* Time, venue, format,
  audience. Each context is a top-level folder with the full 82-leaf anatomy.
- **Caliber** — *slides WITHIN a gig; you refine a context WITH it.* A quality tier. Two
  levels, nested inside every context: **My Set** (S-tier) and **The Rotation** (A-tier).

Every leaf playlist is `Context tag AND <lens tag(s)>`, minus anything tagged `Archive`.

---

## Contexts (top-level folders)

| Context | Meaning | Notes |
|---|---|---|
| **Daytime** ✅ | Outdoor festivals, day parties | Mid-energy, day/up cluster with Pool Party |
| **Pool Party** ✅ | Fun, upbeat, crowd-friendly | Day/up cluster |
| **Frankys Beach** ✅ | Like Pool Party but **kid-friendly** | Franky's & Louie's is a beach bar where his wife plays and he sometimes hops in. **Tag has no apostrophe:** `Frankys Beach` |
| **Morningtime Vibes** ✅ | Warm, easy listening, early | Warm/low cluster |
| **Sunrise** ✅ | Morning sets, comedown | Warm/low cluster |
| **Chillin** ✅ | Background music, lounge | Warm/low cluster |
| **Nighttime** ✅ | Club sets, evening | Peak; canonical template context |
| **Late Night** ✅ | Dark rooms, 2am+ | Peak-dark |
| **Frankys After** ✅ | Franky's during the **11pm–1am** slot once the kids are gone | The grown-up version of Frankys Beach. **Tag has no apostrophe:** `Frankys After` |
| **Afterparty** ✅ | Low-key, intimate, late | Where **The Rotation** shines |
| **Ketamine Music** ✅ | Weird, wonky music | Tag is `Ketamine Music` |
| **Silent Disco** ✅ | Headphone sets | A *format*, not a time — selection differs |
| **Crispy Speakers** ✅ | The best tracks for the best speakers | Tracks built to sound huge on a great rig. Dane builds his own systems and enjoys playing nice ones, so these get a dedicated context |
| **Missy** ✅ | Curated pool for B2B sets with his wife, **Missy** | Songs picked for her vibe |
| **B2B** ✅ | General back-to-back / collaborative-set pool | Format context, like Missy but not partner-specific |
| **My Set** (global) ✅ | Situation-independent **S-tier** browse — "the songs that represent me / Dane Dubz" | The best of the best; a showcase context. No caliber nesting (nesting My Set in My Set is redundant) |

### Caliber tiers (nested inside every context)

| Tier | Tag | Meaning |
|---|---|---|
| **My Set** ✅ | `My Set` | S-tier. The absolute best; the tracks that represent Dane Dubz |
| **The Rotation** ✅ | `The Rotation` | A-tier, a notch below My Set. Reliable floor-movers you play out at an afterparty "just messing around" — not all absolute bangers, but guaranteed to move the floor or pique interest. Can overlap with My Set |

---

## Light standalone folders

Niche/themed collections that don't warrant the full 82-leaf anatomy. Each is a **flat
texture-light** folder: `All` + the 7 texture singles (Groovy, Deep, Heavy, Organic, Vocals,
Weird, Palate Cleanser) = 8 playlists, no genre/flow/caliber. Rarely synced. Built from the
shared base `helpers/_texture-singles.json`.

| Folder | Meaning |
|---|---|
| **Party Hits** ✅ | Sing-along songs, but remixes — like Vibes, but **always has vocals** |
| **Trippin** ✅ | "Bicycle Day" type vibe (psychedelic) |
| **LR Friends** ✅ | Songs his **Little Rock** friends will like — usually house/funky |
| **New Years** ✅ | New Year's songs — usually dreamy, feelsy |
| **Halloween** ✅ | Halloween songs |
| **SHADES** ✅ | A particular artist/sound he loves — effectively an **as-yet-undefined genre**; may graduate into the Genre lens later |

---

## Lenses (the sub-folders inside each context)

You browse a context by **one lens at a time** (Situation-first, one-lens-second).

### Flow — set position ✅ (top level only, not inside caliber)
`Openers` → `Beginning` → `Middle` → `End` → `Closers`. Where a track sits in a set's arc.
(Energy is separate — see Ratings below.)

### Texture — how it SOUNDS (genre-blind) ✅ (from README)
The unifying cross-genre lens: every genre can be any texture, and same-texture tracks mix.

| Texture (tag) | Feel |
|---|---|
| **GROOVY (The Pocket)** | Swing, shuffle, broken beats, syncopation |
| **DEEP (The Head)** | Minimal, spacious, dark, hypnotic |
| **HEAVY (The Face)** | Aggressive, distorted, high energy, "bass face" |
| **ORGANIC (The Soul)** | Melodic, warm, emotional, acoustic samples |
| **WEIRD (The Brain)** | Experimental, psychedelic, unexpected |
| **VOCALS** | Lyrical focus, rap, grime, vocal-led |
| **PALATE CLEANSER** | Transitions, palette shifts, breathers |

**Texture Combos** (curated pairs, materialized as folders because the RR can't filter
them live): Groovy+Deep, Groovy+Heavy, Groovy+Organic, Groovy+Vocals, Deep+Organic,
Deep+Heavy, Deep+Weird, Heavy+Weird, Heavy+Vocals, Organic+Vocals. *This is a starting
set — adjust to the combos actually reached for.*

### Genre — what it IS ✅ (texture-blind)
`Beats`, `DnB`, `Dub`, `Dubstep`, `Feels`, `House`, `Jungle`, `Riddim`, `UKG`, `Vibes`, `Weapons`

Meanings:
- **Weapons** ✅ — killers, every time. The best of the best, regardless of genre. It's a
  genre-*lens* filter only (present in every context) but is **excluded from the global
  Genres tree** (it's a caliber-flavored catch-all, not a genre with sub-styles).
- **Feels** ✅ — dreamier, usually melodic songs.
- **Vibes** ✅ — heavier but generally good-vibes tracks you can dance to; often songs you
  know, remixed.
- `Beats`, `DnB`, `Dub`, `Dubstep`, `House`, `Jungle`, `Riddim`, `UKG` — standard genres.

---

## Global Genres tree (situation-independent, sub-styles)

Genre-first browsing with sub-styles. Only Dub and DnB have sub-styles today; the rest
show just `All`. `Weapons` is deliberately omitted (see above).

**Dub sub-styles** ✅:
- `Dub Doubles` — good songs you could double (overlap/mix two copies).
- `Dub Wobblers` — wubbier songs; the stereotypical dub wobble.
- `Dub Sound System` — like Crispy Speakers but dub-focused: songs that slap on a big system.
- `Dub Slimzee` — a particular type of *new* dub; disorienting and crazy.
- `Dub Trippy/Interesting` — usually lower tempo, interesting to listen to, interesting fill
  elements — songs that take you on a journey.
- `Dub Reggae` — the typical "Jamaican Dub" sound; old-school.

**DnB sub-styles** (standard DnB subgenres ✅):
- `DnB Jump Up` · `DnB Rollers` · `DnB Liquid` · `DnB Dancefloor`

---

## Utility

### Go Through — a to-do / QA bucket
| Tag | Meaning |
|---|---|
| **Bad Quality** ✅ | Low audio-quality tracks flagged to review/replace |
| **Bad Grid** ✅ | Tracks with a bad beatgrid that needs fixing |
| **Jayden** ✅ | Cool songs to **show** his nephew Jayden (not yet a DJ) — like Missy, but "show him" rather than "play B2B with." See note below. |

> **Placement note:** `Jayden` currently lives under **Go Through** (the QA/to-do bucket), but
> conceptually it's a *curated audience pool* like Missy — not a QA task. Consider promoting it
> to its own light context (or a "People I build for" grouping alongside Missy) in a future pass.

### Recent Additions ✅ (date-based utility)
"What have I added lately" — smart playlists filtered by `dateCreated`, not tags:
`Last 30 Days`, `Last 60 Days`, plus `… Rotation` variants (same window, also tagged
`The Rotation`). The one place the library uses date filters instead of My Tags.

### `Archive` ✅
A global exclusion tag. Anything tagged `Archive` is filtered OUT of every playlist
(`negativeConditions`). Use it to retire a track without deleting it.

### `Dirty` — explicit-content flag ✅
Marks explicit tracks. Exposed as an **opt-in `Clean/` folder** (NOT a context-wide
exclusion — you can still pull dirty tracks from the normal folders). The Clean folder =
`All` + the 7 texture singles, each also excluding `Dirty`, built from
`helpers/lens-clean.json` (a `_texture-singles` base + a `Dirty` negative).

- **Pool Party** and **Chillin** carry a `Clean/` folder.
- **Jayden** (nephew, in Go Through) is always-clean — a single `doesNotContain: ["Dirty"]`.
- **Franky's Beach** is assumed already-clean, so it has **no** Clean folder or filter.

Structurally, `Clean/` is an **allowed augmentation**: the audit's `AUGMENTABLE_SUBTREES`
excludes it from the uniformity check, so all 15 contexts still share an identical 82-leaf
*core* even though Pool Party/Chillin resolve to 90 leaves.

### Retired tags ✅ (intentionally gone — don't re-add)
- **Breaky** → folded into **UKG**.
- **Earthy** → folded into **ORGANIC (The Soul)**.
- **Transition** → folded into **PALATE CLEANSER**.

### Ratings = Energy ✅ (not quality)
1★ warmup/ambient → 5★ maximum/headliner. Sortable on all hardware, so energy is handled
by rating sort rather than by folders.

---

## Status
All meanings confirmed with the DJ (2026-07-08). No open ❓ items remain. One structural
suggestion is parked: `Jayden` may deserve promotion out of Go Through into a curated-pool
context (see the Go Through placement note).
