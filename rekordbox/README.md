# Rekordbox Smart Playlists

Python tools, part of TuneWrangler, that generate Rekordbox smart playlists from JSON configurations and back up the Rekordbox database. Commands run from the TuneWrangler repo root via `deno task rb`.

## What This Project Does

- **Create Smart Playlists**: Generate complex Rekordbox smart playlists from JSON configuration files
- **Backup & Restore**: Safely backup and restore your Rekordbox database

## Playlist Organization Methodology

The tree is **Root -> Lane**, built to find a track fast on a laptop or on an XDJ/CDJ with only
folder navigation. Playlists are disposable output; the My Tags on tracks are the source of truth.
No tag is ever written, renamed or deleted by this tool.

```text
Daytime
  All              [Daytime]
  House            [Daytime + House]
  Dub Groovy       [Daytime + Dub + GROOVY]
  Weapons          [Daytime + Weapons]
  ...
```

### Roots

A root is one JSON file and one folder. Its tag (`mainConditions`) is ANDed into every playlist
under it, and `Archive` is always excluded. `_order.json` sets the folder order.

- **Situations**: Daytime, Pool Party, Morningtime Vibes, Sunrise, Chillin, Nighttime, Late Night,
  Ketamine Music, Silent Disco, Crispy Speakers, Missy.
- **Tiers**: My Set and The Rotation. These are roots, not nested inside situations.
- **Lanes**: a root with no tag, so its lanes span the whole library.
- **Weapons and Party Hits** are a lane in every root *and* a root of their own. The root form
  gives `Weapons -> Dub Groovy`, for pulling weapons inside a lane on an XDJ-RR. Their roots set
  `minTracks: 1`, since a couple of songs is fine there.
- **Gigs**: one flat folder with a smart playlist per gig tag (tag, not Archive), no lanes.
- **Recent Additions** and **Go Through** are organization utilities, kept as they are.

### Lanes

Every lane root is `All` plus the same lane list, defined once in `helpers/_lanes.json`. A lane
is a smart playlist over existing tags (CONTAINS, plus NOT CONTAINS for a few). Order follows
tempo, with the mixed-tempo catch-alls last. Tempo itself is not encoded: sort by BPM on the deck.

- Genre lanes: House, UKG, Riddim, Halftime, Jungle, DnB, Feels, Beats, Vibes.
- Sub-genre lanes: Dub Deep, Dub Groovy, Dub Vocals, Dub Weird, Dub Trippy, Dub Organic, Dub
  Heavy, Dub Wobblers, Dub Sound System, Dub Reggae, Dubstep Heavy, Dubstep Weird, DnB Rollers,
  DnB Liquid, DnB Jump Up, DnB Dancefloor.
- Weird (the WEIRD texture outside every named genre), Weapons, Party Hits.

Textures (GROOVY, DEEP, HEAVY, ORGANIC, WEIRD, VOCALS, PALATE CLEANSER) are tags that combine
with a genre inside a lane name, for example Dub + GROOVY. Dub Deep is Dub without GROOVY or HEAVY.
Dub Trippy is separate from Dub Weird because a smart list cannot express Dub AND (WEIRD OR
Trippy).

### Skipped lanes (`minTracks`)

A lane is only created when it has at least `minTracks` matching tracks (Archive excluded) in
that root; the lanes in `_lanes.json` use 10. `All` is always created. A root-level `minTracks`
overrides the lane's. A lane whose tag is the root's own tag (Weapons inside Weapons) is skipped
as a duplicate of `All`. Small roots come out nearly flat and grow lanes as tracks get tagged.

The skip matters because the tree is capped by what an XDJ-RR export can hold. The audit counts
the upper bound; the real total depends on the library.

### Hardware

- **Laptop**: use the Track Filter and My Tag combinations for anything beyond the tree.
- **CDJ-3000**: use the Track Filter to combine ratings and sorting within a playlist.
- **XDJ-RR / CDJ-2000NXS2**: rely on the folders. Sort by Rating (energy) or Date Added.

### Ratings as Energy

The 1-5 star rating is **energy**, not quality: 1 warmup or ambient, 2 building, 3 cruising,
4 peak time, 5 maximum energy. Sort a playlist by Rating to separate warmup from peak.

## Usage

Requires macOS, Rekordbox installed, and `uv`. The database is
`~/Library/Pioneer/rekordbox/master.db`. Close Rekordbox before any command that writes. Pass
arguments right after the task name, with no `--`.

```bash
deno task rb --dry-run -v playlist create --all   # preview, no writes
deno task rb --dry-run playlist create --file daytime.json
deno task rb playlist create --all                # backs up master.db, then writes
deno task rb playlist validate --all
deno task rb playlist list
deno task rb backup create                        # also: list, restore, validate, delete, cleanup
deno task rb:audit                                # offline structure check, no database
```

Global flags (`--dry-run`, `-v`, `-q`, `--log-file`) go before the subcommand.

## JSON Configuration Format

### Root File

One file per root in `playlist-data/`. `All` and the lanes come from the shared base, so
`playlists` stays empty (it is still required). `helpers/_lanes.json` uses the dict-style `data`
(not an array) because it is only inherited.

```json
{
  "data": [
    {
      "parent": "Daytime",
      "mainConditions": ["Daytime"],
      "negativeConditions": ["Archive"],
      "base": "helpers/_lanes.json",
      "playlists": []
    }
  ]
}
```

A lane in the base:

```json
{ "name": "Dub Deep", "operator": 1, "contains": ["Dub"], "doesNotContain": ["GROOVY", "HEAVY"],
  "minTracks": 10 }
```

`operator` must be the integer `1`. Anything else makes the list ANY and drops every exclusion.
Files starting with `_` are inheritance bases, not playlists.

### JSON Field Reference

| Field | Type | Description |
|---|---|---|
| `parent` | string | Folder name in Rekordbox |
| `mainConditions` | string[] | Tags ANDed into every playlist in this category |
| `negativeConditions` | string[] | Tags excluded (NOT CONTAINS) from every playlist |
| `base` | string | Path to a base JSON file whose playlists are prepended (relative to `playlist-data/`) |
| `minTracks` | int | Replaces `minTracks` on lanes that set one; others never skip |
| `playlists` | object[] | Array of playlist definitions |
| `playlists[].name` | string | Playlist name in Rekordbox |
| `playlists[].operator` | int | `1` = ALL (AND), `2` = ANY (OR), `5` = Rating range |
| `playlists[].contains` | string[] | Tags to require (ANDed with mainConditions) |
| `playlists[].doesNotContain` | string[] | Tags to exclude |
| `playlists[].rating` | string[] | Rating range `["min", "max"]` (e.g., `["4", "5"]`) |
| `playlists[].playlistType` | string | Set to `"folder"` to create a folder linking to another JSON |
| `playlists[].link` | string | Path to linked JSON file (relative to `playlist-data/`) |
| `playlists[].minTracks` | int | Skip this playlist when fewer tracks match |
| `playlists[].dateCreated` | object | Date filter with `time_period`, `time_unit`, `operator` |

## Configuration

Environment variables only, loaded from the repo-root `.env` (see `.env.example`). There is no
config file.

| Variable | Meaning |
|---|---|
| `TUNEWRANGLER_RB_BACKUP_PATH` | Required for any backup. Must be an existing absolute folder. Only the newest 10 backups this tool wrote are kept; other files are left alone. |
| `TUNEWRANGLER_RB_PLAYLIST_DATA_PATH` | Playlist JSON folder. Default `rekordbox/playlist-data`. |
| `TUNEWRANGLER_RB_PARENT_PLAYLIST` | Folder generated playlists go under. Default `DaneDubz`. |
| `TUNEWRANGLER_RB_DRY_RUN`, `_VERBOSE`, `_LOG_LEVEL`, `_LOG_FILE` | Defaults for the matching CLI flags. |

## Safety Features

- **Backup first**: `playlist create` backs up the Rekordbox library before writing.
- **Dry run**: `--dry-run` runs the whole create path without committing.
- **Pre-flight**: before anything is deleted, every config is checked. Invalid JSON, a missing
  base or link file, or a tag name that does not exist or matches more than one tag stops the
  run with nothing changed.
- **All or nothing**: if any playlist fails, the whole run rolls back and nothing is committed.
- **Overwrite guard**: overwriting refuses to delete a folder that contains a regular
  (hand-made, non-smart) playlist.
- **Validation**: `playlist validate --all` checks the JSON files without a database.

## Recovery

Regenerate the playlists with `playlist create --all --existing overwrite`. Do not restore a
backup for this: restore rolls back every tag added since the backup was taken. Restore only
when the database itself is damaged.

## Important Notes

1. **Always close Rekordbox** before running any scripts
2. **Start with `--dry-run`** to preview changes
3. **Backups are automatically created** before making changes
4. **Test with a single file** (`--file daytime.json`) before running `--all`

## Troubleshooting

- Close Rekordbox before running any write command.
- Check the database exists at `~/Library/Pioneer/rekordbox/master.db` and is readable and writable.
- Debug one file: `deno task rb --dry-run -v playlist create --file daytime.json`.

## Acknowledgments

- [pyrekordbox](https://github.com/dylanljones/pyrekordbox) for Rekordbox database access
- Pioneer DJ for creating Rekordbox
