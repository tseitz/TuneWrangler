"""
Command implementations for the CLI interface.

Provides concrete command classes for playlist and backup operations.
"""

import argparse
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from ..core.backup_manager import BackupError, BackupManager, assert_rekordbox_closed
from ..core.config import Config, ConfigurationError
from ..core.database import DatabaseError, RekordboxDatabase
from ..core.playlist_manager import ExistingPlaylistStrategy, PlaylistManager
from ..tagging import apply as tag_apply
from ..tagging import embed as tag_embed
from ..tagging import evaluate as tag_evaluate
from ..tagging import library as tag_library
from ..tagging import manifest as tag_manifest
from ..tagging import models as tag_models
from ..tagging import report as tag_report
from ..tagging import suggest as tag_suggest
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


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


class TagCommand(BaseCommand):
    """Audio tagging. Only `apply` and `undo` write to Rekordbox; the rest write under the tagging
    directory."""

    @staticmethod
    def setup_parser(parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers(dest="tag_action", help="Tag actions", metavar="ACTION")
        embed_parser = subparsers.add_parser(
            "embed", help="Embed tracks and cache the vectors (resumable)"
        )
        embed_parser.add_argument(
            "--limit",
            type=int,
            help="Only consider the first N library tracks (by id); cached ones are skipped",
        )
        embed_parser.add_argument(
            "--retry-failed", action="store_true", help="Retry tracks that failed before"
        )
        evaluate_parser = subparsers.add_parser(
            "evaluate", help="Cross-validate per-tag classifiers on the embedding cache"
        )
        evaluate_parser.add_argument(
            "--jobs", type=int, default=-1, help="Parallel workers for fold fits (default: all)"
        )
        subparsers.add_parser(
            "report", help="Write tracks.csv and crosstab.md from the caches and evaluation"
        )
        suggest_parser = subparsers.add_parser(
            "suggest", help="Write a tag manifest for the newest tracks with no lane tags"
        )
        suggest_parser.add_argument(
            "--limit", type=int, default=100, help="Newest N candidates by date added (default 100)"
        )
        suggest_parser.add_argument(
            "--all", action="store_true", help="Consider every candidate instead of the newest N"
        )
        suggest_parser.add_argument(
            "--min-precision",
            type=float,
            default=tag_suggest.DEFAULT_APPLY_PRECISION,
            help="Estimated precision a tag needs to be proposed (default 0.8)",
        )
        suggest_parser.add_argument(
            "--new-tag-precision",
            type=float,
            default=None,
            help="Threshold for Experimental Bass (and Halftime, which follows it); "
            "defaults to --min-precision",
        )

        apply_parser = subparsers.add_parser(
            "apply", help="Add a manifest's proposed tags to Rekordbox (add-only, backs up first)"
        )
        apply_parser.add_argument("manifest", type=Path, help="Manifest from tag suggest")
        pick = apply_parser.add_mutually_exclusive_group()
        pick.add_argument("--limit", type=_positive_int, help="Only the first N apply entries")
        pick.add_argument("--sample", type=_positive_int, help="A random N apply entries")
        pick.add_argument("--only", nargs="+", help="Only these content ids")
        apply_parser.add_argument("--seed", type=int, default=0, help="Seed for --sample")
        apply_parser.add_argument(
            "--yes", action="store_true", help="Write to Rekordbox (default is a dry run)"
        )
        undo_parser = subparsers.add_parser(
            "undo", help="Remove exactly the rows a tag apply wrote, from its apply log"
        )
        undo_parser.add_argument("log", type=Path, help="The .applied-*.json log from tag apply")
        undo_parser.add_argument(
            "--yes", action="store_true", help="Write to Rekordbox (default is a dry run)"
        )
        undo_parser.add_argument(
            "--force",
            action="store_true",
            help="Also remove tags on tracks you've reviewed (Autotagged removed)",
        )

    @staticmethod
    def validate_args(args: argparse.Namespace) -> bool:
        if not getattr(args, "tag_action", None):
            logger.error("Tag action is required")
            return False
        if args.tag_action == "embed" and args.limit is not None and args.limit < 1:
            logger.error("--limit must be at least 1")
            return False
        if args.tag_action == "suggest":
            if args.limit < 1:
                logger.error("--limit must be at least 1")
                return False
            if not tag_suggest.REVIEW_PRECISION <= args.min_precision <= 1:
                logger.error(
                    f"--min-precision must be between {tag_suggest.REVIEW_PRECISION} and 1"
                )
                return False
            new = args.new_tag_precision
            if new is not None and not tag_suggest.REVIEW_PRECISION <= new <= 1:
                logger.error(
                    f"--new-tag-precision must be between {tag_suggest.REVIEW_PRECISION} and 1"
                )
                return False
        return True

    def execute(self, args: argparse.Namespace) -> int:
        try:
            if args.tag_action == "suggest":
                return self._suggest(args)
            if args.tag_action == "embed":
                return self._embed(args)
            if args.tag_action == "evaluate":
                return self._evaluate(args)
            if args.tag_action == "report":
                return self._report()
            if args.tag_action == "apply":
                return self._apply(args)
            if args.tag_action == "undo":
                return self._undo(args)
            logger.error(f"Unknown tag action: {args.tag_action}")
            return 1
        except (
            ConfigurationError,
            tag_models.ModelIntegrityError,
            tag_evaluate.PoolGuardError,
            tag_evaluate.ControlError,
            tag_report.ReportInputError,
            tag_manifest.ManifestError,
            tag_suggest.SuggestInputError,
            tag_apply.ApplyError,
            BackupError,
        ) as e:
            log_error(logger, str(e))
            return 1
        except Exception as e:
            log_exception(logger, e, f"tag {args.tag_action}")
            return 1

    def _embed(self, args: argparse.Namespace) -> int:
        tagging_dir = Path(self.config.tagging_dir).expanduser()
        vocab = tag_library.load_vocabulary(
            Path(self.config.playlist_data_path) / "helpers" / "_lanes.json"
        )
        with RekordboxDatabase(self.config) as db:
            tracks = tag_library.load_library(db, vocab)
        logger.info(f"{len(tracks)} library tracks with an existing file")

        embed_fn, class_names = tag_embed.make_essentia_embedder(tagging_dir / "models")
        cache = tag_embed.EmbeddingCache(tagging_dir, class_names)
        summary = tag_embed.run_embed(
            tracks, cache, embed_fn, limit=args.limit, retry_failed=args.retry_failed
        )
        print(summary.render())
        return 1 if summary.failed else 0

    def _evaluate(self, args: argparse.Namespace) -> int:
        tagging_dir = Path(self.config.tagging_dir).expanduser()
        vocab = tag_library.load_vocabulary(
            Path(self.config.playlist_data_path) / "helpers" / "_lanes.json"
        )
        with RekordboxDatabase(self.config) as db:
            tracks = tag_library.load_library(db, vocab)
        tag_evaluate.run_evaluation(tracks, tagging_dir, vocab, args.jobs)
        return 0

    def _vocab(self) -> frozenset[str]:
        return tag_library.load_vocabulary(
            Path(self.config.playlist_data_path) / "helpers" / "_lanes.json"
        )

    def _apply(self, args: argparse.Namespace) -> int:
        manifest = tag_manifest.read_manifest(args.manifest)
        selection = tag_apply.Selection(
            limit=args.limit,
            sample=args.sample,
            seed=args.seed,
            only=frozenset(args.only or ()),
        )
        with RekordboxDatabase(self.config) as db:
            result = tag_apply.apply_manifest(
                db,
                manifest,
                args.manifest,
                self._vocab(),
                selection,
                create_backup=self._tag_backup,
                assert_closed=assert_rekordbox_closed,
                dry_run=self._dry(args),
            )
        verb = "Would add" if self._dry(args) else "Added"
        for content_id, tags in result.writes:
            print(f"  {content_id}: {', '.join(tags)}")
        for content_id, reason in result.skipped:
            print(f"  skipped {content_id}: {reason}")
        rows = sum(len(t) for _, t in result.writes)
        print(f"{verb} {rows} tags on {len(result.writes)} tracks; skipped {len(result.skipped)}")
        if result.log_path:
            print(f"apply log (for tag undo): {result.log_path}")
        elif self._dry(args) and result.writes:
            print("dry run: nothing written; add --yes to write")
        return 0

    def _dry(self, args: argparse.Namespace) -> bool:
        return self.config.dry_run or not args.yes

    def _undo(self, args: argparse.Namespace) -> int:
        with RekordboxDatabase(self.config) as db:
            removed, gone = tag_apply.undo(
                db,
                args.log,
                create_backup=self._tag_backup,
                assert_closed=assert_rekordbox_closed,
                dry_run=self._dry(args),
                force=args.force,
            )
        for row_id, reason in gone:
            print(f"  left {row_id}: {reason}")
        verb = "Would remove" if self._dry(args) else "Removed"
        print(f"{verb} {len(removed)} tag rows; {len(gone)} already gone or changed")
        return 0

    def _tag_backup(self) -> str | None:
        # Exempt from rotation: it's the snapshot to go back to if a batch goes wrong.
        return BackupManager(self.config).create_backup(tag_apply.BACKUP_NAME, cleanup=False)

    def _suggest(self, args: argparse.Namespace) -> int:
        tagging_dir = Path(self.config.tagging_dir).expanduser()
        vocab = tag_library.load_vocabulary(
            Path(self.config.playlist_data_path) / "helpers" / "_lanes.json"
        )
        with RekordboxDatabase(self.config) as db:
            tracks = tag_library.load_library(db, vocab)
        now = datetime.now()
        manifest, stats, missing = tag_suggest.suggest(
            tracks,
            vocab,
            tag_evaluate.load_cache(tagging_dir),
            args.min_precision,
            None if args.all else args.limit,
            now,
            new_tag_precision=args.new_tag_precision,
        )
        path = tagging_dir / "manifests" / f"tag-manifest-{now:%Y%m%d-%H%M%S}.json"
        tag_manifest.write_manifest(manifest, path)
        print(tag_suggest.render_summary(manifest, stats, missing, str(path)))
        return 0

    def _report(self) -> int:
        tagging_dir = Path(self.config.tagging_dir).expanduser()
        vocab = tag_library.load_vocabulary(
            Path(self.config.playlist_data_path) / "helpers" / "_lanes.json"
        )
        tag_report.read_oof(tagging_dir)
        with RekordboxDatabase(self.config) as db:
            tracks = tag_library.load_library(db, vocab)
        tag_report.run_report(tracks, tagging_dir, vocab)
        return 0
