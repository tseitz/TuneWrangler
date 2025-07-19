# TuneWrangler Examples

This directory contains example scripts, configurations, and workflows to help you get started with TuneWrangler.

## 📁 Contents

- **`daily-music-processing.sh`** - Automated daily music processing workflow
- **`dj-workflow.sh`** - DJ-specific music processing workflow
- **`env.example`** - Example environment configuration file

## 🚀 Quick Start

### 1. Environment Configuration

Copy the example environment file and customize it for your system:

```bash
# Copy the example configuration
cp examples/env.example .env

# Edit the configuration with your paths
nano .env
```

### 2. Make Scripts Executable

```bash
# Make example scripts executable
chmod +x examples/daily-music-processing.sh
chmod +x examples/dj-workflow.sh
```

### 3. Test Configuration

```bash
# Validate your configuration
./tunewrangler validate
```

## 📋 Example Scripts

### Daily Music Processing

The `daily-music-processing.sh` script automates the daily processing of new music downloads:

**Features:**

- Automatic backup of original files
- File renaming and organization
- FLAC to MP3 conversion
- Logging and reporting
- Cleanup of download directory

**Usage:**

```bash
# Run daily processing
./examples/daily-music-processing.sh

# Set up as a cron job (daily at 2 AM)
0 2 * * * /path/to/TuneWrangler/examples/daily-music-processing.sh
```

**Configuration:**
Edit the script to customize paths:

```bash
MUSIC_DOWNLOADS="/Users/username/Downloads/Music"
MUSIC_ORGANIZED="/Users/username/Music/Organized"
MUSIC_BACKUP="/Users/username/Music/Backup"
```

### DJ Workflow

The `dj-workflow.sh` script processes music specifically for DJ use:

**Features:**

- DJ-friendly file naming
- High-quality MP3 conversion (320kbps)
- Playlist processing
- BPM and key analysis preparation
- DJ software import preparation

**Usage:**

```bash
# Run DJ processing
./examples/dj-workflow.sh

# Set up as a cron job (weekly)
0 10 * * 0 /path/to/TuneWrangler/examples/dj-workflow.sh
```

**Configuration:**
Edit the script to customize DJ paths:

```bash
DJ_DOWNLOADS="/Users/username/Downloads/DJ"
DJ_COLLECTION="/Users/username/DJ/Collection"
DJ_PLAYLISTS="/Users/username/DJ/Playlists"
```

## ⚙️ Environment Configuration

### Basic Configuration

The `env.example` file shows how to configure TuneWrangler for different scenarios:

**Standard Setup:**

```bash
TUNEWRANGLER_MUSIC=/Users/username/Music/
TUNEWRANGLER_DOWNLOADS=/Users/username/Downloads/
TUNEWRANGLER_DJ_MUSIC=/Users/username/DJ/Collection/
```

**External Drive Setup:**

```bash
TUNEWRANGLER_MUSIC=/Volumes/ExternalDrive/Music/
TUNEWRANGLER_DJ_MUSIC=/Volumes/ExternalDrive/DJ/Collection/
```

**Network Storage Setup:**

```bash
TUNEWRANGLER_MUSIC=/mnt/nas/Music/
TUNEWRANGLER_DJ_MUSIC=/mnt/nas/DJ/Collection/
```

### Platform-Specific Examples

**macOS:**

```bash
TUNEWRANGLER_MUSIC=$HOME/Music/
TUNEWRANGLER_DOWNLOADS=$HOME/Downloads/
TUNEWRANGLER_DJ_MUSIC=$HOME/Documents/DJ/Collection/
```

**Linux:**

```bash
TUNEWRANGLER_MUSIC=$HOME/Music/
TUNEWRANGLER_DOWNLOADS=$HOME/Downloads/
TUNEWRANGLER_DJ_MUSIC=$HOME/DJ/Collection/
```

**Windows:**

```cmd
TUNEWRANGLER_MUSIC=%USERPROFILE%\Music\
TUNEWRANGLER_DOWNLOADS=%USERPROFILE%\Downloads\
TUNEWRANGLER_DJ_MUSIC=%USERPROFILE%\DJ\Collection\
```

## 🔧 Customization

### Modifying Scripts

1. **Update paths:** Change the directory paths at the top of each script
2. **Add features:** Extend scripts with additional processing steps
3. **Customize logging:** Modify the logging functions for your needs
4. **Add error handling:** Enhance error handling for your environment

### Example Customizations

**Add email notifications:**

```bash
# Add to script
send_notification() {
    echo "$1" | mail -s "TuneWrangler Processing" user@example.com
}

# Use in script
send_notification "Daily music processing completed successfully!"
```

**Add Slack notifications:**

```bash
# Add to script
send_slack_notification() {
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"$1\"}" \
        https://hooks.slack.com/services/YOUR/WEBHOOK/URL
}

# Use in script
send_slack_notification "DJ processing completed: $FILE_COUNT files"
```

**Add file validation:**

```bash
# Add to script
validate_audio_file() {
    local file="$1"
    if ! ffprobe -v quiet "$file"; then
        error "Invalid audio file: $file"
        return 1
    fi
    return 0
}

# Use in script
for file in "$DJ_DOWNLOADS"/*.mp3; do
    validate_audio_file "$file" || continue
done
```

## 📊 Monitoring and Logging

### Log Files

Both example scripts create detailed log files:

- **Daily processing:** `/Users/username/Music/processing.log`
- **DJ workflow:** `/Users/username/DJ/processing.log`

### Monitoring Commands

```bash
# Check recent processing logs
tail -f /Users/username/Music/processing.log

# Check TuneWrangler logs
./tunewrangler logs --tail

# Monitor disk space
df -h /Users/username/Music/

# Check file counts
find /Users/username/Music/Organized -name "*.mp3" | wc -l
```

### Performance Monitoring

```bash
# Monitor script execution time
time ./examples/daily-music-processing.sh

# Monitor system resources during processing
top -pid $(pgrep tunewrangler)

# Check for errors in logs
grep -i error /Users/username/Music/processing.log
```

## 🔄 Automation

### Cron Jobs

Set up automated processing with cron:

```bash
# Edit crontab
crontab -e

# Daily music processing at 2 AM
0 2 * * * /path/to/TuneWrangler/examples/daily-music-processing.sh

# Weekly DJ processing on Sunday at 10 AM
0 10 * * 0 /path/to/TuneWrangler/examples/dj-workflow.sh

# Monthly backup cleanup
0 3 1 * * find /Users/username/Music/Backup -mtime +30 -delete
```

### Launch Agents (macOS)

Create a Launch Agent for automatic execution:

```xml
<!-- ~/Library/LaunchAgents/com.tunewrangler.daily.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tunewrangler.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/TuneWrangler/examples/daily-music-processing.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
```

## 🛠️ Troubleshooting

### Common Issues

1. **Permission errors:** Ensure scripts are executable and directories are writable
2. **Path issues:** Verify all paths in scripts and configuration files
3. **Missing dependencies:** Ensure TuneWrangler and required tools are installed
4. **Disk space:** Monitor available disk space for processing and backups

### Debug Mode

Run scripts with debug output:

```bash
# Enable bash debug mode
bash -x ./examples/daily-music-processing.sh

# Enable verbose TuneWrangler mode
TUNEWRANGLER_VERBOSE=1 ./examples/daily-music-processing.sh
```

### Testing

Test scripts with a small dataset first:

```bash
# Create test directory
mkdir -p /tmp/tunewrangler-test

# Copy a few files for testing
cp /path/to/test/music/* /tmp/tunewrangler-test/

# Update script paths temporarily
MUSIC_DOWNLOADS="/tmp/tunewrangler-test"
./examples/daily-music-processing.sh
```

## 📚 Additional Resources

- [User Guide](../docs/USER_GUIDE.md) - Complete user documentation
- [API Reference](../docs/API_REFERENCE.md) - Developer documentation
- [Troubleshooting Guide](../docs/TROUBLESHOOTING.md) - Common issues and solutions

## 🤝 Contributing

Have a great example workflow? Share it with the community:

1. Create a new script in the `examples/` directory
2. Add documentation in this README
3. Submit a pull request

---

**Need help?** Check the [Troubleshooting Guide](../docs/TROUBLESHOOTING.md) or open an issue on GitHub.
