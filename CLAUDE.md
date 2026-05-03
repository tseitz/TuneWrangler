# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TuneWrangler is a music file management tool with two distinct components:

1. **Main tool** (Deno/TypeScript): CLI for renaming music files (Bandcamp, iTunes, Beatport formats), playlist management, FLAC conversion, and DJ collection analysis.
2. **soundcloud_dl** (Python/uv): Subproject for automating SoundCloud free downloads using the SoundCloud API (Phase 1) and browser-use with a local LLM agent (Phase 2).

## Commands

### Deno (main tool)

```bash
# Run via CLI wrapper (needs .env configured with paths)
./tunewrangler <command> [options]

# Or via deno tasks (shortcuts in deno.json)
deno task rM          # rename music
deno task rBc         # rename bandcamp
deno task rI          # rename itunes
deno task rBp         # rename beatport
deno task ytRb        # add M3U to YouTube playlist
deno task playlistImport  # import playlists
deno task cF          # convert FLACs
deno task validate    # validate config
deno task cli         # run full CLI (deno run -A src/cli/main.ts)

# Run directly
deno run -A src/cli/main.ts rename-music
deno run -A src/processors/renameMusic.ts
```

### soundcloud_dl (Python subproject)

```bash
cd soundcloud_dl

# Run the tool
uv run python -m soundcloud_dl.main

# Or from repo root
uv run --project soundcloud_dl soundcloud-dl

# Lint and type check
uv run ruff check soundcloud_dl && uv run ruff format soundcloud_dl
uv run ty check soundcloud_dl
```

## Architecture

### Deno/TypeScript (`src/`)

- **`src/cli/main.ts`** — CLI entry point. Parses args, dispatches to commands. All commands are registered in a `commands` record with metadata (flags, examples, execute function).
- **`src/cli/commands/`** — Command handlers (validate, logs, performance, analyze).
- **`src/processors/`** — Core music processing logic. Each processor handles a specific source format (Bandcamp, iTunes, Beatport, generic music). Some have "Optimized" variants (`renameMusicOptimized.ts`, `renameBandcampOptimized.ts`, `convertFlacsOptimized.ts`).
- **`src/config/paths.ts`** — Platform-specific path defaults (macOS/Windows/Linux) with env var overrides (`TUNEWRANGLER_*_PATH`). Paths are hardcoded to the owner's directory structure as defaults.
- **`src/core/utils/`** — Shared utilities: logger (with file rotation), custom error classes, retry logic, performance monitoring, unicode handling, validation.
- **`src/core/models/`** — Data models: `Song.ts`, `ArtistAnalysis.ts`, `Semaphore.ts` (concurrency control), shared types.

### Python (`soundcloud_dl/`)

- **`config.py`** — Loads `.env` from TuneWrangler root (parent of soundcloud_dl). All settings via `TUNEWRANGLER_SC_*` env vars.
- **`main.py`** — Entry point. Runs Phase 1 (API playlist extraction) then Phase 2 (browser-use agent per track).
- **`playlist.py`** — SoundCloud API interaction for extracting track URLs.
- **`agent_task.py`** — browser-use agent configuration for per-track free download automation.
- **`resume.py`** — Tracks processed URLs in `logs/soundcloud_dl_processed.json` to skip on re-runs.
- **`playlist_cache.py`** — Caches playlist track lists in `logs/soundcloud_dl_playlist_cache.json`.

## Key Conventions

- **Runtime versions**: Deno 2.6.9, Python 3.12, FFmpeg 7.1.1 (managed via `.mise.toml`)
- **Configuration**: Main tool uses `TUNEWRANGLER_*` env vars with platform-specific hardcoded defaults. SoundCloud subproject uses `TUNEWRANGLER_SC_*` env vars loaded from root `.env`.
- **Logging**: Both projects log to `logs/` at the repo root. Deno uses a custom logger (`src/core/utils/logger.ts`). Python uses stdlib logging.
- **Python tooling**: uv for package management, ruff for linting/formatting (line-length 100, select ALL minus D/COM812/ISC001), ty for type checking.
- **Markdown**: Linted with markdownlint (`.markdownlint.json`). Lines under 100 chars. Blank lines around code blocks and headers.
- **Commit style**: Conventional commits (`feat:`, `fix:`, etc.).
- **No summary files**: Don't create summary markdown files after completing work. Only document actual features.
