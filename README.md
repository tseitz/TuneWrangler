# 🎵 TuneWrangler

**Professional Music File Management & Organization Tool**

[![Deno](https://img.shields.io/badge/Deno-1.40+-000000?logo=deno&logoColor=white)](https://deno.land/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

TuneWrangler is a powerful, Deno-based tool for managing and organizing music files. It provides intelligent file
renaming, playlist management, format conversion for compatibility with DJ software, and comprehensive logging
for music enthusiasts, DJs, and audio professionals.

## ✨ Features

- 🎯 **Smart File Renaming** - Intelligent artist/title extraction and formatting
- 📁 **Multi-Platform Support** - Works with iTunes, Bandcamp, Beatport, and more
- 🎵 **Playlist Management** - Import, export, and convert between formats
- 🔄 **Format Conversion** - Convert FLAC to other formats with metadata preservation
- 📊 **Comprehensive Logging** - Professional logging with file rotation and management
- ⚙️ **Flexible Configuration** - Environment-based configuration with validation
- 🛡️ **Error Handling** - Robust error handling with retry mechanisms
- 🚀 **CLI Interface** - Professional command-line interface with help system

## 🚀 Quick Start

### Installation

1. **Install Deno** (if not already installed):

   ```bash
   # macOS/Linux
   curl -fsSL https://deno.land/install.sh | sh
   
   # Windows
   iwr https://deno.land/install.ps1 -useb | iex
   ```

2. **Clone the repository**:

   ```bash
   git clone https://github.com/yourusername/TuneWrangler.git
   cd TuneWrangler
   ```

3. **Install CLI wrapper** (optional):

   ```bash
   chmod +x install.sh
   ./install.sh
   ```

### Basic Usage

```bash
# Validate your configuration
./tunewrangler validate

# Rename music files with proper formatting
./tunewrangler rename-music /path/to/music

# Convert FLAC files to MP3
./tunewrangler convert --input /path/to/flacs --output /path/to/mp3s

# View logs
./tunewrangler logs --tail
```

## 📋 Commands

| Command | Description | Example |
|---------|-------------|---------|
| `rename-music` | Rename music files with artist - title format | `./tunewrangler rename-music --input /music` |
| `rename-bandcamp` | Rename Bandcamp music files | `./tunewrangler rename-bandcamp --input /bandcamp` |
| `rename-itunes` | Rename iTunes music files | `./tunewrangler rename-itunes --input /itunes` |
| `rename-beatport` | Rename Beatport music files | `./tunewrangler rename-beatport --input /beatport` |
| `youtube` | Add M3U playlists to YouTube | `./tunewrangler youtube --playlist playlist.m3u` |
| `playlist` | Import and process playlists | `./tunewrangler playlist --import /playlists` |
| `convert` | Convert FLAC files to other formats | `./tunewrangler convert --input /flacs --output /mp3s` |
| `validate` | Validate configuration and paths | `./tunewrangler validate` |
| `logs` | Manage and view log files | `./tunewrangler logs --list` |

## ⚙️ Configuration

TuneWrangler uses environment variables for configuration. Create a `.env` file or set environment variables:

```bash
# Music directories
export TUNEWRANGLER_MUSIC="/Users/username/Music/"
export TUNEWRANGLER_DOWNLOADS="/Users/username/Downloads/"
export TUNEWRANGLER_YOUTUBE="/Users/username/Music/Youtube/"
export TUNEWRANGLER_DOWNLOADED="/Users/username/Music/Downloaded/"

# DJ directories
export TUNEWRANGLER_DJ_MUSIC="/Users/username/DJ/Collection/"
export TUNEWRANGLER_DJ_PLAYLISTS="/Users/username/DJ/Playlists/"
export TUNEWRANGLER_DJ_PLAYLIST_IMPORT="/Users/username/DJ/Import/"

# Processing directories
export TUNEWRANGLER_RENAME="/Users/username/Music/Renamed/"
export TUNEWRANGLER_BACKUP="/Users/username/Music/Backup/"
export TUNEWRANGLER_TRANSFER="/Users/username/Music/Transfer/"
```

### Platform-Specific Defaults

TuneWrangler automatically detects your platform and sets sensible defaults:

- **macOS**: Uses `~/Music/`, `~/Downloads/`, etc.
- **Linux**: Uses `~/Music/`, `~/Downloads/`, etc.
- **Windows**: Uses `%USERPROFILE%\Music\`, `%USERPROFILE%\Downloads\`, etc.

## 📖 Examples

### Renaming Music Files

```bash
# Rename files in a directory with proper artist - title format
./tunewrangler rename-music --input "/Users/username/Downloads/Music" --output "/Users/username/Music/Renamed"

# Rename Bandcamp files (removes Bandcamp-specific formatting)
./tunewrangler rename-bandcamp --input "/Users/username/Downloads/Bandcamp" --output "/Users/username/Music/Bandcamp"

# Rename iTunes files (preserves iTunes metadata)
./tunewrangler rename-itunes --input "/Users/username/Music/iTunes" --output "/Users/username/Music/Organized"
```

### Playlist Management

```bash
# Import M3U playlist to YouTube
./tunewrangler youtube --playlist "my-playlist.m3u" --name "My Awesome Playlist"

# Process multiple playlists
./tunewrangler playlist --import "/Users/username/Playlists" --format m3u
```

### Format Conversion

```bash
# Convert FLAC files to MP3
./tunewrangler convert --input "/Users/username/Music/FLAC" --output "/Users/username/Music/MP3" --format mp3

# Convert with specific quality
./tunewrangler convert --input "/Users/username/Music/FLAC" --output "/Users/username/Music/MP3" --format mp3 --quality 320
```

### Logging and Debugging

```bash
# View recent logs
./tunewrangler logs --tail

# List all log files
./tunewrangler logs --list

# View specific log file
./tunewrangler logs --file tunewrangler-2025-07-18.log

# Enable verbose logging
./tunewrangler --verbose validate

# Suppress output (errors only)
./tunewrangler --quiet validate
```

## 🔧 Advanced Usage

### Batch Processing

```bash
# Process multiple directories
for dir in /path/to/music1 /path/to/music2 /path/to/music3; do
  ./tunewrangler rename-music --input "$dir" --output "/Users/username/Music/Organized"
done
```

### Integration with Scripts

```bash
#!/bin/bash
# Backup and process music files

# Backup original files
cp -r /Users/username/Downloads/Music /Users/username/Music/Backup/

# Process files
./tunewrangler rename-music --input "/Users/username/Downloads/Music" --output "/Users/username/Music/Organized"

# Convert to MP3
./tunewrangler convert --input "/Users/username/Music/Organized" --output "/Users/username/Music/MP3" --format mp3

# Check logs
./tunewrangler logs --tail
```

### Custom Configuration

```bash
# Use custom configuration for specific operations
export TUNEWRANGLER_MUSIC="/custom/music/path"
export TUNEWRANGLER_DOWNLOADS="/custom/downloads/path"

./tunewrangler validate
./tunewrangler rename-music --input "/custom/music/path"
```

## 🛠️ Development

### Prerequisites

- [Deno](https://deno.land/) 1.40 or higher
- Node.js (for some dependencies)

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/yourusername/TuneWrangler.git
cd TuneWrangler

# Install dependencies
deno cache src/**/*.ts

# Run tests
deno test

# Build (if needed)
deno compile --allow-read --allow-write --allow-run src/cli/main.ts
```

### Project Structure

```bash
TuneWrangler/
├── src/
│   ├── cli/                # Command-line interface
│   │   ├── main.ts         # Main CLI entry point
│   │   └── commands/       # Individual commands
│   ├── core/               # Core functionality
│   │   ├── models/         # Data models
│   │   └── utils/          # Utilities (logging, errors, etc.)
│   ├── config/             # Configuration management
│   └── processors/         # Music processing modules
├── docs/                   # Documentation
├── examples/               # Example scripts and configurations
├── logs/                   # Generated log files
└── output/                 # Generated output files
```

## 📚 Documentation

- **[User Guide](docs/USER_GUIDE.md)** - Complete user documentation
- **[API Reference](docs/API_REFERENCE.md)** - Developer API documentation
- **[Configuration Guide](docs/CONFIGURATION.md)** - Detailed configuration options
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions
- **[Examples](examples/)** - Example scripts and configurations

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests for new functionality
5. Run tests: `deno test`
6. Commit your changes: `git commit -m 'Add amazing feature'`
7. Push to the branch: `git push origin feature/amazing-feature`
8. Open a Pull Request

## 🐛 Troubleshooting

### Common Issues

**Configuration validation fails:**

```bash

./tunewrangler validate
# Check the output and ensure all paths exist
```

**Permission errors:**

```bash

# Ensure you have read/write permissions
chmod +rw /path/to/music/directory
```

**File format not supported:**

```bash

# Check supported formats
./tunewrangler convert --help
```

### Getting Help

1. **Check the logs**: `./tunewrangler logs --tail`
2. **Validate configuration**: `./tunewrangler validate`
3. **Enable verbose mode**: `./tunewrangler --verbose <command>`
4. **Check documentation**: See the [docs/](docs/) directory
5. **Open an issue**: [GitHub Issues](https://github.com/yourusername/TuneWrangler/issues)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Deno](https://deno.land/) - Runtime and standard library
- [FFmpeg](https://ffmpeg.org/) - Audio processing capabilities
- [MusicBrainz](https://musicbrainz.org/) - Music metadata
- All contributors and users of TuneWrangler

## 📊 Status

- ✅ **Core Functionality** - Complete
- ✅ **CLI Interface** - Complete
- ✅ **Error Handling** - Complete
- ✅ **Logging System** - Complete
- ✅ **Configuration Management** - Complete
- ✅ **Documentation** - Complete
- 🔄 **Testing** - Planned
- ✅ **Performance Optimization** - Complete

---

**Made with ❤️ for music lovers everywhere**

For questions, issues, or contributions, please visit our [GitHub repository](https://github.com/tseitz/TuneWrangler).
