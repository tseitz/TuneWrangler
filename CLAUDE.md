# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project Overview

TuneWrangler is a music file management tool with two components:

1. **Main tool** (Deno/TypeScript, `src/`): CLI that renames downloaded music files into a normalized `artist - album - title` format, manages playlists, converts formats, and analyzes a DJ collection.
2. **soundcloud_dl** (Python/uv, `soundcloud_dl/`): Automates SoundCloud free-download gates using Playwright + CDP attach. Pulls track URLs from the SoundCloud API, then drives a real Chrome instance through per-host gate handlers.

## Commands

### Deno (main tool)

```bash
deno task rM                       # rename music: dry-run, writes manifest
deno task rM --apply <manifest>    # apply approved entries from a manifest
deno task rM --move                # legacy: parse + move all in one shot
deno task promote <manifest>       # copy manifest into tests/corpus/ as regression coverage
deno task test                     # run all tests (unit + corpus regression)
deno task validate                 # validate config paths exist
deno task rBc / rI / rBp           # rename Bandcamp / iTunes / Beatport
deno task cF                       # convert FLACs
deno task ytRb                     # add M3U to YouTube playlist
deno task playlistImport           # import playlists
deno task cli                      # full CLI entry point
```

### soundcloud_dl (Python)

All Python tooling is wrapped as `deno task py:*` so everything runs from the
repo root and there's a single discoverable entry point. Always use these —
don't `cd soundcloud_dl/` and don't invoke `uv` directly:

```bash
deno task py                  # run the downloader (soundcloud-dl)
deno task py:test             # pytest
deno task py:check            # ty type-check
deno task py:lint             # ruff lint
deno task py:fmt              # ruff format (writes)
deno task py:fmt:check        # ruff format --check
```

The wrappers expand to `uv run --project soundcloud_dl <cmd>` — see `deno.json`.

## Rename workflow (the important one)

The `rename-music` flow is **dry-run first, apply second** — never `--move` unless the user explicitly asks for it. The manifest exists so the user can review low-confidence entries before any files are touched.

```
1. deno task rM                       → writes logs/tunewrangler/manifests/rename-manifest-<ts>.json
                                        Each entry has confidence (high/medium/low) + decision (apply/review/skip)
2. User opens manifest, edits "decision" or "proposed" fields for low-confidence entries
3. deno task rM --apply <manifest>    → moves only entries with decision: "apply"
4. deno task promote <manifest>       → locks the batch into tests/corpus/ as regression tests
```

Confidence model lives in `src/core/confidence.ts`. Low-confidence triggers: 3-part filenames with bare remix keywords (FLIP/EDIT/DUB/etc. as the last segment), empty artist/title after parsing, mangled extensions (`.mp3` appearing twice), or artist duplicated across artist+album fields.

The corpus harness (`src/core/corpus_test.ts`) loads every promoted manifest and runs `parseDownloadedSong` against each entry. `proposed === parser_output` becomes a regression test; `proposed !== parser_output` (user override) is logged as a parser improvement target.

## Architecture

### Deno/TypeScript (`src/`)

- **`src/cli/main.ts`** — CLI entry. Args parsed via `@std/cli/parse-args`. Commands registered in a record with metadata.
- **`src/cli/commands/`** — Command handlers (validate, logs, performance, analyze).
- **`src/processors/`** — Per-source processors. `renameMusic.ts` is the manifest-driven flow; the rest (`renameBandcamp`, `renameItunes`, `renameBeatport`, `convertFlacs`) still use the older immediate-move pattern.
- **`src/processors/*Optimized.ts`** — **Deprecated duplicates of their non-Optimized counterparts.** Drift hazard. Don't extend these; consolidate into one file when touched.
- **`src/core/parser.ts`** — `parseDownloadedSong()`: extracted parsing pipeline. Pure-ish entry point used by both `renameMusic` and the corpus tests.
- **`src/core/confidence.ts`** — `scoreConfidence()`: returns `{level, reasons, decision}`.
- **`src/core/manifest.ts`** — `Manifest`/`ManifestEntry` types + `readManifest`/`writeManifest`. `parser_output` is immutable; `proposed` is user-editable.
- **`src/core/models/Song.ts`** — Song data model. Heavy mutation, regex-based methods (`checkRemix`, `checkFeat`, `checkWith`). Refactor target — see "Known tech debt" below.
- **`src/core/utils/`** — `common.ts` (move/cache/dedup), `logger.ts` (file-rotating), `unicode.ts`, `errors.ts`, `retry.ts`, `performance.ts`.
- **`src/config/paths.ts`** — Platform-specific path defaults with `TUNEWRANGLER_*_PATH` env var overrides.
- **`scripts/promote.ts`** — Copies an applied manifest into `tests/corpus/`.
- **`tests/corpus/`** — Promoted manifests, loaded automatically by the corpus test.

### Python (`soundcloud_dl/`)

- **`config.py`** — Loads `.env` from repo root. All settings via `TUNEWRANGLER_SC_*` env vars. Provides `get_log_dir()` (returns `logs/soundcloud_dl/`), `get_debug_dir()`, `get_processed_file()`, `get_playlist_cache_file()`.
- **`main.py`** — Entry. Phase 1 = pull track URLs from SoundCloud API. Phase 2 = iterate tracks through gate handlers in a CDP-attached Chrome.
- **`playlist.py`** — SoundCloud API: extracts track URLs from a playlist URL.
- **`chrome_bringup.py`** — Launches Chrome with `--remote-debugging-port`, attaches Playwright via CDP.
- **`gate_handlers/`** — Per-host gate strategies. `base.py` defines `BaseGateHandler` with declarative steps (required/optional, depends_on). `registry.py` maps URL hosts to handlers. Add a new handler by subclassing and registering.
- **`captcha.py`** — Detects Cloudflare/captcha walls; pauses for manual completion.
- **`resume.py`** — Records each URL's terminal state (`done`/`unsupported`/`captcha_pending`/`manual_review`/`failed`) in `logs/soundcloud_dl/processed.json`.
- **`playlist_cache.py`** — Caches playlist track lists in `logs/soundcloud_dl/playlist_cache.json` to skip API hits on re-runs.

## Logs and state

```
logs/
├── tunewrangler/
│   ├── tunewrangler-YYYY-MM-DD.log         # rotating Deno logger
│   └── manifests/
│       └── rename-manifest-<timestamp>.json # dry-run output
└── soundcloud_dl/
    ├── soundcloud_dl.log                   # Python stdlib logging
    ├── processed.json                      # resume state per playlist
    ├── playlist_cache.json                 # cached API responses
    └── debug/
        └── <track>.png                     # Playwright screenshots on failure
```

## Known tech debt

- **`Song.ts` is doing too many jobs** — model + parser + regex stack + normalizer + dedup state, all with mutation. Refactor target. Wait until `tests/corpus/` has 50+ entries before touching it (so changes are testable). The `parser.ts` extraction is the first step in this direction.
- **`checkRemix` has 7 near-identical regex branches** (REMIX/REFIX/FLIP/EDIT/BOOTLEG/REBOOT/DUB). Should be one data-driven loop.

## Conventions

- **Runtimes**: Deno 2.6.9, Python 3.12, FFmpeg 7.1.1 (managed via `.mise.toml`).
- **Env vars**: Main tool uses `TUNEWRANGLER_*_PATH`; soundcloud_dl uses `TUNEWRANGLER_SC_*`. Both load from repo-root `.env`.
- **Python tooling**: uv, ruff (line-length 100, select ALL minus D/COM812/ISC001), ty.
- **Markdown**: markdownlint enforced (`.markdownlint.json`). Lines under 100 chars; blank lines around code blocks and headers.
- **Commits**: Conventional (`feat:`, `fix:`, `refactor:`, etc.). **Land directly on `main`** — solo project, no feature branches unless explicitly requested.
- **Testing**: `deno task test` for the main tool (unit + regression corpus). `pytest` for soundcloud_dl. New rename-pipeline changes should add a corpus entry rather than handwritten tests where possible.
- **No summary docs**: Don't create post-task `*_SUMMARY.md` files. Document features in CLAUDE.md or README.md, not throwaway markdown.
- **Sandbox quirk**: Writes to the Google Drive cloud-mount path (`/Users/tseitz/Library/CloudStorage/...`) require running with `dangerouslyDisableSandbox: true`.
