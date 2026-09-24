# Configuration

Path management for the main tool. Every path comes from its environment variable, set in the
repo-root `.env` (template: `.env.example`). There are no built-in defaults: a missing variable
throws a `ConfigurationError` naming it, so a command only needs the paths it uses.

## Usage

```typescript
import { loadConfig, getFolder, validatePaths } from "./index.ts";

const config = loadConfig();
const downloadPath = getFolder("downloaded");
const { valid, errors } = await validatePaths(config);
```

## Paths

| Key | Env variable | Purpose |
|---|---|---|
| `music` | `TUNEWRANGLER_MUSIC_PATH` | Main music library |
| `downloads` | `TUNEWRANGLER_DOWNLOADS_PATH` | OS Downloads folder |
| `downloaded` | `TUNEWRANGLER_DOWNLOADED_PATH` | Source for `rename-music` |
| `bandcamp` | `TUNEWRANGLER_BANDCAMP_PATH` | Source for `rename-bandcamp` |
| `itunes` | `TUNEWRANGLER_ITUNES_PATH` | Source for `rename-itunes` |
| `youtube` | `TUNEWRANGLER_YOUTUBE_PATH` | YouTube downloads |
| `djMusic` | `TUNEWRANGLER_DJMUSIC_PATH` | DJ collection (used for dedup) |
| `djPlaylists` | `TUNEWRANGLER_DJPLAYLISTS_PATH` | DJ playlist backups |
| `djPlaylistImport` | `TUNEWRANGLER_DJPLAYLISTIMPORT_PATH` | Playlist import staging |
| `rename` | `TUNEWRANGLER_RENAME_PATH` | Destination for renamed files |
| `backup` | `TUNEWRANGLER_BACKUP_PATH` | Source-file backup destination |
| `transfer` | `TUNEWRANGLER_TRANSFER_PATH` | Transfer/staging folder |

Run `deno task validate` to list the configured paths, flag unset variables, and check that
each set path exists.
