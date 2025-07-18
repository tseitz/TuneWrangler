# Configuration System

The TuneWrangler configuration system provides flexible path management across different platforms.

## Features

- **Platform Detection**: Automatically detects macOS, Windows, or Linux
- **Environment Variables**: Override any path using environment variables
- **Path Validation**: Validates that configured paths exist
- **Type Safety**: Full TypeScript support with proper interfaces

## Usage

### Basic Usage

```typescript
import { loadConfig, getFolder } from "../config/index.ts";

// Load all configuration
const config = loadConfig();

// Get a specific folder path
const musicPath = getFolder("music");
const downloadsPath = getFolder("downloads");
```

### Platform Detection

```typescript
import { detectPlatform } from "../config/index.ts";

const platform = detectPlatform();
console.log(`Running on: ${platform.isMac ? "macOS" : platform.isWindows ? "Windows" : "Linux"}`);
```

### Path Validation

```typescript
import { validatePaths } from "../config/index.ts";

const config = loadConfig();
const validation = await validatePaths(config);

if (!validation.valid) {
  console.error("Invalid paths:", validation.errors);
}
```

## Environment Variables

You can override any path using environment variables:

```bash
# Set custom paths
export TUNEWRANGLER_MUSIC_PATH="/custom/music/path"
export TUNEWRANGLER_DOWNLOADS_PATH="/custom/downloads/path"
export TUNEWRANGLER_YOUTUBE_PATH="/custom/youtube/path"

# Run with custom configuration
deno task rM
```

## Available Paths

| Path | Environment Variable | Description |
|------|-------------------|-------------|
| `music` | `TUNEWRANGLER_MUSIC_PATH` | Main music library |
| `downloads` | `TUNEWRANGLER_DOWNLOADS_PATH` | Downloads folder |
| `playlists` | `TUNEWRANGLER_PLAYLISTS_PATH` | Playlist storage |
| `youtube` | `TUNEWRANGLER_YOUTUBE_PATH` | YouTube downloads |
| `downloaded` | `TUNEWRANGLER_DOWNLOADED_PATH` | Downloaded music |
| `itunes` | `TUNEWRANGLER_ITUNES_PATH` | iTunes music folder |
| `formatted` | `TUNEWRANGLER_FORMATTED_PATH` | Formatted playlists |
| `broken` | `TUNEWRANGLER_BROKEN_PATH` | Broken/corrupted files |
| `djMusic` | `TUNEWRANGLER_DJMUSIC_PATH` | DJ music collection |
| `djPlaylists` | `TUNEWRANGLER_DJPLAYLISTS_PATH` | DJ playlist backups |
| `djPlaylistImport` | `TUNEWRANGLER_DJPLAYLISTIMPORT_PATH` | DJ playlist imports |
| `rename` | `TUNEWRANGLER_RENAME_PATH` | Renamed music output |
| `backup` | `TUNEWRANGLER_BACKUP_PATH` | Backup directory |
| `transfer` | `TUNEWRANGLER_TRANSFER_PATH` | Transfer music folder |

## Validation

Run the validation task to check your configuration:

```bash
deno task validate
```

This will:
- Detect your platform
- Show all configured paths
- Validate that paths exist
- Display any configuration errors 