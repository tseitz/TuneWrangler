"""
Rekordbox Smart Playlists

A tool for managing Rekordbox smart playlists from JSON configuration files.
Provides backup and restore capabilities.
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .core.backup_manager import BackupManager
from .core.database import RekordboxDatabase
from .core.playlist_manager import PlaylistManager

__all__ = [
    "RekordboxDatabase",
    "PlaylistManager",
    "BackupManager",
]
