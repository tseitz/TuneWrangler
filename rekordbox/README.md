# Rekordbox Smart Playlist Tools

A collection of Python tools for managing Rekordbox 6 databases, smart playlists, and metadata synchronization. Built for DJs who want to organize large, genre-diverse libraries and generate smart playlists from simple JSON configurations.

## What This Project Does

- **Create Smart Playlists**: Generate complex Rekordbox smart playlists from JSON configuration files
- **Fix Metadata Issues**: Synchronize metadata between your Rekordbox database and filename formats
- **Backup & Restore**: Safely backup and restore your Rekordbox database
- **Manage Playlists**: Copy, modify, and organize your Rekordbox playlists programmatically

## Playlist Organization Methodology

This project implements a **Situation-first, Texture-second** playlist architecture designed for DJs who play across multiple genres and need to find the right track quickly -- whether on a laptop with full Rekordbox filtering or on a CDJ/XDJ with only folder navigation.

### The Problem

Organizing a diverse library by genre first (Dub, DnB, House, etc.) leads to an explosion of playlists. If you have 10 genres and 15 attributes (energy levels, openers, closers, styles), you end up with 150+ playlists. Scrolling through deep folder trees on a CDJ mid-set is slow and stressful.

### The Solution: Three-Layer Hierarchy

```
Situation  ->  Sonic Texture  ->  Genre / Cross-Texture
```

#### Layer 1: Situation (When are you playing?)

The top-level folders answer "what kind of set is this?" Each situation is a Rekordbox tag that you apply to tracks. Every track can belong to multiple situations.

| Situation | Description |
|---|---|
| Daytime | Outdoor festivals, day parties |
| Nighttime | Club sets, evening events |
| Late Night | Dark rooms, 2am+ |
| Sunrise | Morning sets, comedown |
| Afterparty | Low-key, intimate |
| Chillin | Background music, lounge |
| Silent Disco | Headphone sets |
| Morningtime Vibes | Warm, easy listening |
| Pool Party | Fun, upbeat, crowd-friendly |

Additional root playlists like **My Set**, **The Rotation**, **Missy**, and **B2B** follow the same pattern for gig-specific or collaborative prep.

#### Layer 2: Sonic Texture (What does it sound like?)

Inside each situation, tracks are organized by *how they sound*, not what genre they are. This creates a consistent mental model across all situations -- "Playlist 2 is always for heads-down hypnotic music" regardless of whether you're playing Dub or DnB.

| Texture | Tag | Description |
|---|---|---|
| GROOVY (The Pocket) | Swing, shuffle, broken beats, syncopation |
| DEEP (The Head) | Minimal, spacious, dark, hypnotic |
| HEAVY (The Face) | Aggressive, distorted, high energy, "bass face" |
| ORGANIC (The Soul) | Melodic, warm, emotional, acoustic samples |
| WEIRD (The Brain) | Experimental, psychedelic, unexpected |
| VOCALS | Lyrical focus, rap, grime, vocal-led |
| PALATE CLEANSER | Transitions, palette shifts, breathers |

#### Layer 3: Genre & Cross-Texture (Drill down)

Inside each texture, you get two types of sub-playlists:

1. **Genre playlists** (inherited from `_base.json`): All, Beats, DnB, Dub, Feels, House, Jungle, Riddim, UKG, Vibes, etc.
2. **Cross-texture playlists** (flat, single tag): DEEP, GROOVY, HEAVY, etc. -- for finding tracks that live at the intersection of two textures.

### Navigation Example

```
Daytime
  -> DEEP (The Head)                    [Daytime + DEEP]
       -> All                           [Daytime + DEEP -- all genres]
       -> Dub                           [Daytime + DEEP + Dub]
       -> DnB                           [Daytime + DEEP + DnB]
       -> House                         [Daytime + DEEP + House]
       -> ...
       -> GROOVY                        [Daytime + DEEP + GROOVY]
       -> HEAVY                         [Daytime + DEEP + HEAVY]
       -> ...
       -> PALATE CLEANSER               [Daytime + DEEP + PALATE CLEANSER]
            -> All                      [Daytime + DEEP + PALATE CLEANSER]
            -> Dub                      [Daytime + DEEP + PALATE CLEANSER + Dub]
            -> ...
```

### How Conditions Stack

Every playlist's filter is the **AND** of all tags from every level of the hierarchy:

- **Situation** tag (e.g., `Daytime`) -- from the root JSON's `mainConditions`
- **Texture** tag (e.g., `DEEP (The Head)`) -- from the helper JSON's `mainConditions`
- **Genre/Cross-texture** tag (e.g., `Dub`) -- from the individual playlist's `contains`

This means a track must be tagged with **all three** to appear in `Daytime -> DEEP -> Dub`.

### Hardware Considerations

This structure is optimized for both laptop and standalone hardware:

- **Laptop (Rekordbox)**: Use the Track Filter panel and My Tag combinations for ad-hoc filtering beyond the playlist structure.
- **CDJ-3000**: Use the Track Filter to combine ratings and sorting within any playlist.
- **XDJ-RR / CDJ-2000NXS2**: Rely on the folder structure for navigation. Sort by Rating (energy) or Date Added within any playlist. The structure is kept shallow (3 levels max) to minimize scrolling.

### Ratings as Energy

Across all playlists, the 1-5 star rating represents **energy level**, not quality:

- 1 star: Low energy, warmup, ambient
- 2 stars: Building, chill but moving
- 3 stars: Cruising, mid-energy
- 4 stars: Peak time, driving
- 5 stars: Maximum energy, headliner moment

On any CDJ, you can sort a playlist by Rating to instantly separate warmup tracks from peak-time bangers.

## Quick Start

### Prerequisites

1. **Python 3.8+** installed
2. **Rekordbox 6** installed and configured
3. **macOS** (scripts are designed for macOS file paths)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/rekordbox-smart-playlist.git
   cd rekordbox-smart-playlist
   ```

2. **Install dependencies:**
   ```bash
   pip install pyrekordbox
   ```

3. **Verify your Rekordbox database location:**
   ```bash
   # Default location:
   # ~/Library/Pioneer/rekordbox6/master.db
   ```

## Usage

### CLI Commands

**Create all playlists (dry run first):**
```bash
rekordbox-smart-playlists --dry-run --verbose playlist create --all
```

**Create playlists from a specific file:**
```bash
rekordbox-smart-playlists --dry-run playlist create --file daytime.json
```

**Create playlists for real (commits to database):**
```bash
rekordbox-smart-playlists playlist create --all
```

**Validate configuration files:**
```bash
rekordbox-smart-playlists playlist validate --all
```

**List existing playlists:**
```bash
rekordbox-smart-playlists playlist list
```

## JSON Configuration Format

### Project Structure

```
playlist-data/
  helpers/
    _base.json             # Shared genre playlists (inherited by all textures)
    groovy.json            # GROOVY texture definition
    deep.json              # DEEP texture definition
    heavy.json             # HEAVY texture definition
    organic.json           # ORGANIC texture definition
    weird.json             # WEIRD texture definition
    vocal.json             # VOCALS texture definition
    palate_cleanser.json   # PALATE CLEANSER texture definition
  daytime.json             # Situation: Daytime
  nighttime.json           # Situation: Nighttime
  late-night.json          # Situation: Late Night
  sunrise.json             # Situation: Sunrise
  afterparty.json          # Situation: Afterparty
  chillin.json             # Situation: Chillin
  silent-disco.json        # Situation: Silent Disco
  morningtime-vibes.json   # Situation: Morningtime Vibes
  pool-party.json          # Situation: Pool Party
  my-set.json              # Root: My Set
  rotation.json            # Root: The Rotation
  missy.json               # Root: Missy
  b2b.json                 # Root: B2B
  old/                     # Archived previous playlist definitions
```

### Situation File (Root Level)

Each situation file defines a top-level folder that links to the shared texture helpers. The `mainConditions` tag filters everything below it.

```json
{
  "data": [
    {
      "parent": "Daytime",
      "mainConditions": ["Daytime"],
      "negativeConditions": ["Archive"],
      "playlists": [
        { "name": "GROOVY (The Pocket)", "operator": 1, "playlistType": "folder", "link": "helpers/groovy.json" },
        { "name": "DEEP (The Head)", "operator": 1, "playlistType": "folder", "link": "helpers/deep.json" },
        { "name": "HEAVY (The Face)", "operator": 1, "playlistType": "folder", "link": "helpers/heavy.json" },
        { "name": "ORGANIC (The Soul)", "operator": 1, "playlistType": "folder", "link": "helpers/organic.json" },
        { "name": "WEIRD (The Brain)", "operator": 1, "playlistType": "folder", "link": "helpers/weird.json" },
        { "name": "VOCALS", "operator": 1, "playlistType": "folder", "link": "helpers/vocal.json" },
        { "name": "PALATE CLEANSER", "operator": 1, "playlistType": "folder", "link": "helpers/palate_cleanser.json" }
      ]
    }
  ]
}
```

### Texture File (Helper)

Each texture file uses the `base` field to inherit shared genre playlists from `_base.json`, then adds cross-texture flat playlists. This keeps the JSON DRY -- genres are defined once.

```json
{
  "data": [
    {
      "parent": "GROOVY (The Pocket)",
      "mainConditions": ["GROOVY (The Pocket)"],
      "negativeConditions": ["Archive"],
      "base": "helpers/_base.json",
      "playlists": [
        { "name": "DEEP", "operator": 1, "contains": ["DEEP (The Head)"] },
        { "name": "HEAVY", "operator": 1, "contains": ["HEAVY (The Face)"] },
        { "name": "ORGANIC", "operator": 1, "contains": ["ORGANIC (The Soul)"] },
        { "name": "VOCALS", "operator": 1, "contains": ["VOCALS"] },
        { "name": "WEIRD", "operator": 1, "contains": ["WEIRD (The Brain)"] },
        { "name": "PALATE CLEANSER", "operator": 1, "playlistType": "folder", "link": "helpers/palate_cleanser.json" }
      ]
    }
  ]
}
```

### Base File

The base file defines playlists that are shared across all textures. It uses a dict-style `data` field (not an array) since it's only used for inheritance.

```json
{
  "data": {
    "playlists": [
      { "name": "All", "operator": 1, "contains": [] },
      { "name": "Beats", "operator": 1, "contains": ["Beats"] },
      { "name": "DnB", "operator": 1, "contains": ["DnB"] },
      { "name": "Dub", "operator": 1, "contains": ["Dub"] }
    ]
  }
}
```

### JSON Field Reference

| Field | Type | Description |
|---|---|---|
| `parent` | string | Folder name in Rekordbox |
| `mainConditions` | string[] | Tags ANDed into every playlist in this category |
| `negativeConditions` | string[] | Tags excluded (NOT CONTAINS) from every playlist |
| `base` | string | Path to a base JSON file whose playlists are prepended (relative to `playlist-data/`) |
| `playlists` | object[] | Array of playlist definitions |
| `playlists[].name` | string | Playlist name in Rekordbox |
| `playlists[].operator` | int | `1` = ALL (AND), `2` = ANY (OR), `5` = Rating range |
| `playlists[].contains` | string[] | Tags to require (ANDed with mainConditions) |
| `playlists[].doesNotContain` | string[] | Tags to exclude |
| `playlists[].rating` | string[] | Rating range `["min", "max"]` (e.g., `["4", "5"]`) |
| `playlists[].playlistType` | string | Set to `"folder"` to create a folder linking to another JSON |
| `playlists[].link` | string | Path to linked JSON file (relative to `playlist-data/`) |
| `playlists[].dateCreated` | object | Date filter with `time_period`, `time_unit`, `operator` |

## Metadata Commands

The metadata commands synchronize artist/title/album between the Rekordbox database and filenames. Files are expected to follow the `Artist - Title.ext` or `Artist - Album - Title.ext` naming convention.

### Preview discrepancies (no changes)

```bash
rekordbox-smart-playlists metadata preview
rekordbox-smart-playlists metadata preview --max-files 50
```

### Fix modes

There are four modes for resolving mismatches:

**Interactive** — prompts you for each discrepancy:
```bash
rekordbox-smart-playlists metadata fix --interactive
```

**Batch: database is authority** — renames files to match Rekordbox metadata:
```bash
rekordbox-smart-playlists --dry-run metadata fix --batch-database
rekordbox-smart-playlists metadata fix --batch-database
```

**Batch: filename is authority** — updates the Rekordbox database to match filenames:
```bash
rekordbox-smart-playlists --dry-run metadata fix --batch-filename
rekordbox-smart-playlists metadata fix --batch-filename
```

**Batch by age** — uses file age to choose the authority automatically:
- Files **newer** than the cutoff → filename is authority (database gets updated)
- Files **older** than the cutoff → database is authority (file gets renamed)

```bash
rekordbox-smart-playlists --dry-run metadata fix --batch-by-age --newer-than-days 30
rekordbox-smart-playlists metadata fix --batch-by-age --newer-than-days 30
```

The cutoff is `now - newer_than_days`. For example, `--newer-than-days 1` treats anything imported today as new (filename wins) and everything before today as established (rekordbox wins). `--newer-than-days 0` is purely database authority.

Age is determined from the Rekordbox `DateAdded` field first, falling back to the file's creation time on disk.

### Validate filename formats

Checks that filenames in your collection follow the expected `Artist - Title` pattern:

```bash
rekordbox-smart-playlists metadata validate
rekordbox-smart-playlists metadata validate --max-files 100
```

### Typical workflow for new downloads

```bash
# 1. Preview what would change
rekordbox-smart-playlists --dry-run metadata fix --batch-by-age --newer-than-days 1

# 2. Apply the changes
rekordbox-smart-playlists metadata fix --batch-by-age --newer-than-days 1
```

## Configuration

### Environment Variables

```bash
export REKORDBOX_COLLECTION_PATH="/path/to/your/music"
export REKORDBOX_BACKUP_PATH="/path/to/backups"
export REKORDBOX_DRY_RUN="true"
```

### Configuration File

Create a `config.json` or `config.toml`:

```json
{
  "collection_path": "/path/to/your/music/collection",
  "playlist_data_path": "playlist-data",
  "dry_run": true,
  "backup_before_changes": true
}
```

## Safety Features

- **Automatic Backups**: Creates backups before making changes
- **Dry Run Mode**: Preview all changes with `--dry-run` before committing
- **Transaction Support**: Database operations are wrapped in transactions -- nothing is committed until all playlists are created successfully
- **Validation**: Run `playlist validate --all` to check your JSON files for errors before creating playlists

## Important Notes

1. **Always close Rekordbox** before running any scripts
2. **Start with `--dry-run`** to preview changes
3. **Backups are automatically created** before making changes
4. **Test with a single file** (`--file daytime.json`) before running `--all`

## Troubleshooting

### pyrekordbox Installation Issues

```bash
# 1. Install the sqlcipher C library (macOS with Homebrew)
brew install sqlcipher

# 2. Install the Python bindings -- pip should find the Homebrew sqlcipher automatically
SQLCIPHER_PATH=$(brew --prefix sqlcipher)
C_INCLUDE_PATH="$SQLCIPHER_PATH/include" LIBRARY_PATH="$SQLCIPHER_PATH/lib" pip install sqlcipher3

# 3. Install pyrekordbox
pip install pyrekordbox
```

If `pip install sqlcipher3` fails, you can fall back to building from source:

```bash
git clone https://github.com/coleifer/sqlcipher3
cd sqlcipher3
SQLCIPHER_PATH=$(brew --prefix sqlcipher)
C_INCLUDE_PATH="$SQLCIPHER_PATH/include" LIBRARY_PATH="$SQLCIPHER_PATH/lib" python setup.py build
C_INCLUDE_PATH="$SQLCIPHER_PATH/include" LIBRARY_PATH="$SQLCIPHER_PATH/lib" python setup.py install
cd ..
```

### Database Connection Errors

- Ensure Rekordbox is **closed** before running any commands
- Check database location: `~/Library/Pioneer/rekordbox6/master.db`
- Verify read/write permissions to the database file

### Debugging

```bash
# Verbose dry run of a single file
rekordbox-smart-playlists --dry-run --verbose playlist create --file daytime.json

# Validate all configs
rekordbox-smart-playlists playlist validate --all
```

## Acknowledgments

- [pyrekordbox](https://github.com/dylanljones/pyrekordbox) for Rekordbox database access
- Pioneer DJ for creating Rekordbox
