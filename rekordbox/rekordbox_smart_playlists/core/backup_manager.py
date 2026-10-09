"""
Backup and restore management for Rekordbox databases.

Provides comprehensive backup and restore functionality with proper error handling,
validation, and safety features.
"""

import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pyrekordbox.utils import get_rekordbox_agent_pid, get_rekordbox_pid

from ..utils.file_utils import (
    temporary_directory,
)
from ..utils.logging import (
    get_logger,
    log_error,
    log_exception,
    log_success,
    log_warning,
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


BACKUP_CREATED_BY = "rekordbox-smart-playlists"
# Snapshots taken before a tag batch; rotation never deletes them.
PINNED_BACKUP_NAME = "before_tag_apply"
MASTER_DB = "Library/rekordbox/master.db"


def _is_own_backup(path: Path) -> bool:
    """True only for zips this tool wrote; nothing else is ever listed, cleaned or deleted."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.endswith("_content/backup_metadata.json")]
            if not names:
                return False
            return json.loads(zf.read(names[0])).get("created_by") == BACKUP_CREATED_BY
    except (zipfile.BadZipFile, OSError, ValueError):
        return False


def assert_rekordbox_closed() -> None:
    """A copy of master.db taken while Rekordbox has it open can be inconsistent."""
    if get_rekordbox_pid() or get_rekordbox_agent_pid():
        raise BackupError("Rekordbox is running. Close it before backing up or restoring.")


def _log_leftover(function, path, exc) -> None:
    log_error(logger, f"Could not remove {path} ({exc}); delete it by hand.")


@dataclass
class BackupInfo:
    """Information about a backup file."""

    path: Path
    name: str
    size_bytes: int
    size_mb: float
    created: datetime
    created_str: str
    is_valid: bool | None = None

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
        self.backup_base = config.require_backup_dir()
        self.pioneer_app_support = Path(config.pioneer_app_support)
        self.pioneer_library = Path(config.pioneer_library)

    def create_backup(
        self, backup_name: str | None = None, validate: bool = True, cleanup: bool = True
    ) -> str | None:
        """
        Create a comprehensive backup of Rekordbox database and configuration.

        Args:
            backup_name: Optional custom name for backup
            validate: Whether to validate backup after creation

        Returns:
            Path to created backup file, or None if failed
        """
        partial_path: Path | None = None
        try:
            assert_rekordbox_closed()

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

                # Written under a hidden name and renamed into place, so a crash mid-write
                # never leaves a half-written zip that looks like a backup.
                archive_path = self.backup_base / f"{backup_name}.zip"
                partial_path = self.backup_base / f".{backup_name}.partial.zip"
                self._create_archive(temp_dir, partial_path)

                if validate and not self.validate_backup(partial_path):
                    log_error(logger, f"Backup validation failed: {archive_path}")
                    partial_path.unlink()
                    return None
                os.replace(partial_path, archive_path)

                # Log success
                size_mb = archive_path.stat().st_size / (1024 * 1024)
                log_success(logger, f"Backup created successfully: {archive_path}")
                logger.info(f"Backup size: {size_mb:.1f} MB")

                if cleanup and self.config.max_backups > 0:
                    self._cleanup_old_backups()

                return str(archive_path)

        except Exception as e:
            log_exception(logger, e, "creating backup")
            return None
        finally:
            if partial_path is not None:
                partial_path.unlink(missing_ok=True)

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

            # The Library directory holds master.db; a backup without it is no backup.
            if not self.pioneer_library.is_dir():
                raise FileNotFoundError(f"Library directory not found: {self.pioneer_library}")
            library_backup = backup_dir / "Library"
            logger.info("Backing up Library directory...")
            shutil.copytree(self.pioneer_library, library_backup)
            log_success(logger, "Library backed up")

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
                "created_by": BACKUP_CREATED_BY,
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
            with open(metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)

        except Exception as e:
            raise BackupError(f"Could not write backup metadata: {e}") from e

    def _create_archive(self, source_dir: Path, archive_path: Path) -> None:
        """
        Create compressed archive from source directory.

        Args:
            source_dir: Source directory to compress
            archive_path: Path for output archive
        """
        logger.info("Creating compressed archive...")
        shutil.make_archive(str(archive_path.with_suffix("")), "zip", source_dir)

    def _cleanup_old_backups(self) -> None:
        """Clean up old backups based on max_backups setting."""
        try:
            backups = [
                b for b in self.list_backups() if not b.name.startswith(f"{PINNED_BACKUP_NAME}_")
            ]
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

    def restore_backup(self, backup_path: str | Path, create_safety_backup: bool = True) -> bool:
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
            assert_rekordbox_closed()
            self._assert_restore_preconditions()

            if not self.validate_backup(backup_file):
                log_error(logger, "Backup validation failed, aborting restore")
                return False

            # Create safety backup if requested
            if create_safety_backup:
                safety_backup = self._create_safety_backup()
                if safety_backup:
                    log_success(logger, f"Safety backup created: {safety_backup}")
                else:
                    log_error(logger, "Failed to create safety backup, aborting restore")
                    return False

            # Extract and restore
            with temporary_directory(prefix="rekordbox_restore_") as temp_dir:
                self._extract_backup(backup_file, temp_dir)
                self._restore_from_extracted(temp_dir)

            log_success(logger, "Backup restore completed successfully")
            return True

        except Exception as e:
            log_exception(logger, e, "restoring backup")
            return False

    def _create_safety_backup(self) -> str | None:
        """Create a safety backup before restore operation."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safety_name = f"safety_backup_before_restore_{timestamp}"
        # No cleanup: it could delete the very backup being restored.
        return self.create_backup(safety_name, validate=True, cleanup=False)

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

    def _restore_targets(self) -> list[Path]:
        return [self.pioneer_library, self.pioneer_app_support]

    def _assert_restore_preconditions(self) -> None:
        """Refuse a restore whose swap could strand data or act on the wrong folder."""
        for target in self._restore_targets():
            if target.is_symlink():
                raise BackupError(f"{target} is a symlink; restore would replace the link")
            leftovers = [
                p
                for marker in ("restoring", "pre-restore", "failed")
                for p in target.parent.glob(f"{target.name}.{marker}-*")
            ]
            if leftovers:
                listed = ", ".join(str(p) for p in leftovers)
                raise BackupError(
                    f"An earlier restore did not finish; inspect and remove these first: {listed}"
                )

    def _restore_from_extracted(self, extract_dir: Path) -> None:
        """
        Restore files from extracted backup directory.

        Args:
            extract_dir: Directory containing extracted backup
        """
        content_dirs = [
            d for d in extract_dir.iterdir() if d.is_dir() and d.name.endswith("_content")
        ]
        if len(content_dirs) != 1:
            raise BackupError(
                f"Expected one *_content folder in the backup, found {len(content_dirs)}"
            )
        backup_content = content_dirs[0]

        pairs = [(backup_content / "Library", self.pioneer_library)]
        if (backup_content / "Application Support").exists():
            pairs.append((backup_content / "Application Support", self.pioneer_app_support))
        elif self.pioneer_app_support.exists():
            raise BackupError(
                "Backup has no Application Support folder; restoring only the Library would "
                "pair it with newer settings"
            )

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        staged = self._stage(pairs, stamp)

        assert_rekordbox_closed()  # staging can take minutes; check again before touching live
        swapped: list[tuple[Path, Path | None]] = []
        try:
            for staging, target in staged:
                previous = target.with_name(f"{target.name}.pre-restore-{stamp}")
                moved = target.exists()
                if moved:
                    target.rename(previous)
                # Recorded before the second rename, so a failure there still rolls back.
                swapped.append((target, previous if moved else None))
                staging.rename(target)
        except BaseException:
            self._roll_back(swapped, stamp)
            for staging, _ in staged:
                if staging.exists():
                    shutil.rmtree(staging, onexc=_log_leftover)
            raise

        for target, previous in swapped:
            if previous is not None:
                shutil.rmtree(previous, onexc=_log_leftover)
            log_success(logger, f"Restored {target}")

    def _stage(self, pairs: list[tuple[Path, Path]], stamp: str) -> list[tuple[Path, Path]]:
        """Copy each backup folder beside its live target; a failure touches nothing live."""
        staged: list[tuple[Path, Path]] = []
        try:
            for source, target in pairs:
                staging = target.with_name(f"{target.name}.restoring-{stamp}")
                logger.info(f"Staging {target}...")
                staged.append((staging, target))
                shutil.copytree(source, staging)
        except BaseException:
            for staging, _ in staged:
                if staging.exists():
                    shutil.rmtree(staging, onexc=_log_leftover)
            raise
        return staged

    def _roll_back(self, swapped: list[tuple[Path, Path | None]], stamp: str) -> None:
        """Put each original folder back. Nothing is deleted here, only renamed."""
        for target, previous in reversed(swapped):
            try:
                failed = target.with_name(f"{target.name}.failed-{stamp}")
                if target.exists():
                    target.rename(failed)
                if previous is not None:
                    previous.rename(target)
                if failed.exists():
                    shutil.rmtree(failed, onexc=_log_leftover)
            except Exception as e:
                log_error(
                    logger,
                    f"Could not put {target} back ({e}). Your data is in {previous}; "
                    f"rename it to {target} by hand.",
                )

    def validate_backup(self, backup_path: str | Path) -> bool:
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

                file_list = zip_ref.namelist()
                master = [n for n in file_list if n.endswith(f"_content/{MASTER_DB}")]
                if len(master) != 1 or zip_ref.getinfo(master[0]).file_size == 0:
                    log_error(logger, f"Backup has no usable {MASTER_DB}")
                    return False

            if not _is_own_backup(backup_file):
                log_error(logger, "Backup has no rekordbox-smart-playlists metadata")
                return False

            logger.debug(f"Backup validation passed: {backup_file}")
            return True

        except zipfile.BadZipFile:
            log_error(logger, f"Invalid zip file: {backup_file}")
            return False
        except Exception as e:
            log_exception(logger, e, f"validating backup {backup_file}")
            return False

    def list_backups(self) -> list[BackupInfo]:
        """
        List all available backups.

        Returns:
            List of BackupInfo objects, sorted by creation time (newest first)
        """
        if not self.backup_base.exists():
            return []

        backup_files = [
            f
            for f in self.backup_base.glob("*.zip")
            if not f.name.startswith(".") and _is_own_backup(f)
        ]
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

    def get_backup_info(self, backup_path: str | Path) -> BackupInfo | None:
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

    def delete_backup(self, backup_path: str | Path) -> bool:
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

        if backup_file.resolve().parent != self.backup_base.resolve():
            log_error(logger, f"Refusing to delete a file outside {self.backup_base}")
            return False
        if not _is_own_backup(backup_file):
            log_error(logger, f"Refusing to delete a file this tool did not write: {backup_file}")
            return False

        try:
            backup_file.unlink()
            log_success(logger, f"Deleted backup: {backup_file.name}")
            return True
        except Exception as e:
            log_exception(logger, e, f"deleting backup {backup_file}")
            return False

    def get_backup_summary(self) -> dict[str, Any]:
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
            print("\nRecent backups:")
            for i, backup in enumerate(summary["backups"][:5], 1):
                print(f"  {i}. {backup.name} ({backup.size_mb:.1f} MB) - {backup.created_str}")
