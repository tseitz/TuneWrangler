"""
Command implementations for the CLI interface.

Provides concrete command classes for playlist, backup, and metadata operations.
"""

import argparse
from abc import ABC, abstractmethod
from pathlib import Path

from ..utils.logging import get_logger, log_success, log_error, log_exception
from ..core.config import Config
from ..core.database import RekordboxDatabase, DatabaseError
from ..core.playlist_manager import PlaylistManager
from ..core.backup_manager import BackupManager
from ..core.metadata_fixer import MetadataFixer, MetadataSource

logger = get_logger(__name__)


class BaseCommand(ABC):
    """Base class for CLI commands."""

    def __init__(self, config: Config):
        """
        Initialize command with configuration.

        Args:
            config: Configuration object
        """
        self.config = config

    @staticmethod
    @abstractmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        """Set up argument parser for this command."""
        pass

    @staticmethod
    @abstractmethod
    def validate_args(args: argparse.Namespace) -> bool:
        """Validate command-specific arguments."""
        pass

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the command and return exit code."""
        pass


class PlaylistCommand(BaseCommand):
    """Command for playlist management operations."""

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        """Set up playlist command parser."""
        subparsers = parser.add_subparsers(
            dest="playlist_action", help="Playlist actions", metavar="ACTION"
        )

        # Create playlists
        create_parser = subparsers.add_parser(
            "create", help="Create smart playlists from JSON configurations"
        )
        create_group = create_parser.add_mutually_exclusive_group(required=True)
        create_group.add_argument(
            "--file", "-f", type=str, help="Create playlists from specific JSON file"
        )
        create_group.add_argument(
            "--all",
            "-a",
            action="store_true",
            help="Create playlists from all JSON files in playlist data directory",
        )
        create_parser.add_argument(
            "--skip-backup",
            action="store_true",
            help="Skip automatic backup before creating playlists",
        )

        # List playlists
        list_parser = subparsers.add_parser("list", help="List existing playlists")
        list_parser.add_argument(
            "--filter", type=str, help="Filter playlists by name (case-insensitive)"
        )
        list_parser.add_argument(
            "--smart-only", action="store_true", help="Show only smart playlists"
        )

        # Validate configurations
        validate_parser = subparsers.add_parser(
            "validate", help="Validate playlist configuration files"
        )
        validate_parser.add_argument("--file", "-f", type=str, help="Validate specific JSON file")
        validate_parser.add_argument(
            "--all",
            "-a",
            action="store_true",
            help="Validate all JSON files in playlist data directory",
        )

    @staticmethod
    def validate_args(args: argparse.Namespace) -> bool:
        """Validate playlist command arguments."""
        if not hasattr(args, "playlist_action") or not args.playlist_action:
            logger.error("Playlist action is required")
            return False

        if args.playlist_action == "create":
            if args.file and not Path("playlist-data", args.file).exists():
                logger.error(f"Playlist file not found: {args.file}")
                return False

        return True

    def execute(self, args: argparse.Namespace) -> int:
        """Execute playlist command."""
        try:
            if args.playlist_action == "create":
                return self._create_playlists(args)
            elif args.playlist_action == "list":
                return self._list_playlists(args)
            elif args.playlist_action == "validate":
                return self._validate_configurations(args)
            else:
                logger.error(f"Unknown playlist action: {args.playlist_action}")
                return 1
        except Exception as e:
            log_exception(logger, e, f"playlist {args.playlist_action}")
            return 1

    def _create_playlists(self, args: argparse.Namespace) -> int:
        """Create playlists from configuration files."""
        logger.info("Creating playlists...")

        # Create backup if requested and not in dry run mode
        if not args.skip_backup and not self.config.dry_run and self.config.backup_before_changes:
            backup_manager = BackupManager(self.config)
            backup_path = backup_manager.create_backup("before_playlist_creation")
            if backup_path:
                log_success(logger, f"Backup created: {backup_path}")
            else:
                log_error(logger, "Failed to create backup")
                return 1

        try:
            with RekordboxDatabase(self.config) as db:
                playlist_manager = PlaylistManager(db, self.config)

                if args.file:
                    # Create from specific file
                    config_file = Path(args.file)
                    if not config_file.is_absolute():
                        config_file = Path(self.config.playlist_data_path) / config_file

                    results = playlist_manager.create_playlists_from_file(config_file)
                else:
                    # Create from all files
                    results = playlist_manager.create_playlists_from_directory(
                        self.config.playlist_data_path
                    )

                # Commit changes if not in dry run mode
                if not self.config.dry_run:
                    db.commit()

                # Print summary
                successful = [r for r in results if r.success]
                failed = [r for r in results if not r.success]
                created = [r for r in successful if not r.skipped]
                skipped = [r for r in successful if r.skipped]

                print(f"\nPlaylist Creation Summary:")
                print(f"Created: {len(created)}")
                print(f"Skipped: {len(skipped)}")
                print(f"Failed: {len(failed)}")

                if skipped:
                    print(f"\nSkipped playlists:")
                    for result in skipped:
                        reason = result.skip_reason or "Already exists"
                        print(f"  - {result.playlist_name}: {reason}")

                if failed:
                    print(f"\nFailed playlists:")
                    for result in failed:
                        print(f"  - {result.playlist_name}: {result.error_message}")

                return 0 if not failed else 1

        except DatabaseError as e:
            log_error(logger, f"Database error: {e}")
            return 1

    def _list_playlists(self, args: argparse.Namespace) -> int:
        """List existing playlists."""
        try:
            with RekordboxDatabase(self.config) as db:
                playlists = db.get_playlists()

                # Apply filters
                if args.filter:
                    filter_term = args.filter.lower()
                    playlists = [p for p in playlists if filter_term in p.Name.lower()]

                if args.smart_only:
                    playlists = [p for p in playlists if p.is_smart_playlist]

                # Print playlists
                print(f"\nRekordbox Playlists ({len(playlists)} found):")
                print("-" * 60)

                for playlist in playlists:
                    playlist_type = "Smart" if playlist.is_smart_playlist else "Regular"
                    parent_name = (
                        playlist.Parent.Name
                        if hasattr(playlist, "Parent") and playlist.Parent
                        else "Root"
                    )

                    print(f"{playlist.Name}")
                    print(f"  Type: {playlist_type}")
                    print(f"  Parent: {parent_name}")
                    print(f"  ID: {playlist.ID}")
                    print()

                return 0

        except DatabaseError as e:
            log_error(logger, f"Database error: {e}")
            return 1

    def _validate_configurations(self, args: argparse.Namespace) -> int:
        """Validate playlist configuration files."""
        from ..utils.validation import validate_playlist_config
        import json

        files_to_validate = []

        if args.file:
            config_file = Path(args.file)
            if not config_file.is_absolute():
                config_file = Path(self.config.playlist_data_path) / config_file
            files_to_validate.append(config_file)
        else:
            # Validate all JSON files
            playlist_dir = Path(self.config.playlist_data_path)
            files_to_validate = list(playlist_dir.glob("*.json"))

        if not files_to_validate:
            logger.warning("No configuration files found to validate")
            return 0

        all_valid = True

        for config_file in files_to_validate:
            try:
                with open(config_file, "r") as f:
                    config_data = json.load(f)

                is_valid, errors = validate_playlist_config(config_data)

                if is_valid:
                    log_success(logger, f"Valid: {config_file.name}")
                else:
                    log_error(logger, f"Invalid: {config_file.name}")
                    for error in errors:
                        print(f"  - {error}")
                    all_valid = False

            except Exception as e:
                log_error(logger, f"Error validating {config_file.name}: {e}")
                all_valid = False

        return 0 if all_valid else 1


class BackupCommand(BaseCommand):
    """Command for backup and restore operations."""

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        """Set up backup command parser."""
        subparsers = parser.add_subparsers(
            dest="backup_action", help="Backup actions", metavar="ACTION"
        )

        # Create backup
        create_parser = subparsers.add_parser(
            "create", help="Create a backup of Rekordbox database"
        )
        create_parser.add_argument(
            "--name",
            "-n",
            type=str,
            help="Custom name for backup (timestamp used if not provided)",
        )
        create_parser.add_argument(
            "--no-validate",
            action="store_true",
            help="Skip backup validation after creation",
        )

        # List backups
        list_parser = subparsers.add_parser("list", help="List available backups")
        list_parser.add_argument(
            "--detailed", action="store_true", help="Show detailed backup information"
        )

        # Restore backup
        restore_parser = subparsers.add_parser("restore", help="Restore from backup")
        restore_parser.add_argument(
            "backup_path", type=str, help="Path to backup file or backup name"
        )
        restore_parser.add_argument(
            "--no-safety-backup",
            action="store_true",
            help="Skip creating safety backup before restore",
        )

        # Validate backup
        validate_parser = subparsers.add_parser("validate", help="Validate backup file integrity")
        validate_parser.add_argument(
            "backup_path", type=str, help="Path to backup file to validate"
        )

        # Delete backup
        delete_parser = subparsers.add_parser("delete", help="Delete backup file")
        delete_parser.add_argument("backup_path", type=str, help="Path to backup file to delete")
        delete_parser.add_argument(
            "--force", action="store_true", help="Delete without confirmation"
        )

        # Cleanup old backups
        cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old backups")
        cleanup_parser.add_argument(
            "--keep",
            type=int,
            default=5,
            help="Number of recent backups to keep (default: 5)",
        )

    @staticmethod
    def validate_args(args: argparse.Namespace) -> bool:
        """Validate backup command arguments."""
        if not hasattr(args, "backup_action") or not args.backup_action:
            logger.error("Backup action is required")
            return False

        if args.backup_action in ["restore", "validate", "delete"]:
            if not hasattr(args, "backup_path") or not args.backup_path:
                logger.error(f"Backup path is required for {args.backup_action}")
                return False

        return True

    def execute(self, args: argparse.Namespace) -> int:
        """Execute backup command."""
        try:
            backup_manager = BackupManager(self.config)

            if args.backup_action == "create":
                return self._create_backup(backup_manager, args)
            elif args.backup_action == "list":
                return self._list_backups(backup_manager, args)
            elif args.backup_action == "restore":
                return self._restore_backup(backup_manager, args)
            elif args.backup_action == "validate":
                return self._validate_backup(backup_manager, args)
            elif args.backup_action == "delete":
                return self._delete_backup(backup_manager, args)
            elif args.backup_action == "cleanup":
                return self._cleanup_backups(backup_manager, args)
            else:
                logger.error(f"Unknown backup action: {args.backup_action}")
                return 1

        except Exception as e:
            log_exception(logger, e, f"backup {args.backup_action}")
            return 1

    def _create_backup(self, backup_manager: BackupManager, args: argparse.Namespace) -> int:
        """Create a new backup."""
        if self.config.dry_run:
            logger.info("[DRY RUN] Would create backup")
            return 0

        backup_path = backup_manager.create_backup(
            backup_name=args.name, validate=not args.no_validate
        )

        if backup_path:
            log_success(logger, f"Backup created: {backup_path}")
            return 0
        else:
            log_error(logger, "Failed to create backup")
            return 1

    def _list_backups(self, backup_manager: BackupManager, args: argparse.Namespace) -> int:
        """List available backups."""
        if args.detailed:
            backup_manager.print_backup_summary()
        else:
            backups = backup_manager.list_backups()

            if not backups:
                print("No backups found")
                return 0

            print(f"\nAvailable Backups ({len(backups)}):")
            print("-" * 60)

            for i, backup in enumerate(backups, 1):
                print(f"{i:2d}. {backup.name}")
                print(f"    Size: {backup.size_mb:.1f} MB")
                print(f"    Date: {backup.created_str}")
                print()

        return 0

    def _restore_backup(self, backup_manager: BackupManager, args: argparse.Namespace) -> int:
        """Restore from backup."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would restore from backup: {args.backup_path}")
            return 0

        # Resolve backup path
        backup_path = Path(args.backup_path)
        if not backup_path.is_absolute():
            # Try to find backup by name
            backups = backup_manager.list_backups()
            matching_backups = [b for b in backups if args.backup_path in b.name]

            if len(matching_backups) == 1:
                backup_path = matching_backups[0].path
            elif len(matching_backups) > 1:
                logger.error(f"Multiple backups match '{args.backup_path}':")
                for backup in matching_backups:
                    print(f"  - {backup.name}")
                return 1
            else:
                logger.error(f"No backup found matching '{args.backup_path}'")
                return 1

        success = backup_manager.restore_backup(
            backup_path, create_safety_backup=not args.no_safety_backup
        )

        if success:
            log_success(logger, "Backup restored successfully")
            return 0
        else:
            log_error(logger, "Failed to restore backup")
            return 1

    def _validate_backup(self, backup_manager: BackupManager, args: argparse.Namespace) -> int:
        """Validate backup file."""
        backup_path = Path(args.backup_path)

        if backup_manager.validate_backup(backup_path):
            log_success(logger, f"Backup is valid: {backup_path}")
            return 0
        else:
            log_error(logger, f"Backup is invalid: {backup_path}")
            return 1

    def _delete_backup(self, backup_manager: BackupManager, args: argparse.Namespace) -> int:
        """Delete backup file."""
        backup_path = Path(args.backup_path)

        if not args.force:
            response = input(f"Delete backup '{backup_path}'? (y/N): ")
            if response.lower() not in ["y", "yes"]:
                logger.info("Deletion cancelled")
                return 0

        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would delete backup: {backup_path}")
            return 0

        if backup_manager.delete_backup(backup_path):
            log_success(logger, f"Backup deleted: {backup_path}")
            return 0
        else:
            log_error(logger, f"Failed to delete backup: {backup_path}")
            return 1

    def _cleanup_backups(self, backup_manager: BackupManager, args: argparse.Namespace) -> int:
        """Clean up old backups."""
        backups = backup_manager.list_backups()

        if len(backups) <= args.keep:
            logger.info(f"No cleanup needed. Found {len(backups)} backups, keeping {args.keep}")
            return 0

        backups_to_delete = backups[args.keep :]

        print(f"Will delete {len(backups_to_delete)} old backups:")
        for backup in backups_to_delete:
            print(f"  - {backup.name} ({backup.created_str})")

        if not self.config.dry_run:
            response = input(f"\nProceed with deletion? (y/N): ")
            if response.lower() not in ["y", "yes"]:
                logger.info("Cleanup cancelled")
                return 0

        deleted_count = 0
        for backup in backups_to_delete:
            if self.config.dry_run:
                logger.info(f"[DRY RUN] Would delete: {backup.name}")
                deleted_count += 1
            else:
                if backup_manager.delete_backup(backup.path):
                    deleted_count += 1

        log_success(logger, f"Cleaned up {deleted_count} backups")
        return 0


class MetadataCommand(BaseCommand):
    """Command for metadata synchronization operations."""

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        """Set up metadata command parser."""
        subparsers = parser.add_subparsers(
            dest="metadata_action", help="Metadata actions", metavar="ACTION"
        )

        # Fix metadata
        fix_parser = subparsers.add_parser(
            "fix", help="Fix metadata discrepancies between database and filenames"
        )
        fix_group = fix_parser.add_mutually_exclusive_group()
        fix_group.add_argument(
            "--interactive",
            "-i",
            action="store_true",
            help="Interactive mode - prompt for each discrepancy",
        )
        fix_group.add_argument(
            "--batch-database",
            action="store_true",
            help="Batch mode - use database as authority",
        )
        fix_group.add_argument(
            "--batch-filename",
            action="store_true",
            help="Batch mode - use filename as authority",
        )
        fix_parser.add_argument(
            "--skip-backup",
            action="store_true",
            help="Skip automatic backup before fixing metadata",
        )

        # Preview metadata changes
        preview_parser = subparsers.add_parser(
            "preview", help="Preview metadata discrepancies without making changes"
        )
        preview_parser.add_argument(
            "--max-files",
            type=int,
            default=20,
            help="Maximum number of files to preview (default: 20)",
        )

        # Validate filenames
        validate_parser = subparsers.add_parser(
            "validate", help="Validate filename formats in collection"
        )
        validate_parser.add_argument(
            "--max-files",
            type=int,
            default=50,
            help="Maximum number of files to check (default: 50)",
        )

    @staticmethod
    def validate_args(args: argparse.Namespace) -> bool:
        """Validate metadata command arguments."""
        if not hasattr(args, "metadata_action") or not args.metadata_action:
            logger.error("Metadata action is required")
            return False

        if args.metadata_action == "fix":
            # Must specify one mode for fix command
            if not (args.interactive or args.batch_database or args.batch_filename):
                logger.error(
                    "Must specify fix mode: --interactive, --batch-database, or --batch-filename"
                )
                return False

        return True

    def execute(self, args: argparse.Namespace) -> int:
        """Execute metadata command."""
        try:
            if args.metadata_action == "fix":
                return self._fix_metadata(args)
            elif args.metadata_action == "preview":
                return self._preview_metadata(args)
            elif args.metadata_action == "validate":
                return self._validate_filenames(args)
            else:
                logger.error(f"Unknown metadata action: {args.metadata_action}")
                return 1

        except Exception as e:
            log_exception(logger, e, f"metadata {args.metadata_action}")
            return 1

    def _fix_metadata(self, args: argparse.Namespace) -> int:
        """Fix metadata discrepancies."""
        try:
            with RekordboxDatabase(self.config) as db:
                metadata_fixer = MetadataFixer(db, self.config)

                if args.interactive:
                    results = metadata_fixer.fix_metadata_interactive()
                elif args.batch_database:
                    results = metadata_fixer.fix_metadata_batch(MetadataSource.DATABASE)
                elif args.batch_filename:
                    results = metadata_fixer.fix_metadata_batch(MetadataSource.FILENAME)

                # Check for failures
                failed_results = [r for r in results if not r.success]
                return 0 if not failed_results else 1

        except Exception as e:
            log_exception(logger, e, "fixing metadata")
            return 1

    def _preview_metadata(self, args: argparse.Namespace) -> int:
        """Preview metadata discrepancies."""
        try:
            with RekordboxDatabase(self.config) as db:
                metadata_fixer = MetadataFixer(db, self.config)
                comparisons = metadata_fixer.preview_metadata_changes(args.max_files)

                if not comparisons:
                    log_success(logger, "No metadata discrepancies found")

                return 0

        except Exception as e:
            log_exception(logger, e, "previewing metadata")
            return 1

    def _validate_filenames(self, args: argparse.Namespace) -> int:
        """Validate filename formats."""
        from ..utils.validation import validate_filename_format
        from ..utils.file_utils import find_files

        try:
            collection_path = Path(self.config.collection_path)
            patterns = [f"*{ext}" for ext in self.config.audio_extensions]
            audio_files = find_files(collection_path, patterns, recursive=True)

            if not audio_files:
                logger.warning("No audio files found in collection")
                return 0

            files_to_check = audio_files[: args.max_files]
            valid_count = 0
            invalid_count = 0

            print(f"\nValidating filename formats ({len(files_to_check)} files):")
            print("-" * 60)

            for file_path in files_to_check:
                is_valid, error = validate_filename_format(file_path.name)

                if is_valid:
                    valid_count += 1
                    print(f"✓ {file_path.name}")
                else:
                    invalid_count += 1
                    print(f"✗ {file_path.name}")
                    print(f"  {error}")

            print(f"\nValidation Summary:")
            print(f"Valid filenames: {valid_count}")
            print(f"Invalid filenames: {invalid_count}")

            return 0 if invalid_count == 0 else 1

        except Exception as e:
            log_exception(logger, e, "validating filenames")
            return 1
