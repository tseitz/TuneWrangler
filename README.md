# TuneWrangler

Music file management for DJs. Renames downloaded tracks into a consistent
`artist - album - title` format, manages playlists, converts formats for DJ
software, and automates SoundCloud free downloads.

Built for personal use against a specific directory layout — see
[Configuration](#configuration). Heavy on opinions, light on flexibility.

## Components

| Component | Stack | What it does |
|---|---|---|
| Main tool (`src/`) | Deno 2 / TypeScript | Renames music, converts FLACs, manages playlists, analyzes a DJ collection |
| `soundcloud_dl/` | Python 3.12 / uv | Drives a real Chrome via Playwright + CDP through SoundCloud free-download gates |

## Quick start

```bash
# Install runtimes via mise
mise install

# Configure paths (see "Configuration" below)
cp examples/env.example .env
$EDITOR .env

# Verify config
deno task validate

# Rename downloaded music — dry-run first, then apply
deno task rM
deno task rM --apply ./logs/tunewrangler/manifests/rename-manifest-<timestamp>.json
```

## Rename workflow

The `rename-music` flow uses a **manifest workflow** so you can review the
parser's guesses before any files are moved:

1. **Dry-run** — `deno task rM` parses every file in `TUNEWRANGLER_DOWNLOADED_PATH`,
   scores confidence (high/medium/low), and writes a JSON manifest to
   `logs/tunewrangler/manifests/`. No files are touched.
2. **Review** — open the manifest. High and medium confidence entries are
   pre-approved (`decision: "apply"`). Low-confidence entries are flagged
   (`decision: "review"`) with reasons. Edit the `proposed` filename or change
   `decision` as needed.
3. **Apply** — `deno task rM --apply <manifest>` moves only the entries you
   approved. The source file is backed up to `TUNEWRANGLER_BACKUP_PATH` first.
4. **Promote** — `deno task promote <manifest>` copies the applied manifest
   into `tests/corpus/` so the parser can never silently regress on those
   filenames.

Legacy `--move` mode (parse + move all in one shot, no review) is preserved
but not recommended for unfamiliar source folders.

## Commands

```bash
deno task rM                       # dry-run rename, writes manifest
deno task rM --apply <manifest>    # apply approved entries
deno task rM --move                # legacy: parse + move all
deno task promote <manifest>       # add manifest to regression test corpus
deno task test                     # run all tests (unit + corpus)
deno task validate                 # validate config paths

deno task rBc / rI / rBp           # rename Bandcamp / iTunes / Beatport
deno task cF                       # convert FLACs
deno task ytRb                     # add M3U to YouTube playlist
deno task playlistImport           # import playlists
```

## Configuration

All paths are configurable via `TUNEWRANGLER_*_PATH` environment variables
(typically set in a repo-root `.env`). Defaults are platform-specific and
hardcoded for the maintainer's directory structure — you'll want to override
them.

| Variable | Purpose |
|---|---|
| `TUNEWRANGLER_DOWNLOADED_PATH` | Source folder for `rename-music` |
| `TUNEWRANGLER_DJMUSIC_PATH` | DJ collection used for duplicate detection |
| `TUNEWRANGLER_RENAME_PATH` | Destination for renamed files |
| `TUNEWRANGLER_BACKUP_PATH` | Source-file backup destination |
| `TUNEWRANGLER_BANDCAMP_PATH` | Source for `rename-bandcamp` |
| `TUNEWRANGLER_ITUNES_PATH` | Source for `rename-itunes` |
| `TUNEWRANGLER_YOUTUBE_PATH` | YouTube downloads |
| `TUNEWRANGLER_DJPLAYLISTS_PATH` | DJ playlist backups |
| `TUNEWRANGLER_DJPLAYLISTIMPORT_PATH` | Playlist import staging |
| `TUNEWRANGLER_TRANSFER_PATH` | Transfer/staging folder |

soundcloud_dl uses a separate `TUNEWRANGLER_SC_*` namespace — see
`soundcloud_dl/README.md`.

## soundcloud_dl

Subproject that automates SoundCloud free-download gates. Pulls track URLs
from the SoundCloud API, then drives a real Chrome instance (CDP-attached)
through per-host gate handlers.

```bash
uv run --project soundcloud_dl soundcloud-dl
```

See `soundcloud_dl/README.md` for setup details.

## Project layout

```
src/                          Main tool (Deno/TypeScript)
├── cli/                      CLI entry + commands
├── config/                   Path config with platform defaults
├── core/
│   ├── parser.ts             Filename parsing pipeline
│   ├── confidence.ts         Confidence scoring for rename proposals
│   ├── manifest.ts           Manifest types + read/write
│   ├── models/               Song, Semaphore, ArtistAnalysis
│   └── utils/                Logger, errors, retry, unicode, etc.
├── processors/               Per-source rename processors + FLAC conversion
└── ...

soundcloud_dl/                Python subproject
├── soundcloud_dl/            Module source
└── tests/                    pytest tests

scripts/promote.ts            Promote manifest → corpus
tests/corpus/                 Promoted manifests = regression coverage
logs/                         Logs + state (see CLAUDE.md for layout)
examples/                     Sample env file + helper scripts
```

## Development

```bash
deno task test                 # 267+ tests including corpus regression
deno check src/                # typecheck

# soundcloud_dl
uv run --project soundcloud_dl pytest soundcloud_dl/tests/
uv run --project soundcloud_dl ruff check soundcloud_dl/soundcloud_dl
uv run --project soundcloud_dl ty check soundcloud_dl/soundcloud_dl
```

See [`CLAUDE.md`](CLAUDE.md) for architecture details, the rename workflow in
depth, and known tech debt.

## License

MIT
