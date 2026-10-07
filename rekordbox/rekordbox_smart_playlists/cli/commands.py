"""
Command implementations for the CLI interface.

Provides concrete command classes for playlist and backup operations.
"""

import argparse
from abc import ABC, abstractmethod
from pathlib import Path

from ..core.backup_manager import BackupManager
from ..core.config import Config, ConfigurationError
from ..core.database import DatabaseError, RekordboxDatabase
from ..core.playlist_manager import ExistingPlaylistStrategy, PlaylistManager
from ..utils.logging import get_logger, log_error, log_exception, log_success

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
        create_parser.add_argument(
            "--existing",
            choices=["overwrite", "skip", "prompt"],
            default=None,
            help=(
                "How to handle existing playlists: overwrite, skip, or prompt for each "
                "(default: prompt interactively at start)"
            ),
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
        except ConfigurationError as e:
            log_error(logger, str(e))
            return 1
        except Exception as e:
            log_exception(logger, e, f"playlist {args.playlist_action}")
            return 1

    def _create_playlists(self, args: argparse.Namespace) -> int:
        """Create playlists from configuration files."""
        logger.info("Creating playlists...")

        if args.file:
            config_file = Path(args.file)
            if not config_file.is_absolute():
                config_file = Path(self.config.playlist_data_path) / config_file
            if not config_file.is_file():
                log_error(logger, f"Playlist file not found: {config_file}")
                return 1

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

                # Determine strategy for handling existing playlists
                if args.existing:
                    strategy = ExistingPlaylistStrategy(args.existing)
                elif self.config.dry_run:
                    print(
                        "[DRY RUN] Would prompt for existing playlist strategy. "
                        "Defaulting to skip.\n"
                    )
                    strategy = ExistingPlaylistStrategy.SKIP_ALL
                else:
                    print("\nHow would you like to handle existing playlists?")
                    print("  1. Overwrite all existing playlists")
                    print("  2. Skip all existing playlists")
                    print("  3. Prompt for each existing playlist")
                    choice = input("Choose (1/2/3) [default: 3]: ").strip()
                    if choice == "1":
                        strategy = ExistingPlaylistStrategy.OVERWRITE_ALL
                    elif choice == "2":
                        strategy = ExistingPlaylistStrategy.SKIP_ALL
                    else:
                        strategy = ExistingPlaylistStrategy.PROMPT_EACH
                    print()

                playlist_manager.existing_strategy = strategy

                config_file_arg = args.file if args.file else None
                preflight_errors = playlist_manager.preflight(config_file_arg)
                if preflight_errors:
                    log_error(logger, "Pre-flight failed; nothing was changed:")
                    for error in preflight_errors:
                        print(f"  - {error}")
                    return 1

                # Check for existing root folders and handle based on strategy
                existing_roots = playlist_manager.find_existing_root_folders(config_file_arg)

                if existing_roots:
                    print(f"Found {len(existing_roots)} existing root folder(s):")
                    for root in existing_roots:
                        child_str = (
                            f"{root['child_count']} child playlist(s)"
                            if root["child_count"]
                            else "empty"
                        )
                        print(f"  - {root['name']} ({child_str})")
                    print()

                    if self.config.dry_run:
                        print("[DRY RUN] Would handle existing folders based on strategy.\n")
                    elif strategy == ExistingPlaylistStrategy.OVERWRITE_ALL:
                        for root in existing_roots:
                            deleted = playlist_manager.delete_root_folder(root["playlist"])
                            print(f"  Deleted '{root['name']}' ({deleted} playlist(s)).")
                        print()
                    elif strategy == ExistingPlaylistStrategy.SKIP_ALL:
                        for root in existing_roots:
                            playlist_manager._skip_parents.add(root["name"])
                            print(f"  Skipping '{root['name']}'.")
                        print()
                    else:
                        # PROMPT_EACH
                        for root in existing_roots:
                            child_count = root["child_count"]
                            child_str = (
                                f"{child_count} child playlist(s)" if child_count else "empty"
                            )
                            response = input(
                                f"'{root['name']}' already exists ({child_str}). "
                                "Overwrite or skip? (o/S): "
                            )
                            if response.lower() in ["o", "overwrite"]:
                                deleted = playlist_manager.delete_root_folder(root["playlist"])
                                print(f"  Deleted '{root['name']}' ({deleted} playlist(s)).")
                            else:
                                playlist_manager._skip_parents.add(root["name"])
                                print(f"  Skipping '{root['name']}'.")
                        print()

                if args.file:
                    results = playlist_manager.create_playlists_from_file(config_file)
                else:
                    # Create from all files
                    results = playlist_manager.create_playlists_from_directory(
                        self.config.playlist_data_path
                    )

                successful = [r for r in results if r.success]
                failed = [r for r in results if not r.success]

                if failed:
                    db.rollback()
                elif not self.config.dry_run:
                    db.commit()

                created = [r for r in successful if not r.skipped]
                skipped = [r for r in successful if r.skipped]

                print("\nPlaylist Creation Summary:")
                print(f"Created: {len(created)}")
                print(f"Skipped: {len(skipped)}")
                print(f"Failed: {len(failed)}")

                if skipped:
                    print("\nSkipped playlists:")
                    for result in skipped:
                        reason = result.skip_reason or "Already exists"
                        print(f"  - {result.playlist_name}: {reason}")

                if failed:
                    print("\nFailed playlists:")
                    for result in failed:
                        print(f"  - {result.playlist_name}: {result.error_message}")
                    print("\nRolled back: nothing was changed.")

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
        import json

        from ..utils.validation import validate_playlist_config

        files_to_validate = []

        if args.file:
            config_file = Path(args.file)
            if not config_file.is_absolute():
                config_file = Path(self.config.playlist_data_path) / config_file
            files_to_validate.append(config_file)
        else:
            # Validate all JSON files
            playlist_dir = Path(self.config.playlist_data_path)
            files_to_validate = [
                f for f in sorted(playlist_dir.glob("*.json")) if not f.name.startswith((".", "_"))
            ]

        if not files_to_validate:
            log_error(logger, f"No configuration files found in {self.config.playlist_data_path}")
            return 1

        all_valid = True

        for config_file in files_to_validate:
            try:
                with open(config_file) as f:
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

        logger.info(f"Validated {len(files_to_validate)} configuration files")
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

        except ConfigurationError as e:
            log_error(logger, str(e))
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
            response = input("\nProceed with deletion? (y/N): ")
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
