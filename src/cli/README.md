# TuneWrangler CLI

A unified command-line interface for TuneWrangler that provides easy access to all music processing features.

## Installation

### Quick Install

```bash
# Run the installation script
./install.sh

# Test the installation
./tunewrangler --help
```

### System-wide Installation

```bash
# Create a symlink to make it available everywhere
sudo ln -s "$(pwd)/tunewrangler" /usr/local/bin/tunewrangler

# Now you can run from anywhere
tunewrangler --help
```

## Usage

### Basic Commands

```bash
# Show help
tunewrangler --help

# Show version
tunewrangler --version

# Validate configuration
tunewrangler validate

# Get help for a specific command
tunewrangler rename-music --help
```

### Available Commands

| Command | Description | Usage |
|---------|-------------|-------|
| `rename-music` | Rename music files with proper artist - title format | `tunewrangler rename-music` |
| `rename-bandcamp` | Rename Bandcamp music files | `tunewrangler rename-bandcamp` |
| `rename-itunes` | Rename iTunes music files | `tunewrangler rename-itunes` |
| `rename-beatport` | Rename Beatport music files | `tunewrangler rename-beatport` |
| `youtube` | Add M3U playlists to YouTube | `tunewrangler youtube` |
| `playlist` | Import and process playlists | `tunewrangler playlist` |
| `convert` | Convert FLAC files to other formats | `tunewrangler convert` |
| `validate` | Validate configuration and paths | `tunewrangler validate` |

### Global Options

- `--help, -h` - Show help for a command
- `--version, -v` - Show version information
- `--verbose` - Enable verbose output
- `--quiet` - Suppress output

## Examples

### Validate Your Setup

```bash
# Check if your configuration is correct
tunewrangler validate
```

### Process Music Files

```bash
# Rename downloaded music files
tunewrangler rename-music

# Process Bandcamp files
tunewrangler rename-bandcamp

# Process iTunes files
tunewrangler rename-itunes
```

### Work with Playlists

```bash
# Import playlists
tunewrangler playlist

# Add playlist to YouTube
tunewrangler youtube --playlist my-playlist.m3u
```

### Convert Audio Files

```bash
# Convert FLAC files
tunewrangler convert
```

## Configuration

The CLI automatically validates your configuration before running commands. If validation fails, you'll see an error message with details about what needs to be fixed.

### Environment Variables

You can override default paths using environment variables:

```bash
export TUNEWRANGLER_MUSIC_PATH="/custom/music/path"
export TUNEWRANGLER_DOWNLOADS_PATH="/custom/downloads/path"
# ... etc
```

## Error Handling

The CLI includes comprehensive error handling:

- **Configuration validation** before running commands
- **Detailed error messages** with context
- **Graceful failure** with helpful suggestions
- **Logging** for debugging issues

## Development

### Adding New Commands

1. Create a new command function in `src/cli/commands/validate.ts`
2. Add the command to the `commands` object in `src/cli/main.ts`
3. Update the help text and examples

### Command Structure

```typescript
export async function myCommand(args: string[]): Promise<void> {
  const flags = parse(args, {
    boolean: ["help"],
    string: ["option"],
    alias: { help: "h" },
  });

  if (flags.help) {
    console.log(`
🎵 TuneWrangler my-command

Description of what this command does.

USAGE:
  tunewrangler my-command [options]

OPTIONS:
  --help, -h    Show this help message
  --option      Some option
`);
    return;
  }

  // Import and run the actual processor
  await import("../../processors/myProcessor.ts");
}
```

## Troubleshooting

### Common Issues

1. **Permission Denied**: Make sure the `tunewrangler` script is executable

   ```bash
   chmod +x tunewrangler
   ```

2. **Configuration Errors**: Run validation to check your setup

   ```bash
   tunewrangler validate
   ```

3. **Command Not Found**: Make sure you're in the right directory or the CLI is in your PATH

### Getting Help

- `tunewrangler --help` - Show all available commands
- `tunewrangler <command> --help` - Show help for a specific command
- `tunewrangler validate` - Check your configuration
