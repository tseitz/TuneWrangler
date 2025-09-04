"""
Main CLI interface for Rekordbox Smart Playlists.

Provides a unified command-line interface for all playlist management operations.
"""

import sys
import argparse
from pathlib import Path
from typing import Optional, List

from ..utils.logging import setup_logging, get_logger
from ..core.config import Config, load_config, find_config_file
from .commands import PlaylistCommand, BackupCommand, MetadataCommand

logger = get_logger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog="rekordbox-smart-playlists",
        description="Manage Rekordbox smart playlists from JSON configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create playlists from all JSON files
  rekordbox-smart-playlists playlist create --all
  
  # Create playlists from specific file
  rekordbox-smart-playlists playlist create --file house.json
  
  # Create backup before operations
  rekordbox-smart-playlists backup create
  
  # Fix metadata interactively
  rekordbox-smart-playlists metadata fix --interactive
  
  # Preview metadata changes
  rekordbox-smart-playlists metadata preview
        """,
    )

    # Global options
    parser.add_argument(
        "--config", "-c", type=str, help="Path to configuration file (JSON or TOML)"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode (warnings and errors only)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    parser.add_argument("--log-file", type=str, help="Log to file in addition to console")

    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands", metavar="COMMAND")

    # Playlist commands
    playlist_parser = subparsers.add_parser(
        "playlist", help="Playlist management commands", aliases=["pl"]
    )
    PlaylistCommand.setup_parser(playlist_parser)

    # Backup commands
    backup_parser = subparsers.add_parser(
        "backup", help="Backup and restore commands", aliases=["bk"]
    )
    BackupCommand.setup_parser(backup_parser)

    # Metadata commands
    metadata_parser = subparsers.add_parser(
        "metadata", help="Metadata synchronization commands", aliases=["meta"]
    )
    MetadataCommand.setup_parser(metadata_parser)

    return parser


def load_configuration(args: argparse.Namespace) -> Config:
    """
    Load configuration from various sources.

    Args:
        args: Parsed command-line arguments

    Returns:
        Loaded configuration object
    """
    # Determine config file path
    config_file = None
    if args.config:
        config_file = Path(args.config)
        if not config_file.exists():
            logger.error(f"Configuration file not found: {config_file}")
            sys.exit(1)
    else:
        # Try to find default config file
        config_file = find_config_file()
        if config_file:
            logger.info(f"Using configuration file: {config_file}")

    # Create command-line overrides
    overrides = {}
    if hasattr(args, "dry_run") and args.dry_run:
        overrides["dry_run"] = args.dry_run
    if hasattr(args, "verbose") and args.verbose:
        overrides["verbose"] = args.verbose
        overrides["log_level"] = "DEBUG"
    if hasattr(args, "quiet") and args.quiet:
        overrides["log_level"] = "WARNING"
    if hasattr(args, "log_file") and args.log_file:
        overrides["log_file"] = args.log_file

    # Load configuration
    config = load_config(config_file=config_file, **overrides)

    return config


def setup_logging_from_config(config: Config) -> None:
    """Set up logging based on configuration."""
    setup_logging(
        level=config.log_level,
        log_file=config.log_file,
        console=True,
        include_timestamp=True,
    )


def validate_args(args: argparse.Namespace) -> bool:
    """
    Validate command-line arguments.

    Args:
        args: Parsed arguments

    Returns:
        True if arguments are valid, False otherwise
    """
    # Check for conflicting options
    if hasattr(args, "verbose") and hasattr(args, "quiet") and args.verbose and args.quiet:
        logger.error("Cannot use both --verbose and --quiet options")
        return False

    # Validate command-specific arguments
    if args.command in ["playlist", "pl"]:
        return PlaylistCommand.validate_args(args)
    elif args.command in ["backup", "bk"]:
        return BackupCommand.validate_args(args)
    elif args.command in ["metadata", "meta"]:
        return MetadataCommand.validate_args(args)

    return True


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        argv: Command-line arguments (uses sys.argv if None)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Handle case where no command is provided
    if not args.command:
        parser.print_help()
        return 1

    try:
        # Load configuration
        config = load_configuration(args)

        # Set up logging
        setup_logging_from_config(config)

        # Validate arguments
        if not validate_args(args):
            return 1

        # Log startup information
        logger.info(f"Starting Rekordbox Smart Playlists CLI")
        logger.debug(f"Command: {args.command}")
        logger.debug(f"Dry run: {config.dry_run}")

        # Execute command
        exit_code = 0

        if args.command in ["playlist", "pl"]:
            playlist_command = PlaylistCommand(config)
            exit_code = playlist_command.execute(args)
        elif args.command in ["backup", "bk"]:
            backup_command = BackupCommand(config)
            exit_code = backup_command.execute(args)
        elif args.command in ["metadata", "meta"]:
            metadata_command = MetadataCommand(config)
            exit_code = metadata_command.execute(args)
        else:
            logger.error(f"Unknown command: {args.command}")
            exit_code = 1

        if exit_code == 0:
            logger.info("Operation completed successfully")
        else:
            logger.error("Operation failed")

        return exit_code

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.debug("Full traceback:", exc_info=True)
        return 1


def cli_main() -> None:
    """Entry point for console script."""
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
