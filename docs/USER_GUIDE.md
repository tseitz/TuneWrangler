# TuneWrangler User Guide

Welcome to TuneWrangler! This comprehensive guide will help you get started and make the most of your music file management experience.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Configuration](#configuration)
3. [Basic Operations](#basic-operations)
4. [Advanced Features](#advanced-features)
5. [Troubleshooting](#troubleshooting)
6. [Best Practices](#best-practices)

## Getting Started

### Prerequisites

Before using TuneWrangler, ensure you have:

- **Deno 1.40+** installed on your system
- **Read/write permissions** for your music directories
- **FFmpeg** (optional, for format conversion)

### Installation

1. **Install Deno** (if not already installed):
   ```bash
   # macOS/Linux
   curl -fsSL https://deno.land/install.sh | sh
   
   # Windows
   iwr https://deno.land/install.ps1 -useb | iex
   ```

2. **Clone and setup TuneWrangler**:
   ```bash
   git clone https://github.com/yourusername/TuneWrangler.git
   cd TuneWrangler
   chmod +x install.sh
   ./install.sh
   ```

3. **Verify installation**:
   ```bash
   ./tunewrangler --version
   ```

### First Steps

1. **Validate your configuration**:
   ```bash
   ./tunewrangler validate
   ```

2. **Check the logs**:
   ```bash
   ./tunewrangler logs --tail
   ```

3. **Test with a small directory**:
   ```bash
   ./tunewrangler rename-music --input "/path/to/test/music" --output "/path/to/output"
   ```

## Configuration

### Environment Variables

TuneWrangler uses environment variables for configuration. You can set these in your shell profile or create a `.env` file:

```bash
# Core music directories
export TUNEWRANGLER_MUSIC="/Users/username/Music/"
export TUNEWRANGLER_DOWNLOADS="/Users/username/Downloads/"
export TUNEWRANGLER_YOUTUBE="/Users/username/Music/Youtube/"
export TUNEWRANGLER_DOWNLOADED="/Users/username/Music/Downloaded/"

# DJ-specific directories
export TUNEWRANGLER_DJ_MUSIC="/Users/username/DJ/Collection/"
export TUNEWRANGLER_DJ_PLAYLISTS="/Users/username/DJ/Playlists/"
export TUNEWRANGLER_DJ_PLAYLIST_IMPORT="/Users/username/DJ/Import/"

# Processing directories
export TUNEWRANGLER_RENAME="/Users/username/Music/Renamed/"
export TUNEWRANGLER_BACKUP="/Users/username/Music/Backup/"
export TUNEWRANGLER_TRANSFER="/Users/username/Music/Transfer/"
```

### Platform-Specific Configuration

#### macOS
```bash
# Default paths on macOS
export TUNEWRANGLER_MUSIC="$HOME/Music/"
export TUNEWRANGLER_DOWNLOADS="$HOME/Downloads/"
export TUNEWRANGLER_DJ_MUSIC="$HOME/Documents/DJ/Collection/"
```

#### Linux
```bash
# Default paths on Linux
export TUNEWRANGLER_MUSIC="$HOME/Music/"
export TUNEWRANGLER_DOWNLOADS="$HOME/Downloads/"
export TUNEWRANGLER_DJ_MUSIC="$HOME/DJ/Collection/"
```

#### Windows
```cmd
# Default paths on Windows
set TUNEWRANGLER_MUSIC=%USERPROFILE%\Music\
set TUNEWRANGLER_DOWNLOADS=%USERPROFILE%\Downloads\
set TUNEWRANGLER_DJ_MUSIC=%USERPROFILE%\DJ\Collection\
```

### Configuration Validation

Always validate your configuration before processing files:

```bash
./tunewrangler validate
```

This will check:
- All configured paths exist
- You have read/write permissions
- Required directories are accessible

## Basic Operations

### File Renaming

#### Standard Music Files

Rename music files to the standard "Artist - Title" format:

```bash
# Basic renaming
./tunewrangler rename-music --input "/Users/username/Downloads/Music" --output "/Users/username/Music/Organized"

# With specific options
./tunewrangler rename-music \
  --input "/Users/username/Downloads/Music" \
  --output "/Users/username/Music/Organized" \
  --format "Artist - Title" \
  --preserve-metadata
```

#### Platform-Specific Files

**Bandcamp Files**:
```bash
# Remove Bandcamp-specific formatting
./tunewrangler rename-bandcamp \
  --input "/Users/username/Downloads/Bandcamp" \
  --output "/Users/username/Music/Bandcamp"
```

**iTunes Files**:
```bash
# Preserve iTunes metadata
./tunewrangler rename-itunes \
  --input "/Users/username/Music/iTunes" \
  --output "/Users/username/Music/Organized"
```

**Beatport Files**:
```bash
# Handle Beatport naming conventions
./tunewrangler rename-beatport \
  --input "/Users/username/Downloads/Beatport" \
  --output "/Users/username/Music/Beatport"
```

### Format Conversion

Convert audio files between different formats:

```bash
# Convert FLAC to MP3
./tunewrangler convert \
  --input "/Users/username/Music/FLAC" \
  --output "/Users/username/Music/MP3" \
  --format mp3 \
  --quality 320

# Convert to multiple formats
./tunewrangler convert \
  --input "/Users/username/Music/FLAC" \
  --output "/Users/username/Music/Converted" \
  --format mp3,aac \
  --quality 256
```

### Playlist Management

#### Import Playlists
```bash
# Import M3U playlist
./tunewrangler playlist \
  --import "/Users/username/Playlists" \
  --format m3u \
  --output "/Users/username/Music/Playlists"
```

#### YouTube Integration
```bash
# Add playlist to YouTube
./tunewrangler youtube \
  --playlist "my-playlist.m3u" \
  --name "My Awesome Playlist" \
  --description "A collection of my favorite tracks"
```

## Advanced Features

### Batch Processing

Process multiple directories efficiently:

```bash
#!/bin/bash
# Batch processing script

directories=(
  "/Users/username/Downloads/Music1"
  "/Users/username/Downloads/Music2"
  "/Users/username/Downloads/Music3"
)

for dir in "${directories[@]}"; do
  echo "Processing: $dir"
  ./tunewrangler rename-music \
    --input "$dir" \
    --output "/Users/username/Music/Organized"
done
```

### Logging and Monitoring

#### View Logs
```bash
# View recent logs
./tunewrangler logs --tail

# List all log files
./tunewrangler logs --list

# View specific log file
./tunewrangler logs --file tunewrangler-2025-07-18.log
```

#### Verbose Mode
```bash
# Enable detailed logging
./tunewrangler --verbose rename-music --input "/path/to/music"

# Suppress output (errors only)
./tunewrangler --quiet rename-music --input "/path/to/music"
```

### Custom Workflows

#### DJ Workflow
```bash
#!/bin/bash
# Complete DJ music processing workflow

# 1. Backup original files
cp -r /Users/username/Downloads/DJ /Users/username/DJ/Backup/

# 2. Rename files
./tunewrangler rename-music \
  --input "/Users/username/Downloads/DJ" \
  --output "/Users/username/DJ/Collection"

# 3. Convert to DJ-friendly format
./tunewrangler convert \
  --input "/Users/username/DJ/Collection" \
  --output "/Users/username/DJ/MP3" \
  --format mp3 \
  --quality 320

# 4. Import playlists
./tunewrangler playlist \
  --import "/Users/username/DJ/Playlists" \
  --output "/Users/username/DJ/Processed"

# 5. Check results
./tunewrangler logs --tail
```

#### Music Library Organization
```bash
#!/bin/bash
# Organize entire music library

# 1. Validate configuration
./tunewrangler validate

# 2. Process downloads
./tunewrangler rename-music \
  --input "/Users/username/Downloads/Music" \
  --output "/Users/username/Music/Organized"

# 3. Process platform-specific files
./tunewrangler rename-bandcamp \
  --input "/Users/username/Downloads/Bandcamp" \
  --output "/Users/username/Music/Bandcamp"

./tunewrangler rename-itunes \
  --input "/Users/username/Music/iTunes" \
  --output "/Users/username/Music/Organized"

# 4. Convert high-quality files
./tunewrangler convert \
  --input "/Users/username/Music/FLAC" \
  --output "/Users/username/Music/MP3" \
  --format mp3 \
  --quality 320

# 5. Generate report
./tunewrangler logs --tail
```

## Troubleshooting

### Common Issues

#### Configuration Errors
**Problem**: Configuration validation fails
```bash
./tunewrangler validate
# Error: Path 'music' does not exist: /Users/username/Music/
```

**Solution**: 
1. Check if the directory exists
2. Verify environment variables are set correctly
3. Ensure you have read/write permissions

```bash
# Check directory exists
ls -la /Users/username/Music/

# Set environment variable
export TUNEWRANGLER_MUSIC="/Users/username/Music/"

# Check permissions
chmod +rw /Users/username/Music/
```

#### Permission Errors
**Problem**: Permission denied errors
```bash
# Error: Permission denied when accessing /path/to/music
```

**Solution**:
```bash
# Check current permissions
ls -la /path/to/music

# Fix permissions
chmod +rw /path/to/music
chmod +rw /path/to/music/*

# For directories
chmod +rwx /path/to/music
```

#### File Format Issues
**Problem**: Unsupported file format
```bash
# Error: Unsupported audio format: .wma
```

**Solution**:
1. Check supported formats: `./tunewrangler convert --help`
2. Convert unsupported formats first
3. Use FFmpeg for manual conversion if needed

#### Log Analysis
**Problem**: Operation failed but unclear why

**Solution**:
```bash
# Check recent logs
./tunewrangler logs --tail

# Enable verbose mode
./tunewrangler --verbose <command>

# Check specific log file
./tunewrangler logs --file tunewrangler-2025-07-18.log
```

### Getting Help

1. **Check the documentation**: This guide and other docs in the `docs/` directory
2. **Validate configuration**: `./tunewrangler validate`
3. **Check logs**: `./tunewrangler logs --tail`
4. **Enable verbose mode**: `./tunewrangler --verbose <command>`
5. **Open an issue**: [GitHub Issues](https://github.com/yourusername/TuneWrangler/issues)

## Best Practices

### File Organization

1. **Use consistent naming**: Always use the same format for your music files
2. **Backup before processing**: Always backup original files before renaming
3. **Test on small batches**: Test commands on small directories first
4. **Use descriptive output paths**: Use meaningful names for output directories

### Performance

1. **Process in batches**: Don't process your entire library at once
2. **Use appropriate quality settings**: Balance quality vs. file size
3. **Monitor disk space**: Ensure you have enough space for conversions
4. **Use SSD for processing**: Faster storage improves performance

### Data Safety

1. **Regular backups**: Keep backups of your music library
2. **Validate before processing**: Always run validation first
3. **Check logs**: Review logs after operations
4. **Test on copies**: Test new workflows on copied files

### Workflow Optimization

1. **Automate repetitive tasks**: Use scripts for common workflows
2. **Standardize your process**: Use consistent commands and options
3. **Document your workflow**: Keep notes of what works for you
4. **Regular maintenance**: Periodically clean up and organize

### Example Workflows

#### Daily Music Processing
```bash
#!/bin/bash
# Daily music processing workflow

# 1. Check for new downloads
if [ -d "/Users/username/Downloads/Music" ]; then
  # 2. Backup
  cp -r /Users/username/Downloads/Music /Users/username/Music/Backup/$(date +%Y%m%d)
  
  # 3. Process
  ./tunewrangler rename-music \
    --input "/Users/username/Downloads/Music" \
    --output "/Users/username/Music/Organized"
  
  # 4. Clean up
  rm -rf /Users/username/Downloads/Music
fi

# 5. Check logs
./tunewrangler logs --tail
```

#### Weekly Library Maintenance
```bash
#!/bin/bash
# Weekly library maintenance

# 1. Validate configuration
./tunewrangler validate

# 2. Process any pending files
./tunewrangler rename-music \
  --input "/Users/username/Music/Pending" \
  --output "/Users/username/Music/Organized"

# 3. Convert new FLAC files
./tunewrangler convert \
  --input "/Users/username/Music/FLAC" \
  --output "/Users/username/Music/MP3" \
  --format mp3

# 4. Update playlists
./tunewrangler playlist \
  --import "/Users/username/Playlists" \
  --output "/Users/username/Music/Playlists"

# 5. Generate report
echo "Weekly maintenance complete"
./tunewrangler logs --tail
```

---

**Need more help?** Check out the [Troubleshooting Guide](TROUBLESHOOTING.md) or [API Reference](API_REFERENCE.md) for detailed technical information. 