#!/bin/bash
# Daily Music Processing Workflow
# This script automates the daily processing of new music downloads

set -e  # Exit on any error

# Configuration
MUSIC_DOWNLOADS="/Users/username/Downloads/Music"
MUSIC_ORGANIZED="/Users/username/Music/Organized"
MUSIC_BACKUP="/Users/username/Music/Backup"
LOG_FILE="/Users/username/Music/processing.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# Check if TuneWrangler is available
if ! command -v tunewrangler &> /dev/null; then
    error "TuneWrangler not found. Please install it first."
    exit 1
fi

# Validate TuneWrangler configuration
log "Validating TuneWrangler configuration..."
if ! tunewrangler validate; then
    error "TuneWrangler configuration validation failed"
    exit 1
fi
success "Configuration validated successfully"

# Check if there are new downloads
if [ ! -d "$MUSIC_DOWNLOADS" ] || [ -z "$(ls -A "$MUSIC_DOWNLOADS" 2>/dev/null)" ]; then
    log "No new music downloads found"
    exit 0
fi

# Create backup directory with timestamp
BACKUP_DIR="$MUSIC_BACKUP/$(date +%Y%m%d_%H%M%S)"
log "Creating backup at: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Backup original files
log "Backing up original files..."
cp -r "$MUSIC_DOWNLOADS"/* "$BACKUP_DIR/"
success "Backup completed"

# Count files to process
FILE_COUNT=$(find "$MUSIC_DOWNLOADS" -type f \( -name "*.mp3" -o -name "*.flac" -o -name "*.m4a" -o -name "*.aac" \) | wc -l)
log "Found $FILE_COUNT music files to process"

if [ "$FILE_COUNT" -eq 0 ]; then
    warning "No music files found in downloads directory"
    exit 0
fi

# Process music files
log "Starting music file processing..."
if tunewrangler rename-music --input "$MUSIC_DOWNLOADS" --output "$MUSIC_ORGANIZED"; then
    success "Music files processed successfully"
else
    error "Music file processing failed"
    exit 1
fi

# Convert FLAC files to MP3 (if any)
FLAC_COUNT=$(find "$MUSIC_ORGANIZED" -name "*.flac" | wc -l)
if [ "$FLAC_COUNT" -gt 0 ]; then
    log "Converting $FLAC_COUNT FLAC files to MP3..."
    if tunewrangler convert --input "$MUSIC_ORGANIZED" --output "$MUSIC_ORGANIZED" --format mp3 --quality 320; then
        success "FLAC to MP3 conversion completed"
    else
        warning "FLAC to MP3 conversion failed"
    fi
fi

# Clean up downloads directory
log "Cleaning up downloads directory..."
rm -rf "$MUSIC_DOWNLOADS"/*
success "Downloads directory cleaned"

# Generate processing report
log "Generating processing report..."
echo "=== Daily Music Processing Report ===" >> "$LOG_FILE"
echo "Date: $(date)" >> "$LOG_FILE"
echo "Files processed: $FILE_COUNT" >> "$LOG_FILE"
echo "FLAC files converted: $FLAC_COUNT" >> "$LOG_FILE"
echo "Backup location: $BACKUP_DIR" >> "$LOG_FILE"
echo "=====================================" >> "$LOG_FILE"

# Show recent logs
log "Recent TuneWrangler logs:"
tunewrangler logs --tail

success "Daily music processing completed successfully!"
log "Report saved to: $LOG_FILE" 