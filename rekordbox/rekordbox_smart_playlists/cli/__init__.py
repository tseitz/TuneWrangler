"""
Command-line interface modules.
"""

from .main import main
from .commands import PlaylistCommand, BackupCommand, MetadataCommand

__all__ = [
    "main",
    "PlaylistCommand",
    "BackupCommand",
    "MetadataCommand",
]
