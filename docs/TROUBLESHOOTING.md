# TuneWrangler Troubleshooting Guide

This guide helps you diagnose and resolve common issues with TuneWrangler.

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Common Issues](#common-issues)
3. [Error Messages](#error-messages)
4. [Performance Issues](#performance-issues)
5. [Configuration Problems](#configuration-problems)
6. [File Processing Issues](#file-processing-issues)
7. [Log Analysis](#log-analysis)
8. [Getting Help](#getting-help)

## Quick Diagnostics

### Basic Health Check

Run these commands to quickly diagnose common issues:

```bash
# 1. Check TuneWrangler installation
./tunewrangler --version

# 2. Validate configuration
./tunewrangler validate

# 3. Check recent logs
./tunewrangler logs --tail

# 4. Test with verbose mode
./tunewrangler --verbose validate
```

### System Requirements Check

```bash
# Check Deno version
deno --version

# Check available disk space
df -h

# Check file permissions
ls -la /path/to/music/directory

# Check system resources
top -l 1 | head -10
```

## Common Issues

### Issue: "Command not found: tunewrangler"

**Symptoms:**
```bash
$ tunewrangler --version
zsh: command not found: tunewrangler
```

**Causes:**
- TuneWrangler not installed
- Installation script not run
- PATH not updated

**Solutions:**

1. **Reinstall TuneWrangler:**
   ```bash
   cd /path/to/TuneWrangler
   chmod +x install.sh
   ./install.sh
   ```

2. **Manual installation:**
   ```bash
   # Add to your shell profile (.bashrc, .zshrc, etc.)
   export PATH="/path/to/TuneWrangler:$PATH"
   
   # Reload shell
   source ~/.zshrc  # or ~/.bashrc
   ```

3. **Use direct path:**
   ```bash
   ./tunewrangler --version
   ```

### Issue: Configuration Validation Fails

**Symptoms:**
```bash
$ ./tunewrangler validate
❌ Configuration validation failed:
  - Path 'music' does not exist: /Users/username/Music/
```

**Solutions:**

1. **Check if directories exist:**
   ```bash
   ls -la /Users/username/Music/
   ```

2. **Create missing directories:**
   ```bash
   mkdir -p /Users/username/Music/
   mkdir -p /Users/username/Downloads/
   mkdir -p /Users/username/DJ/Collection/
   ```

3. **Set environment variables:**
   ```bash
   export TUNEWRANGLER_MUSIC="/Users/username/Music/"
   export TUNEWRANGLER_DOWNLOADS="/Users/username/Downloads/"
   export TUNEWRANGLER_DJ_MUSIC="/Users/username/DJ/Collection/"
   ```

4. **Use custom paths:**
   ```bash
   # Create .env file
   echo "TUNEWRANGLER_MUSIC=/custom/music/path" > .env
   echo "TUNEWRANGLER_DOWNLOADS=/custom/downloads/path" >> .env
   ```

### Issue: Permission Denied Errors

**Symptoms:**
```bash
❌ Error: Permission denied when accessing /path/to/music
```

**Solutions:**

1. **Check current permissions:**
   ```bash
   ls -la /path/to/music
   ```

2. **Fix file permissions:**
   ```bash
   # Fix directory permissions
   chmod +rwx /path/to/music
   
   # Fix file permissions
   chmod +rw /path/to/music/*
   
   # Recursive fix
   chmod -R +rw /path/to/music
   ```

3. **Check ownership:**
   ```bash
   # Check who owns the files
   ls -la /path/to/music
   
   # Change ownership if needed
   sudo chown -R $USER:$USER /path/to/music
   ```

4. **SELinux/AppArmor (Linux):**
   ```bash
   # Check SELinux status
   sestatus
   
   # Temporarily disable SELinux
   sudo setenforce 0
   ```

### Issue: Unsupported File Format

**Symptoms:**
```bash
❌ Error: Unsupported audio format: .wma
```

**Solutions:**

1. **Check supported formats:**
   ```bash
   ./tunewrangler convert --help
   ```

2. **Convert unsupported formats first:**
   ```bash
   # Use FFmpeg to convert WMA to MP3
   ffmpeg -i "song.wma" "song.mp3"
   ```

3. **Install additional codecs:**
   ```bash
   # macOS
   brew install ffmpeg
   
   # Ubuntu/Debian
   sudo apt-get install ffmpeg
   
   # Windows
   # Download from https://ffmpeg.org/download.html
   ```

## Error Messages

### Configuration Errors

#### "Path does not exist"
```bash
❌ Error: Path 'music' does not exist: /Users/username/Music/
```

**Solution:**
```bash
# Create the directory
mkdir -p /Users/username/Music/

# Or set a different path
export TUNEWRANGLER_MUSIC="/existing/path/to/music/"
```

#### "Permission denied"
```bash
❌ Error: Permission denied when accessing /path/to/music
```

**Solution:**
```bash
# Fix permissions
chmod +rwx /path/to/music
chmod +rw /path/to/music/*

# Check ownership
ls -la /path/to/music
sudo chown -R $USER:$USER /path/to/music
```

### File Processing Errors

#### "File not found"
```bash
❌ Error: File not found: /path/to/file.mp3
```

**Solution:**
```bash
# Check if file exists
ls -la /path/to/file.mp3

# Check file path
realpath /path/to/file.mp3

# Use absolute path
./tunewrangler rename-music --input "/absolute/path/to/music"
```

#### "Invalid audio format"
```bash
❌ Error: Invalid audio format: .xyz
```

**Solution:**
```bash
# Check file extension
file /path/to/file.xyz

# Convert to supported format
ffmpeg -i "file.xyz" "file.mp3"

# Check supported formats
./tunewrangler convert --help
```

### Network Errors

#### "Connection timeout"
```bash
❌ Error: Network timeout when accessing https://api.example.com
```

**Solution:**
```bash
# Check internet connection
ping google.com

# Check DNS
nslookup api.example.com

# Use different network
# Try again later
```

#### "Authentication failed"
```bash
❌ Error: Authentication failed for YouTube API
```

**Solution:**
```bash
# Check API credentials
echo $YOUTUBE_API_KEY

# Set API credentials
export YOUTUBE_API_KEY="your-api-key"

# Verify credentials
curl -H "Authorization: Bearer $YOUTUBE_API_KEY" \
  "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
```

## Performance Issues

### Slow Processing

**Symptoms:**
- File processing takes a very long time
- System becomes unresponsive
- High CPU/memory usage

**Solutions:**

1. **Process in smaller batches:**
   ```bash
   # Instead of processing entire library
   ./tunewrangler rename-music --input "/large/music/library"
   
   # Process in smaller batches
   for dir in /large/music/library/*; do
     ./tunewrangler rename-music --input "$dir" --output "/output"
   done
   ```

2. **Use SSD storage:**
   ```bash
   # Move processing to SSD
   ./tunewrangler rename-music \
     --input "/hdd/music" \
     --output "/ssd/processed"
   ```

3. **Limit concurrent operations:**
   ```bash
   # Process one directory at a time
   ./tunewrangler rename-music --input "/music1" --output "/output"
   ./tunewrangler rename-music --input "/music2" --output "/output"
   ```

4. **Monitor system resources:**
   ```bash
   # Monitor CPU and memory
   top -l 1 | head -10
   
   # Monitor disk I/O
   iostat 1
   ```

### High Memory Usage

**Symptoms:**
- System becomes slow
- Out of memory errors
- Process killed by system

**Solutions:**

1. **Reduce batch size:**
   ```bash
   # Process fewer files at once
   ./tunewrangler rename-music \
     --input "/music" \
     --output "/output" \
     --batch-size 10
   ```

2. **Use streaming processing:**
   ```bash
   # Process files one at a time
   find /music -name "*.mp3" | while read file; do
     ./tunewrangler rename-music --input "$file" --output "/output"
   done
   ```

3. **Monitor memory usage:**
   ```bash
   # Check memory usage
   ps aux | grep tunewrangler
   
   # Monitor in real-time
   top -pid $(pgrep tunewrangler)
   ```

## Configuration Problems

### Environment Variables Not Set

**Symptoms:**
```bash
$ echo $TUNEWRANGLER_MUSIC
# Empty output
```

**Solutions:**

1. **Set environment variables:**
   ```bash
   # Set in current session
   export TUNEWRANGLER_MUSIC="/Users/username/Music/"
   export TUNEWRANGLER_DOWNLOADS="/Users/username/Downloads/"
   
   # Add to shell profile
   echo 'export TUNEWRANGLER_MUSIC="/Users/username/Music/"' >> ~/.zshrc
   echo 'export TUNEWRANGLER_DOWNLOADS="/Users/username/Downloads/"' >> ~/.zshrc
   source ~/.zshrc
   ```

2. **Create .env file:**
   ```bash
   # Create .env file in project directory
   cat > .env << EOF
   TUNEWRANGLER_MUSIC=/Users/username/Music/
   TUNEWRANGLER_DOWNLOADS=/Users/username/Downloads/
   TUNEWRANGLER_DJ_MUSIC=/Users/username/DJ/Collection/
   EOF
   ```

3. **Use absolute paths:**
   ```bash
   # Use absolute paths in commands
   ./tunewrangler rename-music \
     --input "/Users/username/Downloads/Music" \
     --output "/Users/username/Music/Organized"
   ```

### Platform-Specific Issues

#### macOS Issues

**Gatekeeper blocking execution:**
```bash
# Remove quarantine attribute
xattr -d com.apple.quarantine /path/to/tunewrangler

# Or allow in System Preferences
# System Preferences > Security & Privacy > General
```

**Permission issues with external drives:**
```bash
# Check if drive is mounted with correct permissions
mount | grep /Volumes

# Remount with correct permissions
sudo mount -o rw,user /dev/disk2s1 /Volumes/Music
```

#### Linux Issues

**SELinux blocking access:**
```bash
# Check SELinux status
sestatus

# Temporarily disable
sudo setenforce 0

# Or configure SELinux policies
sudo setsebool -P httpd_can_network_connect 1
```

**AppArmor restrictions:**
```bash
# Check AppArmor status
sudo aa-status

# Disable for specific profile
sudo aa-disable tunewrangler
```

#### Windows Issues

**Path length limitations:**
```bash
# Use shorter paths
./tunewrangler rename-music --input "C:\music" --output "C:\out"

# Enable long path support
# Registry: HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1
```

**Antivirus interference:**
```bash
# Add TuneWrangler to antivirus exclusions
# Check antivirus logs for blocked operations
```

## File Processing Issues

### Corrupted Files

**Symptoms:**
```bash
❌ Error: Failed to read audio file: /path/to/corrupted.mp3
```

**Solutions:**

1. **Check file integrity:**
   ```bash
   # Check if file is readable
   file /path/to/corrupted.mp3
   
   # Try to play with ffplay
   ffplay /path/to/corrupted.mp3
   
   # Check file size
   ls -la /path/to/corrupted.mp3
   ```

2. **Attempt recovery:**
   ```bash
   # Try to repair with FFmpeg
   ffmpeg -i /path/to/corrupted.mp3 -c copy /path/to/repaired.mp3
   
   # Or re-encode
   ffmpeg -i /path/to/corrupted.mp3 /path/to/repaired.mp3
   ```

3. **Skip corrupted files:**
   ```bash
   # Use --skip-corrupted flag if available
   ./tunewrangler rename-music --input "/music" --skip-corrupted
   ```

### Duplicate Files

**Symptoms:**
```bash
⚠️  Warning: Duplicate file found: song_copy.mp3 (original: song.mp3)
```

**Solutions:**

1. **Review duplicates:**
   ```bash
   # Check file differences
   diff song.mp3 song_copy.mp3
   
   # Compare file sizes
   ls -la song*.mp3
   ```

2. **Handle duplicates:**
   ```bash
   # Use --handle-duplicates flag
   ./tunewrangler rename-music --input "/music" --handle-duplicates skip
   
   # Or manually remove
   rm song_copy.mp3
   ```

3. **Prevent duplicates:**
   ```bash
   # Use --check-duplicates flag
   ./tunewrangler rename-music --input "/music" --check-duplicates
   ```

### Metadata Issues

**Symptoms:**
```bash
❌ Error: Failed to read metadata from /path/to/file.mp3
```

**Solutions:**

1. **Check metadata:**
   ```bash
   # Use ffprobe to check metadata
   ffprobe /path/to/file.mp3
   
   # Use exiftool if available
   exiftool /path/to/file.mp3
   ```

2. **Repair metadata:**
   ```bash
   # Use FFmpeg to rewrite metadata
   ffmpeg -i /path/to/file.mp3 -c copy -metadata title="Song Title" /path/to/fixed.mp3
   ```

3. **Skip metadata processing:**
   ```bash
   # Use --skip-metadata flag
   ./tunewrangler rename-music --input "/music" --skip-metadata
   ```

## Log Analysis

### Understanding Log Messages

**Log Levels:**
- `DEBUG`: Detailed debugging information
- `INFO`: General information about operations
- `WARN`: Warning messages for potential issues
- `ERROR`: Error messages for recoverable errors
- `FATAL`: Critical errors that may cause termination

**Common Log Patterns:**

1. **Operation Start/End:**
   ```
   [timestamp] INFO: 🚀 Starting operation: rename-music
   [timestamp] INFO: ✅ Completed operation: rename-music
   ```

2. **File Processing:**
   ```
   [timestamp] DEBUG: 📁 Processing file: song.mp3
   [timestamp] INFO: ✅ Processed file: song.mp3 → song_renamed.mp3
   ```

3. **Errors:**
   ```
   [timestamp] ERROR: ❌ Error processing file: song.mp3
   [timestamp] ERROR: Error: Permission denied
   ```

### Log Analysis Commands

```bash
# View recent logs
./tunewrangler logs --tail

# Search for errors
./tunewrangler logs --file tunewrangler-2025-07-18.log | grep ERROR

# Count errors
./tunewrangler logs --file tunewrangler-2025-07-18.log | grep -c ERROR

# Find specific operations
./tunewrangler logs --file tunewrangler-2025-07-18.log | grep "rename-music"

# Analyze performance
./tunewrangler logs --file tunewrangler-2025-07-18.log | grep "Completed operation"
```

### Debug Mode

```bash
# Enable debug logging
./tunewrangler --verbose <command>

# Check debug logs
./tunewrangler logs --tail | grep DEBUG

# Export logs for analysis
./tunewrangler logs --file tunewrangler-2025-07-18.log > analysis.log
```

## Getting Help

### Self-Diagnosis Steps

1. **Check the basics:**
   ```bash
   ./tunewrangler --version
   ./tunewrangler validate
   ./tunewrangler logs --tail
   ```

2. **Enable verbose mode:**
   ```bash
   ./tunewrangler --verbose <command>
   ```

3. **Check system resources:**
   ```bash
   df -h  # Disk space
   free -h  # Memory
   top -l 1 | head -10  # CPU
   ```

4. **Test with minimal setup:**
   ```bash
   # Test with single file
   ./tunewrangler rename-music --input "/single/file.mp3" --output "/test"
   ```

### Collecting Information for Support

When seeking help, collect this information:

```bash
# System information
uname -a
deno --version
./tunewrangler --version

# Configuration
./tunewrangler validate

# Recent logs
./tunewrangler logs --tail

# Error details
./tunewrangler --verbose <failing-command> 2>&1

# File permissions
ls -la /path/to/problematic/directory

# System resources
df -h
free -h
```

### Where to Get Help

1. **Documentation:**
   - [User Guide](USER_GUIDE.md)
   - [API Reference](API_REFERENCE.md)
   - [Configuration Guide](CONFIGURATION.md)

2. **Community:**
   - [GitHub Issues](https://github.com/yourusername/TuneWrangler/issues)
   - [GitHub Discussions](https://github.com/yourusername/TuneWrangler/discussions)

3. **Search existing issues:**
   - Check if your issue has already been reported
   - Look for similar problems and solutions

### Reporting Issues

When reporting an issue, include:

1. **Environment details:**
   - Operating system and version
   - Deno version
   - TuneWrangler version

2. **Steps to reproduce:**
   - Exact commands run
   - Input files/directories
   - Expected vs. actual behavior

3. **Error information:**
   - Full error messages
   - Log output
   - Verbose mode output

4. **System information:**
   - Available disk space
   - Memory usage
   - File permissions

---

**Still having trouble?** Check the [User Guide](USER_GUIDE.md) for more detailed instructions or open an issue on GitHub. 