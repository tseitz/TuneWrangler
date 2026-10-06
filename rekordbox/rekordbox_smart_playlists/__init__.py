"""
Rekordbox Smart Playlists

A tool for managing Rekordbox smart playlists from JSON configuration files.
Provides backup, restore, and metadata synchronization capabilities.
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .core.database import RekordboxDatabase
from .core.playlist_manager import PlaylistManager
from .core.backup_manager import BackupManager
from .core.metadata_fixer import MetadataFixer

__all__ = [
    "RekordboxDatabase",
    "PlaylistManager",
    "BackupManager",
    "MetadataFixer",
]
