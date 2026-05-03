# CLI

Unified entry point that dispatches to processors and command handlers.

## Entry points

- `deno task cli <command> [flags]` — direct invocation
- `./tunewrangler <command> [flags]` — wrapper script (`./install.sh` to set up)

Both run `src/cli/main.ts`, which parses args via `@std/cli/parse-args` and
dispatches based on a `commands` registry.

## Commands

| Command | Description |
|---|---|
| `rename-music` | Rename downloaded music. Default = dry-run + manifest; `--apply <path>` or `--move`. See [the rename workflow](../../README.md#rename-workflow). |
| `rename-bandcamp` | Rename Bandcamp downloads |
| `rename-itunes` | Rename iTunes library |
| `rename-beatport` | Rename Beatport downloads |
| `convert` | Convert FLAC to other formats (preserves metadata) |
| `playlist` | Import / process playlists |
| `youtube` | Add an M3U playlist to YouTube |
| `analyze-dj` | Analyze the DJ collection |
| `logs` | List, tail, view, or clear log files |
| `performance` | Show performance metrics |
| `validate` | Validate config + path existence |

Run `<command> --help` for command-specific flags.

## Global flags

- `--help`, `-h` — show help
- `--version`, `-v` — show version
- `--verbose` — set log level to DEBUG
- `--quiet` — set log level to ERROR

## Adding a new command

1. Add a handler in `src/cli/commands/` (or wire to a processor in `src/processors/`)
2. Register it in the `commands` record in `src/cli/main.ts` with `name`, `description`, `flags`, `examples`, `execute`
3. The auto-generated help picks it up on next run
