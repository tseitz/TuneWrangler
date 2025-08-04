"""
Rekordbox Utilities

This module provides utility functions for Rekordbox operations, including
backup management, database validation, and common operations.
"""

import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
from rekordbox_backup import RekordboxBackup

logger = logging.getLogger(__name__)


def get_backup_info(backup_path: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a backup file.

    Args:
        backup_path: Path to the backup file

    Returns:
        Dictionary with backup information, or None if file doesn't exist
    """
    backup_file = Path(backup_path)
    if not backup_file.exists():
        return None

    try:
        stat = backup_file.stat()
        size_mb = stat.st_size / (1024 * 1024)
        mod_time = datetime.datetime.fromtimestamp(stat.st_mtime)

        return {
            "path": str(backup_file),
            "name": backup_file.name,
            "size_mb": size_mb,
            "size_bytes": stat.st_size,
            "modified": mod_time,
            "modified_str": mod_time.strftime("%Y-%m-%d %H:%M:%S"),
            "exists": True,
        }
    except Exception as e:
        logger.error(f"Error getting backup info: {e}")
        return None


def find_latest_backup(backup_directory: Optional[str] = None) -> Optional[str]:
    """
    Find the most recent backup file.

    Args:
        backup_directory: Directory to search in. If None, uses default location.

    Returns:
        Path to the latest backup file, or None if no backups found
    """
    backup_handler = RekordboxBackup(backup_directory)
    backups = backup_handler.list_backups()

    if backups:
        return str(backups[0])  # First backup is the most recent
    return None


def cleanup_old_backups(
    keep_count: int = 5, backup_directory: Optional[str] = None
) -> int:
    """
    Clean up old backups, keeping only the most recent ones.

    Args:
        keep_count: Number of recent backups to keep
        backup_directory: Directory to search in. If None, uses default location.

    Returns:
        Number of backups deleted
    """
    backup_handler = RekordboxBackup(backup_directory)
    backups = backup_handler.list_backups()

    if len(backups) <= keep_count:
        logger.info(
            f"No cleanup needed. Found {len(backups)} backups, keeping {keep_count}"
        )
        return 0

    deleted_count = 0
    backups_to_delete = backups[keep_count:]  # Keep the most recent ones

    for backup in backups_to_delete:
        if backup_handler.delete_backup(str(backup)):
            deleted_count += 1

    logger.info(f"Cleaned up {deleted_count} old backups")
    return deleted_count


def validate_backup(backup_path: str) -> bool:
    """
    Validate that a backup file is complete and not corrupted.

    Args:
        backup_path: Path to the backup file to validate

    Returns:
        True if backup is valid, False otherwise
    """
    backup_file = Path(backup_path)
    if not backup_file.exists():
        logger.error(f"Backup file not found: {backup_path}")
        return False

    try:
        # Check if it's a valid zip file
        with open(backup_file, "rb") as f:
            # Check zip file magic number
            if f.read(4) != b"PK\x03\x04":
                logger.error(f"Invalid zip file: {backup_path}")
                return False

        # Try to read the zip file
        import zipfile

        with zipfile.ZipFile(backup_file, "r") as zip_ref:
            # Check for required directories
            file_list = zip_ref.namelist()
            has_app_support = any("Application Support" in name for name in file_list)
            has_library = any("Library" in name for name in file_list)

            if not has_app_support and not has_library:
                logger.error(
                    f"Backup appears to be missing required directories: {backup_path}"
                )
                return False

            # Test extraction of a few files
            test_files = file_list[:5]  # Test first 5 files
            for test_file in test_files:
                try:
                    zip_ref.read(test_file)
                except Exception as e:
                    logger.error(f"Failed to read file {test_file} from backup: {e}")
                    return False

        logger.info(f"✓ Backup validation passed: {backup_path}")
        return True

    except Exception as e:
        logger.error(f"Backup validation failed: {e}")
        return False


def create_backup_with_validation(
    backup_name: Optional[str] = None, backup_directory: Optional[str] = None
) -> Optional[str]:
    """
    Create a backup and validate it was created successfully.

    Args:
        backup_name: Optional custom name for the backup
        backup_directory: Directory to store backup in

    Returns:
        Path to the created backup file, or None if backup failed
    """
    backup_handler = RekordboxBackup(backup_directory)

    # Create backup
    backup_path = backup_handler.create_backup(backup_name)
    if not backup_path:
        logger.error("Failed to create backup")
        return None

    # Validate backup
    if validate_backup(backup_path):
        logger.info("✓ Backup created and validated successfully")
        return backup_path
    else:
        logger.error("❌ Backup validation failed")
        # Optionally delete the invalid backup
        backup_handler.delete_backup(backup_path)
        return None


def get_backup_summary(backup_directory: Optional[str] = None) -> Dict[str, Any]:
    """
    Get a summary of all backups.

    Args:
        backup_directory: Directory to search in. If None, uses default location.

    Returns:
        Dictionary with backup summary information
    """
    backup_handler = RekordboxBackup(backup_directory)
    backups = backup_handler.list_backups()

    if not backups:
        return {
            "total_backups": 0,
            "total_size_mb": 0,
            "oldest_backup": None,
            "newest_backup": None,
            "backups": [],
        }

    total_size = sum(backup.stat().st_size for backup in backups)
    total_size_mb = total_size / (1024 * 1024)

    # Get oldest and newest backups
    oldest_backup = min(backups, key=lambda x: x.stat().st_mtime)
    newest_backup = max(backups, key=lambda x: x.stat().st_mtime)

    backup_info_list = []
    for backup in backups:
        info = get_backup_info(str(backup))
        if info:
            backup_info_list.append(info)

    return {
        "total_backups": len(backups),
        "total_size_mb": total_size_mb,
        "oldest_backup": get_backup_info(str(oldest_backup)),
        "newest_backup": get_backup_info(str(newest_backup)),
        "backups": backup_info_list,
    }


def print_backup_summary(backup_directory: Optional[str] = None):
    """
    Print a formatted summary of all backups.

    Args:
        backup_directory: Directory to search in. If None, uses default location.
    """
    summary = get_backup_summary(backup_directory)

    print("Rekordbox Backup Summary")
    print("=" * 50)
    print(f"Total backups: {summary['total_backups']}")
    print(f"Total size: {summary['total_size_mb']:.1f} MB")

    if summary["newest_backup"]:
        print(f"Newest backup: {summary['newest_backup']['modified_str']}")

    if summary["oldest_backup"]:
        print(f"Oldest backup: {summary['oldest_backup']['modified_str']}")

    if summary["backups"]:
        print("\nRecent backups:")
        for i, backup in enumerate(summary["backups"][:5], 1):
            print(
                f"  {i}. {backup['name']} ({backup['size_mb']:.1f} MB) - {backup['modified_str']}"
            )


if __name__ == "__main__":
    # Example usage
    print("Rekordbox Utilities")
    print("=" * 30)

    # Print backup summary
    print_backup_summary()

    # Find latest backup
    latest = find_latest_backup()
    if latest:
        print(f"\nLatest backup: {latest}")

    # Validate latest backup
    if latest:
        is_valid = validate_backup(latest)
        print(f"Latest backup is valid: {is_valid}")

    # Cleanup old backups (uncomment to use)
    # deleted = cleanup_old_backups(keep_count=3)
    # print(f"Deleted {deleted} old backups")
