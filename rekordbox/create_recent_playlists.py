#!/usr/bin/env python3
"""
Create Recent Additions Playlists

This script creates smart playlists for songs added to rekordbox within specific time periods:
- Last Month (1 month)
- Last 2 Months (2 months)
- Last 30 Days (30 days)
- Last 60 Days (60 days)

Usage:
    python3 create_recent_playlists.py

The script will:
1. Create a backup of your rekordbox database
2. Create the date-based smart playlists
3. Commit the changes

Note: This uses the recent-additions.json configuration file.
"""

import json
import sys
import os
import importlib.util

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import from smart-playlists.py (hyphenated filename)
spec = importlib.util.spec_from_file_location("smart_playlists", "smart-playlists.py")
smart_playlists = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smart_playlists)

add_data_to_playlist = smart_playlists.add_data_to_playlist
db = smart_playlists.db

from rekordbox_backup import backup_rekordbox_db


def create_recent_playlists():
    """Create date-based smart playlists for recent additions"""
    print("🎵 Creating Recent Additions Playlists...")
    print("=" * 50)

    # Create backup first
    print("📦 Creating backup...")
    backup_path = backup_rekordbox_db()
    if backup_path:
        print(f"✓ Backup created: {backup_path}")
    else:
        print("❌ Backup failed - aborting for safety")
        return

    # Load the recent additions playlist data
    try:
        with open("playlist-data/recent-additions.json", "r") as json_file:
            data = json.load(json_file)["data"]
    except FileNotFoundError:
        print("❌ recent-additions.json not found in playlist-data/")
        return
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing recent-additions.json: {e}")
        return

    print("🚀 Creating playlists...")

    # Create the playlists
    created = add_data_to_playlist(data, index=None)

    if created:
        print(f"✅ Created {len(created)} playlists:")
        for playlist_name in created:
            print(f"   - {playlist_name}")

        print("\n💾 Committing changes...")
        db.commit()
        print("✅ All changes committed successfully!")

        print("\n🎉 Recent additions playlists are now available in rekordbox!")
        print("These smart playlists will automatically update as you add new music.")
    else:
        print("⚠️  No playlists were created (they may already exist)")


if __name__ == "__main__":
    try:
        create_recent_playlists()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
