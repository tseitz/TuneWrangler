"""
Rekordbox Backup and Recovery

This module provides comprehensive backup and restore functionality for Rekordbox databases.
It handles backing up all necessary files and provides safe restore operations.
"""

import shutil
import datetime
import zipfile
from pathlib import Path
from typing import Optional, List
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RekordboxBackup:
    """Handles backup and restore operations for Rekordbox databases"""

    def __init__(self, backup_base_path: Optional[str] = None):
        """
        Initialize the backup handler

        Args:
            backup_base_path: Base path for storing backups. If None, uses default location.
        """
        if backup_base_path is None:
            self.backup_base = Path(
                "/Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Rekordbox DB Backup"
            )
        else:
            self.backup_base = Path(backup_base_path)

        # Define source directories
        self.pioneer_app_support = Path(
            "/Users/tseitz/Library/Application Support/Pioneer"
        )
        self.pioneer_library = Path("/Users/tseitz/Library/Pioneer")

        # Ensure backup directory exists
        self.backup_base.mkdir(parents=True, exist_ok=True)

    def create_backup(self, backup_name: Optional[str] = None) -> Optional[str]:
        """
        Create a comprehensive backup of the Rekordbox database and configuration files.

        Args:
            backup_name: Optional custom name for the backup. If None, uses timestamp.

        Returns:
            Path to the created backup file, or None if backup failed.
        """
        try:
            # Generate backup name
            if backup_name is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"rekordbox_backup_{timestamp}"
            else:
                # Ensure backup name doesn't have .zip extension
                backup_name = backup_name.replace(".zip", "")

            # Create temporary backup directory
            backup_dir = self.backup_base / f"{backup_name}_temp"
            backup_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Starting Rekordbox backup: {backup_name}")
            logger.info(f"Backup location: {backup_dir}")

            # Backup Application Support directory (contains main database)
            if self.pioneer_app_support.exists():
                app_support_backup = backup_dir / "Application Support"
                logger.info("Backing up Application Support directory...")
                shutil.copytree(self.pioneer_app_support, app_support_backup)
                logger.info("✓ Application Support backed up")
            else:
                logger.warning(
                    f"Application Support directory not found: {self.pioneer_app_support}"
                )

            # Backup Library directory (contains additional config)
            if self.pioneer_library.exists():
                library_backup = backup_dir / "Library"
                logger.info("Backing up Library directory...")
                shutil.copytree(self.pioneer_library, library_backup)
                logger.info("✓ Library backed up")
            else:
                logger.warning(f"Library directory not found: {self.pioneer_library}")

            # Create compressed archive
            archive_path = self.backup_base / f"{backup_name}.zip"
            logger.info("Creating compressed archive...")
            shutil.make_archive(
                str(archive_path).replace(".zip", ""), "zip", backup_dir
            )
            logger.info(f"✓ Compressed archive created: {archive_path}")

            # Clean up uncompressed backup directory
            shutil.rmtree(backup_dir)
            logger.info("✓ Cleaned up temporary files")

            # Print backup summary
            size_mb = archive_path.stat().st_size / (1024 * 1024)
            logger.info("🎵 Rekordbox backup completed successfully!")
            logger.info(f"📁 Backup location: {archive_path}")
            logger.info(f"📊 Backup size: {size_mb:.1f} MB")

            return str(archive_path)

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            # Clean up partial backup if it exists
            if "backup_dir" in locals() and backup_dir.exists():
                shutil.rmtree(backup_dir)
            return None

    def restore_backup(
        self, backup_path: str, create_safety_backup: bool = True
    ) -> bool:
        """
        Restore Rekordbox database from backup.

        Args:
            backup_path: Path to the backup file to restore from
            create_safety_backup: Whether to create a backup of current state before restoring

        Returns:
            True if restore was successful, False otherwise
        """
        try:
            backup_file = Path(backup_path)
            if not backup_file.exists():
                logger.error(f"Backup file not found: {backup_path}")
                return False

            # Extract backup
            extract_dir = backup_file.parent / f"temp_restore_{backup_file.stem}"
            logger.info(f"Extracting backup to: {extract_dir}")

            with zipfile.ZipFile(backup_file, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find the backup directories
            app_support_backup = extract_dir / "Application Support"
            library_backup = extract_dir / "Library"

            # Create safety backup of current state if requested
            if create_safety_backup and (
                self.pioneer_app_support.exists() or self.pioneer_library.exists()
            ):
                logger.info("Creating safety backup of current state...")
                safety_backup = self.create_backup("safety_backup_before_restore")
                if safety_backup:
                    logger.info(f"✓ Safety backup created: {safety_backup}")
                else:
                    logger.warning(
                        "⚠️  Failed to create safety backup, but continuing with restore"
                    )

            # Restore Application Support
            if app_support_backup.exists():
                logger.info("Restoring Application Support directory...")

                # Remove current and restore
                if self.pioneer_app_support.exists():
                    shutil.rmtree(self.pioneer_app_support)
                shutil.copytree(app_support_backup, self.pioneer_app_support)
                logger.info("✓ Application Support restored")

            # Restore Library
            if library_backup.exists():
                logger.info("Restoring Library directory...")

                # Remove current and restore
                if self.pioneer_library.exists():
                    shutil.rmtree(self.pioneer_library)
                shutil.copytree(library_backup, self.pioneer_library)
                logger.info("✓ Library restored")

            # Clean up
            shutil.rmtree(extract_dir)
            logger.info("✓ Cleaned up temporary files")
            logger.info("🎵 Rekordbox restore completed successfully!")

            return True

        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False

    def list_backups(self) -> List[Path]:
        """
        List all available Rekordbox backups.

        Returns:
            List of backup file paths, sorted by modification time (newest first)
        """
        if not self.backup_base.exists():
            logger.info("No backup directory found")
            return []

        backups = list(self.backup_base.glob("rekordbox_backup_*.zip"))
        backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        if not backups:
            logger.info("No backups found")
            return []

        logger.info("Available Rekordbox backups:")
        logger.info("=" * 60)

        for i, backup in enumerate(backups, 1):
            size_mb = backup.stat().st_size / (1024 * 1024)
            mod_time = datetime.datetime.fromtimestamp(backup.stat().st_mtime)
            logger.info(f"{i:2d}. {backup.name}")
            logger.info(f"    Size: {size_mb:.1f} MB")
            logger.info(f"    Date: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("")

        return backups

    def delete_backup(self, backup_path: str) -> bool:
        """
        Delete a backup file.

        Args:
            backup_path: Path to the backup file to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            backup_file = Path(backup_path)
            if not backup_file.exists():
                logger.error(f"Backup file not found: {backup_path}")
                return False

            backup_file.unlink()
            logger.info(f"✓ Deleted backup: {backup_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete backup: {e}")
            return False


# Convenience functions for backward compatibility
def backup_rekordbox_db(backup_name: Optional[str] = None) -> Optional[str]:
    """Create a backup of the Rekordbox database"""
    backup_handler = RekordboxBackup()
    return backup_handler.create_backup(backup_name)


def restore_rekordbox_db(backup_path: str, create_safety_backup: bool = True) -> bool:
    """Restore Rekordbox database from backup"""
    backup_handler = RekordboxBackup()
    return backup_handler.restore_backup(backup_path, create_safety_backup)


def list_backups() -> List[Path]:
    """List all available Rekordbox backups"""
    backup_handler = RekordboxBackup()
    return backup_handler.list_backups()


if __name__ == "__main__":
    # Example usage
    backup_handler = RekordboxBackup()

    print("Rekordbox Backup Management")
    print("=" * 40)

    # List existing backups
    backups = backup_handler.list_backups()

    # Uncomment to create a new backup
    # backup_path = backup_handler.create_backup()

    # Uncomment to restore from a backup
    # restore_success = backup_handler.restore_backup("/path/to/backup.zip")
