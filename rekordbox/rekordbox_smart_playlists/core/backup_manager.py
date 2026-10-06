"""
Backup and restore management for Rekordbox databases.

Provides comprehensive backup and restore functionality with proper error handling,
validation, and safety features.
"""

import shutil
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from dataclasses import dataclass

from ..utils.logging import (
    get_logger,
    log_success,
    log_error,
    log_exception,
    log_warning,
)
from ..utils.file_utils import (
    ensure_directory,
    temporary_directory,
)
from .config import Config

logger = get_logger(__name__)


class BackupError(Exception):
    """Base exception for backup operations."""

    pass


class BackupNotFoundError(BackupError):
    """Raised when backup file is not found."""

    pass


class BackupValidationError(BackupError):
    """Raised when backup validation fails."""

    pass


@dataclass
class BackupInfo:
    """Information about a backup file."""

    path: Path
    name: str
    size_bytes: int
    size_mb: float
    created: datetime
    created_str: str
    is_valid: Optional[bool] = None

    @classmethod
    def from_path(cls, backup_path: Path) -> "BackupInfo":
        """Create BackupInfo from file path."""
        stat = backup_path.stat()
        size_bytes = stat.st_size
        size_mb = size_bytes / (1024 * 1024)
        created = datetime.fromtimestamp(stat.st_mtime)

        return cls(
            path=backup_path,
            name=backup_path.name,
            size_bytes=size_bytes,
            size_mb=size_mb,
            created=created,
            created_str=created.strftime("%Y-%m-%d %H:%M:%S"),
        )


class BackupManager:
    """
    Manages backup and restore operations for Rekordbox databases.
    """

    def __init__(self, config: Config):
        """
        Initialize backup manager.

        Args:
            config: Configuration object with backup settings
        """
        self.config = config
        self.backup_base = Path(config.backup_base_path)
        self.pioneer_app_support = Path(config.pioneer_app_support)
        self.pioneer_library = Path(config.pioneer_library)

        # Ensure backup directory exists
        ensure_directory(self.backup_base)

    def create_backup(
        self, backup_name: Optional[str] = None, validate: bool = True
    ) -> Optional[str]:
        """
        Create a comprehensive backup of Rekordbox database and configuration.

        Args:
            backup_name: Optional custom name for backup
            validate: Whether to validate backup after creation

        Returns:
            Path to created backup file, or None if failed
        """
        try:
            # Generate backup name with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if backup_name is None:
                backup_name = f"rekordbox_backup_{timestamp}"
            else:
                # Clean backup name and add timestamp
                backup_name = backup_name.replace(".zip", "")
                backup_name = f"{backup_name}_{timestamp}"

            logger.info(f"Creating Rekordbox backup: {backup_name}")

            with temporary_directory(prefix="rekordbox_backup_") as temp_dir:
                # Create backup structure
                backup_success = self._create_backup_structure(temp_dir, backup_name)
                if not backup_success:
                    return None

                # Create compressed archive
                archive_path = self.backup_base / f"{backup_name}.zip"
                self._create_archive(temp_dir, archive_path)

                # Validate backup if requested
                if validate:
                    if not self.validate_backup(archive_path):
                        log_error(logger, f"Backup validation failed: {archive_path}")
                        archive_path.unlink()  # Remove invalid backup
                        return None

                # Log success
                size_mb = archive_path.stat().st_size / (1024 * 1024)
                log_success(logger, f"Backup created successfully: {archive_path}")
                logger.info(f"Backup size: {size_mb:.1f} MB")

                # Cleanup old backups if configured
                if self.config.max_backups > 0:
                    self._cleanup_old_backups()

                return str(archive_path)

        except Exception as e:
            log_exception(logger, e, "creating backup")
            return None

    def _create_backup_structure(self, temp_dir: Path, backup_name: str) -> bool:
        """
        Create backup directory structure with source files.

        Args:
            temp_dir: Temporary directory for backup
            backup_name: Name of backup for logging

        Returns:
            True if successful, False otherwise
        """
        try:
            backup_dir = temp_dir / f"{backup_name}_content"
            backup_dir.mkdir()

            # Backup Application Support directory
            if self.pioneer_app_support.exists():
                app_support_backup = backup_dir / "Application Support"
                logger.info("Backing up Application Support directory...")
                shutil.copytree(self.pioneer_app_support, app_support_backup)
                log_success(logger, "Application Support backed up")
            else:
                log_warning(
                    logger,
                    f"Application Support directory not found: {self.pioneer_app_support}",
                )

            # Backup Library directory
            if self.pioneer_library.exists():
                library_backup = backup_dir / "Library"
                logger.info("Backing up Library directory...")
                shutil.copytree(self.pioneer_library, library_backup)
                log_success(logger, "Library backed up")
            else:
                log_warning(logger, f"Library directory not found: {self.pioneer_library}")

            # Create backup metadata
            self._create_backup_metadata(backup_dir, backup_name)

            return True

        except Exception as e:
            log_exception(logger, e, "creating backup structure")
            return False

    def _create_backup_metadata(self, backup_dir: Path, backup_name: str) -> None:
        """
        Create metadata file for backup.

        Args:
            backup_dir: Backup directory
            backup_name: Name of backup
        """
        try:
            metadata = {
                "backup_name": backup_name,
                "created": datetime.now().isoformat(),
                "created_by": "rekordbox-smart-playlists",
                "version": "1.0.0",
                "source_paths": {
                    "pioneer_app_support": str(self.pioneer_app_support),
                    "pioneer_library": str(self.pioneer_library),
                },
                "config": {
                    "backup_base_path": str(self.backup_base),
                    "max_backups": self.config.max_backups,
                },
            }

            metadata_file = backup_dir / "backup_metadata.json"
            import json

            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

        except Exception as e:
            log_exception(logger, e, "creating backup metadata")

    def _create_archive(self, source_dir: Path, archive_path: Path) -> None:
        """
        Create compressed archive from source directory.

        Args:
            source_dir: Source directory to compress
            archive_path: Path for output archive
        """
        logger.info("Creating compressed archive...")
        shutil.make_archive(str(archive_path).replace(".zip", ""), "zip", source_dir)

    def _cleanup_old_backups(self) -> None:
        """Clean up old backups based on max_backups setting."""
        try:
            backups = self.list_backups()
            if len(backups) <= self.config.max_backups:
                return

            # Remove oldest backups
            backups_to_remove = backups[self.config.max_backups :]
            removed_count = 0

            for backup in backups_to_remove:
                try:
                    backup.path.unlink()
                    removed_count += 1
                    logger.debug(f"Removed old backup: {backup.name}")
                except Exception as e:
                    log_exception(logger, e, f"removing old backup {backup.name}")

            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} old backups")

        except Exception as e:
            log_exception(logger, e, "cleaning up old backups")

    def restore_backup(
        self, backup_path: Union[str, Path], create_safety_backup: bool = True
    ) -> bool:
        """
        Restore Rekordbox database from backup.

        Args:
            backup_path: Path to backup file
            create_safety_backup: Whether to create safety backup before restore

        Returns:
            True if restore was successful, False otherwise
        """
        backup_file = Path(backup_path)

        if not backup_file.exists():
            log_error(logger, f"Backup file not found: {backup_file}")
            return False

        logger.info(f"Restoring from backup: {backup_file.name}")

        try:
            # Validate backup first
            if not self.validate_backup(backup_file):
                log_error(logger, "Backup validation failed, aborting restore")
                return False

            # Create safety backup if requested
            if create_safety_backup:
                safety_backup = self._create_safety_backup()
                if safety_backup:
                    log_success(logger, f"Safety backup created: {safety_backup}")
                else:
                    log_warning(logger, "Failed to create safety backup, continuing anyway")

            # Extract and restore
            with temporary_directory(prefix="rekordbox_restore_") as temp_dir:
                self._extract_backup(backup_file, temp_dir)
                self._restore_from_extracted(temp_dir)

            log_success(logger, "Backup restore completed successfully")
            return True

        except Exception as e:
            log_exception(logger, e, "restoring backup")
            return False

    def _create_safety_backup(self) -> Optional[str]:
        """Create a safety backup before restore operation."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safety_name = f"safety_backup_before_restore_{timestamp}"
        return self.create_backup(safety_name, validate=False)

    def _extract_backup(self, backup_file: Path, extract_dir: Path) -> None:
        """
        Extract backup file to directory.

        Args:
            backup_file: Backup file to extract
            extract_dir: Directory to extract to
        """
        logger.info(f"Extracting backup to: {extract_dir}")

        with zipfile.ZipFile(backup_file, "r") as zip_ref:
            zip_ref.extractall(extract_dir)

    def _restore_from_extracted(self, extract_dir: Path) -> None:
        """
        Restore files from extracted backup directory.

        Args:
            extract_dir: Directory containing extracted backup
        """
        # Find backup content directory
        content_dirs = [d for d in extract_dir.iterdir() if d.is_dir() and "content" in d.name]
        if not content_dirs:
            raise BackupError("Backup content directory not found")

        backup_content = content_dirs[0]

        # Restore Application Support
        app_support_backup = backup_content / "Application Support"
        if app_support_backup.exists():
            logger.info("Restoring Application Support directory...")
            if self.pioneer_app_support.exists():
                shutil.rmtree(self.pioneer_app_support)
            shutil.copytree(app_support_backup, self.pioneer_app_support)
            log_success(logger, "Application Support restored")

        # Restore Library
        library_backup = backup_content / "Library"
        if library_backup.exists():
            logger.info("Restoring Library directory...")
            if self.pioneer_library.exists():
                shutil.rmtree(self.pioneer_library)
            shutil.copytree(library_backup, self.pioneer_library)
            log_success(logger, "Library restored")

    def validate_backup(self, backup_path: Union[str, Path]) -> bool:
        """
        Validate backup file integrity and contents.

        Args:
            backup_path: Path to backup file

        Returns:
            True if backup is valid, False otherwise
        """
        backup_file = Path(backup_path)

        if not backup_file.exists():
            log_error(logger, f"Backup file not found: {backup_file}")
            return False

        try:
            # Check if it's a valid zip file
            with zipfile.ZipFile(backup_file, "r") as zip_ref:
                # Test zip file integrity
                bad_files = zip_ref.testzip()
                if bad_files:
                    log_error(logger, f"Corrupted files in backup: {bad_files}")
                    return False

                # Check for required directories
                file_list = zip_ref.namelist()
                has_app_support = any("Application Support" in name for name in file_list)
                has_library = any("Library" in name for name in file_list)

                if not (has_app_support or has_library):
                    log_error(logger, "Backup missing required directories")
                    return False

                # Test extraction of a few files
                test_files = [f for f in file_list if not f.endswith("/")][:5]
                for test_file in test_files:
                    try:
                        zip_ref.read(test_file)
                    except Exception as e:
                        log_error(logger, f"Failed to read {test_file}: {e}")
                        return False

            logger.debug(f"Backup validation passed: {backup_file}")
            return True

        except zipfile.BadZipFile:
            log_error(logger, f"Invalid zip file: {backup_file}")
            return False
        except Exception as e:
            log_exception(logger, e, f"validating backup {backup_file}")
            return False

    def list_backups(self) -> List[BackupInfo]:
        """
        List all available backups.

        Returns:
            List of BackupInfo objects, sorted by creation time (newest first)
        """
        if not self.backup_base.exists():
            return []

        # Look for both standard and custom backup names
        backup_files = list(self.backup_base.glob("rekordbox_backup_*.zip"))
        backup_files.extend(self.backup_base.glob("*backup*.zip"))
        backup_files.extend(self.backup_base.glob("before_*.zip"))
        backup_files.extend(self.backup_base.glob("safety_*.zip"))

        # Remove duplicates while preserving order
        backup_files = list(dict.fromkeys(backup_files))
        backups = []

        for backup_file in backup_files:
            try:
                backup_info = BackupInfo.from_path(backup_file)
                backups.append(backup_info)
            except Exception as e:
                log_exception(logger, e, f"getting info for backup {backup_file.name}")

        # Sort by creation time, newest first
        backups.sort(key=lambda x: x.created, reverse=True)
        return backups

    def get_backup_info(self, backup_path: Union[str, Path]) -> Optional[BackupInfo]:
        """
        Get detailed information about a specific backup.

        Args:
            backup_path: Path to backup file

        Returns:
            BackupInfo object or None if file doesn't exist
        """
        backup_file = Path(backup_path)
        if not backup_file.exists():
            return None

        try:
            backup_info = BackupInfo.from_path(backup_file)
            backup_info.is_valid = self.validate_backup(backup_file)
            return backup_info
        except Exception as e:
            log_exception(logger, e, f"getting backup info for {backup_file}")
            return None

    def delete_backup(self, backup_path: Union[str, Path]) -> bool:
        """
        Delete a backup file.

        Args:
            backup_path: Path to backup file to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        backup_file = Path(backup_path)

        if not backup_file.exists():
            log_error(logger, f"Backup file not found: {backup_file}")
            return False

        try:
            backup_file.unlink()
            log_success(logger, f"Deleted backup: {backup_file.name}")
            return True
        except Exception as e:
            log_exception(logger, e, f"deleting backup {backup_file}")
            return False

    def get_backup_summary(self) -> Dict[str, Any]:
        """
        Get summary of all backups.

        Returns:
            Dictionary with backup summary information
        """
        backups = self.list_backups()

        if not backups:
            return {
                "total_backups": 0,
                "total_size_mb": 0,
                "oldest_backup": None,
                "newest_backup": None,
                "backups": [],
            }

        total_size_mb = sum(backup.size_mb for backup in backups)

        return {
            "total_backups": len(backups),
            "total_size_mb": total_size_mb,
            "oldest_backup": backups[-1] if backups else None,
            "newest_backup": backups[0] if backups else None,
            "backups": backups,
        }

    def print_backup_summary(self) -> None:
        """Print formatted backup summary to console."""
        summary = self.get_backup_summary()

        print("\nRekordbox Backup Summary")
        print("=" * 50)
        print(f"Total backups: {summary['total_backups']}")
        print(f"Total size: {summary['total_size_mb']:.1f} MB")

        if summary["newest_backup"]:
            print(f"Newest backup: {summary['newest_backup'].created_str}")

        if summary["oldest_backup"]:
            print(f"Oldest backup: {summary['oldest_backup'].created_str}")

        if summary["backups"]:
            print(f"\nRecent backups:")
            for i, backup in enumerate(summary["backups"][:5], 1):
                print(f"  {i}. {backup.name} ({backup.size_mb:.1f} MB) - {backup.created_str}")


# Convenience functions for backward compatibility
def create_backup(
    config: Optional[Config] = None, backup_name: Optional[str] = None
) -> Optional[str]:
    """Create a backup using default configuration."""
    if config is None:
        config = Config()

    manager = BackupManager(config)
    return manager.create_backup(backup_name)


def restore_backup(backup_path: str, config: Optional[Config] = None) -> bool:
    """Restore from backup using default configuration."""
    if config is None:
        config = Config()

    manager = BackupManager(config)
    return manager.restore_backup(backup_path)


def list_backups(config: Optional[Config] = None) -> List[BackupInfo]:
    """List backups using default configuration."""
    if config is None:
        config = Config()

    manager = BackupManager(config)
    return manager.list_backups()
