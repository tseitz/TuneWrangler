# Rekordbox Smart Playlist Tools

A collection of Python scripts for managing Rekordbox 6 databases, smart playlists, and metadata synchronization. These tools help DJs maintain organized music collections and create complex smart playlists from JSON configurations.

## 🎯 What This Project Does

This project provides several standalone Python scripts that help you:

- **Create Smart Playlists**: Generate complex Rekordbox smart playlists from JSON configuration files
- **Fix Metadata Issues**: Synchronize metadata between your Rekordbox database and filename formats
- **Backup & Restore**: Safely backup and restore your Rekordbox database
- **Manage Playlists**: Copy, modify, and organize your Rekordbox playlists programmatically

## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+** installed
2. **Rekordbox 6** installed and configured
3. **macOS** (scripts are designed for macOS file paths)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/rekordbox-smart-playlist.git
   cd rekordbox-smart-playlist
   ```

2. **Install dependencies:**
   ```bash
   # Install pyrekordbox (may require additional setup)
   pip install pyrekordbox
   
   # If you encounter issues with pyrekordbox, you may need sqlcipher3:
   # See troubleshooting section below
   ```

3. **Verify your Rekordbox database location:**
   ```bash
   # Default location (adjust if different):
   # ~/Library/Pioneer/rekordbox6/master.db
   ```

## 📋 Available Scripts

### 1. `fix_rekordbox_metadata.py` - Metadata Synchronization Tool

**Purpose**: Fixes metadata discrepancies between your Rekordbox database and filename formats.

**Problem it solves**: When you drag files into Rekordbox, sometimes the metadata doesn't get parsed correctly from the filename, resulting in titles like "[artist] - [title]" instead of just "title".

#### Usage Examples

**Interactive Mode (Recommended for first-time use):**
```bash
python fix_rekordbox_metadata.py
```
This will prompt you for each file that has metadata differences.

**Preview what would be changed (safe to run):**
```bash
python fix_rekordbox_metadata.py --preview --dry-run
```

**Batch Mode - Use database metadata for all files:**
```bash
python fix_rekordbox_metadata.py --batch-database --dry-run
```

**Batch Mode - Use filename metadata for all files:**
```bash
python fix_rekordbox_metadata.py --batch-filename --dry-run
```

**Update filenames to match database metadata:**
```bash
python fix_rekordbox_metadata.py --update-filenames --dry-run
```

#### Command Line Options

```bash
python fix_rekordbox_metadata.py [OPTIONS]

Options:
  --collection-path PATH     Path to your music collection
                            (default: /Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Collection/)
  --dry-run                 Show what would be updated without making changes
  --preview, -p             Show preview of changes without processing
  --preview-count N         Number of files to preview (default: 10)
  --batch-database          Use database metadata as source of truth for all files
  --batch-filename          Use filename metadata as source of truth for all files
  --update-filenames        Update filenames to match database metadata
  --skip-backup             Skip automatic backup before making changes (use with caution)
  --list-backups            List available backups and exit
  --config PATH             Path to a JSON configuration file
  --verbose, -v             Enable verbose logging
  --help, -h                Show help information
```

#### Filename Format Support

The script expects filenames in these formats:
- `[artist] - [title].mp3`
- `[artist] - [album] - [title].mp3`

#### Safety Features

- **Automatic Backups**: Creates backups before making changes
- **Dry Run Mode**: Preview all changes before applying
- **Interactive Mode**: Choose what to do for each file
- **Backup Storage**: `/Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Rekordbox DB Backup/`

### 2. `smart-playlists.py` - Smart Playlist Creator

**Purpose**: Creates Rekordbox smart playlists from JSON configuration files.

#### Usage Examples

**Create all playlists from JSON files:**
```bash
python smart-playlists.py
```

**Create playlists from specific JSON file:**
```bash
python smart-playlists.py house.json
```

#### Configuration Format

Create JSON files in the `playlist-data/` directory with this structure:

```json
{
  "data": [
    {
      "parent": "House",
      "mainConditions": ["House"],
      "negativeConditions": ["Archive"],
      "playlists": [
        {
          "name": "Deep House",
          "operator": 1,
          "contains": ["Deep House"]
        },
        {
          "name": "Party Hits",
          "operator": 1,
          "contains": ["Party Hits"],
          "rating": ["4", "5"]
        }
      ]
    }
  ]
}
```

### 3. `app.py` - Database Management Tool

**Purpose**: Provides various Rekordbox database operations and utilities.

#### Usage Examples

**Run the main playlist processing:**
```bash
python app.py
```

**Create a backup:**
```python
from rekordbox_backup import backup_rekordbox_db
backup_path = backup_rekordbox_db()
```

**List existing backups:**
```python
from rekordbox_backup import list_backups
list_backups()
```

### 4. `rekordbox_backup.py` - Backup & Restore Tool

**Purpose**: Comprehensive backup and restore functionality for Rekordbox databases.

#### Usage Examples

**Create a backup:**
```bash
python -c "from rekordbox_backup import backup_rekordbox_db; backup_rekordbox_db()"
```

**List available backups:**
```bash
python -c "from rekordbox_backup import list_backups; list_backups()"
```

**Restore from backup:**
```bash
python -c "from rekordbox_backup import restore_rekordbox_db; restore_rekordbox_db('/path/to/backup.zip')"
```

## 🛠️ Getting Help

### For Each Script

**Get help for any script:**
```bash
python script_name.py --help
```

**Examples:**
```bash
python fix_rekordbox_metadata.py --help
python smart-playlists.py --help
```

### Common Issues & Solutions

#### 1. **pyrekordbox Installation Issues**

If you get errors installing pyrekordbox, you may need to install sqlcipher3 first:

```bash
# Install sqlcipher3 (macOS with Homebrew)
brew install sqlcipher

# Clone and install sqlcipher3 Python package
git clone https://github.com/coleifer/sqlcipher3
cd sqlcipher3
SQLCIPHER_PATH=$(brew info sqlcipher | awk 'NR==4 {print $1; exit}')
C_INCLUDE_PATH="$SQLCIPHER_PATH"/include LIBRARY_PATH="$SQLCIPHER_PATH"/lib python setup.py build
C_INCLUDE_PATH="$SQLCIPHER_PATH"/include LIBRARY_PATH="$SQLCIPHER_PATH"/lib python setup.py install
cd ..

# Then install pyrekordbox
pip install pyrekordbox
```

#### 2. **Database Connection Errors**

**Problem**: "Failed to initialize Rekordbox database"

**Solutions**:
- Ensure Rekordbox is **closed** before running scripts
- Check database location: `~/Library/Pioneer/rekordbox6/master.db`
- Verify you have read/write permissions to the database file

#### 3. **Permission Errors**

**Problem**: "Permission denied" when accessing files or database

**Solutions**:
- Check file permissions on your music collection directory
- Ensure write permissions to backup directory
- Run with appropriate user permissions

#### 4. **Metadata Not Found Errors**

**Problem**: "Could not find content in database for: filename.mp3"

**Solutions**:
- Ensure the file exists in your Rekordbox collection
- Check that the filename matches exactly (case-sensitive)
- Try importing the file into Rekordbox first

#### 5. **Filename Format Issues**

**Problem**: "Could not parse filename format"

**Solutions**:
- Ensure filenames follow the expected format: `[artist] - [title].ext`
- Check for special characters that might break parsing
- Use `--preview` to see which files have parsing issues

### Debugging Tips

**Enable verbose logging:**
```bash
python fix_rekordbox_metadata.py --verbose --dry-run
```

**Preview changes before applying:**
```bash
python fix_rekordbox_metadata.py --preview --dry-run
```

**Check what files would be processed:**
```bash
python fix_rekordbox_metadata.py --preview --preview-count 50
```

## 📁 Project Structure

```
rekordbox-smart-playlist/
├── fix_rekordbox_metadata.py          # Main metadata synchronization script
├── smart-playlists.py                  # Smart playlist creation script
├── app.py                              # Database management utilities
├── rekordbox_backup.py                 # Backup and restore functionality
├── playlist-data/                      # JSON configuration files
│   ├── house.json
│   ├── dnb.json
│   ├── dub.json
│   └── ...
├── examples/                           # Example files
│   └── example-smart-playlist.xml
├── pyproject.toml                      # Project configuration
└── README.md                           # This file
```

## 🔧 Configuration

### Environment Variables

You can set these environment variables to customize behavior:

```bash
export REKORDBOX_COLLECTION_PATH="/path/to/your/music"
export REKORDBOX_BACKUP_PATH="/path/to/backups"
export REKORDBOX_DRY_RUN="true"  # Set to "false" for live mode
```

### Configuration File

Create a `config.json` file to customize settings:

```json
{
  "collection_path": "/Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Collection/",
  "dry_run": true,
  "skip_backup": false,
  "audio_extensions": [".mp3", ".wav", ".flac", ".aiff", ".m4a", ".aac", ".ogg"],
  "progress_interval": 10
}
```

Then use it with:
```bash
python fix_rekordbox_metadata.py --config config.json
```

## 🛡️ Safety Features

- **Automatic Backups**: Scripts create backups before making changes
- **Dry Run Mode**: Preview all changes before applying them
- **Interactive Mode**: Choose what to do for each file
- **Backup Validation**: Validates backup integrity after creation
- **Transaction Support**: Database operations are wrapped in transactions
- **Comprehensive Logging**: Detailed logging for troubleshooting

## 🚨 Important Notes

1. **Always close Rekordbox** before running any scripts
2. **Start with `--dry-run`** to preview changes
3. **Backups are automatically created** before making changes
4. **Test with a small subset** of files first
5. **Keep your Rekordbox database backed up** regularly

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly with `--dry-run`
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- [pyrekordbox](https://github.com/dylanljones/pyrekordbox) for Rekordbox database access
- Pioneer DJ for creating Rekordbox
- The DJ community for inspiration and feedback

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Use `--help` for command-specific help
3. Enable `--verbose` logging for detailed output
4. Use `--dry-run` to preview changes safely
5. Open an issue on GitHub with detailed error information