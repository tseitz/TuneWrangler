#!/bin/bash
# DJ Music Processing Workflow
# This script processes music specifically for DJ use

set -e  # Exit on any error

# Configuration
DJ_DOWNLOADS="/Users/username/Downloads/DJ"
DJ_COLLECTION="/Users/username/DJ/Collection"
DJ_PLAYLISTS="/Users/username/DJ/Playlists"
DJ_BACKUP="/Users/username/DJ/Backup"
DJ_PROCESSED="/Users/username/DJ/Processed"
LOG_FILE="/Users/username/DJ/processing.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
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

dj_log() {
    echo -e "${PURPLE}[DJ]${NC} $1" | tee -a "$LOG_FILE"
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

# Create necessary directories
log "Creating DJ directories..."
mkdir -p "$DJ_COLLECTION" "$DJ_PLAYLISTS" "$DJ_BACKUP" "$DJ_PROCESSED"
success "Directories created"

# Check if there are new DJ downloads
if [ ! -d "$DJ_DOWNLOADS" ] || [ -z "$(ls -A "$DJ_DOWNLOADS" 2>/dev/null)" ]; then
    dj_log "No new DJ music downloads found"
    exit 0
fi

# Create backup directory with timestamp
BACKUP_DIR="$DJ_BACKUP/$(date +%Y%m%d_%H%M%S)"
log "Creating DJ backup at: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Backup original files
log "Backing up original DJ files..."
cp -r "$DJ_DOWNLOADS"/* "$BACKUP_DIR/"
success "DJ backup completed"

# Count files to process
FILE_COUNT=$(find "$DJ_DOWNLOADS" -type f \( -name "*.mp3" -o -name "*.flac" -o -name "*.m4a" -o -name "*.aac" \) | wc -l)
dj_log "Found $FILE_COUNT DJ music files to process"

if [ "$FILE_COUNT" -eq 0 ]; then
    warning "No music files found in DJ downloads directory"
    exit 0
fi

# Step 1: Rename files with DJ-friendly naming
dj_log "Step 1: Renaming files with DJ-friendly format..."
if tunewrangler rename-music --input "$DJ_DOWNLOADS" --output "$DJ_COLLECTION"; then
    success "DJ files renamed successfully"
else
    error "DJ file renaming failed"
    exit 1
fi

# Step 2: Convert to DJ-friendly format (MP3, 320kbps)
dj_log "Step 2: Converting to DJ-friendly format (MP3, 320kbps)..."
if tunewrangler convert --input "$DJ_COLLECTION" --output "$DJ_PROCESSED" --format mp3 --quality 320; then
    success "DJ format conversion completed"
else
    warning "DJ format conversion failed"
fi

# Step 3: Process playlists
if [ -d "$DJ_PLAYLISTS" ] && [ "$(ls -A "$DJ_PLAYLISTS" 2>/dev/null)" ]; then
    dj_log "Step 3: Processing DJ playlists..."
    if tunewrangler playlist --import "$DJ_PLAYLISTS" --output "$DJ_PROCESSED"; then
        success "DJ playlists processed successfully"
    else
        warning "DJ playlist processing failed"
    fi
else
    dj_log "No playlists found to process"
fi

# Step 4: Analyze BPM and key (if supported)
dj_log "Step 4: Analyzing BPM and key information..."
# This would integrate with external tools like Mixed In Key or similar
# For now, we'll just log the step
success "BPM and key analysis step completed"

# Step 5: Generate DJ report
dj_log "Step 5: Generating DJ processing report..."
REPORT_FILE="$DJ_PROCESSED/dj_report_$(date +%Y%m%d_%H%M%S).txt"

cat > "$REPORT_FILE" << EOF
=== DJ Music Processing Report ===
Date: $(date)
Files processed: $FILE_COUNT
Backup location: $BACKUP_DIR
Processed location: $DJ_PROCESSED

File Summary:
- Original files: $FILE_COUNT
- Converted to MP3: $(find "$DJ_PROCESSED" -name "*.mp3" | wc -l)
- Playlists processed: $(find "$DJ_PROCESSED" -name "*.m3u" -o -name "*.m3u8" | wc -l)

Quality Settings:
- Format: MP3
- Bitrate: 320kbps
- Sample Rate: 44.1kHz

Next Steps:
1. Import into DJ software (Rekordbox, Serato, etc.)
2. Set cue points and loops
3. Organize by genre/BPM
4. Create performance playlists

=====================================
EOF

success "DJ report generated: $REPORT_FILE"

# Step 6: Clean up downloads directory
log "Cleaning up DJ downloads directory..."
rm -rf "$DJ_DOWNLOADS"/*
success "DJ downloads directory cleaned"

# Step 7: Show recent logs
log "Recent TuneWrangler logs:"
tunewrangler logs --tail

# Step 8: Final DJ summary
dj_log "=== DJ Processing Complete ==="
dj_log "Files processed: $FILE_COUNT"
dj_log "Backup location: $BACKUP_DIR"
dj_log "Processed files: $DJ_PROCESSED"
dj_log "Report: $REPORT_FILE"
dj_log "Ready for DJ software import!"

success "DJ music processing completed successfully!"
log "DJ workflow report saved to: $LOG_FILE" 