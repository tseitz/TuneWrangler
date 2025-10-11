"""
Rekordbox Metadata Fixer

This script helps synchronize metadata between Rekordbox database and filenames.
It can update database metadata based on filename format or rename files to match database metadata.
The script automatically creates a backup before making any changes to your Rekordbox database.

Usage Examples:
    # Interactive mode - prompt for each file
    python fix_rekordbox_metadata.py

    # Preview what would be changed (dry run)
    python fix_rekordbox_metadata.py --preview --dry-run

    # Batch mode - use database metadata for all files
    python fix_rekordbox_metadata.py --batch-database --dry-run

    # Batch mode - use filename metadata for all files
    python fix_rekordbox_metadata.py --batch-filename --dry-run

    # Update filenames to match database metadata
    python fix_rekordbox_metadata.py --update-filenames --dry-run

    # List available backups
    python fix_rekordbox_metadata.py --list-backups

    # Skip automatic backup (use with caution)
    python fix_rekordbox_metadata.py --skip-backup

    # Specify custom collection path
    python fix_rekordbox_metadata.py --collection-path /path/to/music

    # Use configuration file
    python fix_rekordbox_metadata.py --config config.json

Backup and Recovery:
    - The script automatically creates a backup before making changes
    - Backups are stored in: /Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Rekordbox DB Backup/
    - Use --list-backups to see available backups
    - Use restore_rekordbox_db() from app.py to restore from backup

Filename Format:
    The script expects filenames in the format:
    - [artist] - [title].ext
    - [artist] - [album] - [title].ext

Configuration File:
    Create a config.json file to customize settings:
    {
        "collection_path": "/path/to/music",
        "dry_run": true,
        "skip_backup": false,
        "audio_extensions": [".mp3", ".wav", ".flac"],
        "progress_interval": 10
    }
"""

from pathlib import Path
from pyrekordbox import Rekordbox6Database
from typing import Optional, Tuple, List, Dict, Any
import logging
import argparse
import json
import unicodedata

# Import backup functions from the new backup module
from rekordbox_backup import backup_rekordbox_db, list_backups

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class RekordboxMetadataFixer:
    def __init__(
        self,
        collection_path: str = "/Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Collection/",
        dry_run: bool = True,
    ):
        self.collection_path = Path(collection_path)

        # Validate collection path exists
        if not self.collection_path.exists():
            raise ValueError(f"Collection path does not exist: {self.collection_path}")

        try:
            self.db = Rekordbox6Database()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Rekordbox database: {e}")

        self.dry_run = dry_run
        self.skip_backup = False

    def normalize_string(self, text: str) -> str:
        """Normalize Unicode string for consistent comparison"""
        if not text:
            return ""
        return unicodedata.normalize("NFC", str(text).lower().strip())

    def parse_filename(self, filename: str) -> Optional[Tuple[str, str, Optional[str]]]:
        """
        Parse filename in format [artist] - [title] or [artist] - [album] - [title]
        Returns (artist, title, album) where album can be None
        """
        # Remove file extension
        name_without_ext = Path(filename).stem

        # Split by " - " to separate components
        parts = name_without_ext.split(" - ")

        if len(parts) == 2:
            # Format: [artist] - [title]
            artist, title = parts
            return artist.strip(), title.strip(), None
        elif len(parts) == 3:
            # Format: [artist] - [album] - [title]
            artist, album, title = parts
            return artist.strip(), title.strip(), album.strip()
        else:
            logger.warning(f"Could not parse filename format: {filename}")
            return None

    def get_audio_files(self) -> List[Path]:
        """Get all audio files from the collection directory"""
        audio_files: List[Path] = []

        if not self.collection_path.exists():
            logger.error(f"Collection path does not exist: {self.collection_path}")
            return audio_files

        for file_path in self.collection_path.rglob("*"):
            if file_path.is_file() and file_path.name != ".DS_Store":
                audio_files.append(file_path)

        logger.info(f"Found {len(audio_files)} audio files in collection")
        return audio_files

    def preview_changes(self, max_files: int = 10) -> None:
        """Preview what changes would be made (for testing)"""
        audio_files = self.get_audio_files()

        logger.info(f"Preview of first {max_files} files that would be processed:")
        logger.info("=" * 80)

        for i, file_path in enumerate(audio_files[:max_files]):
            filename = file_path.name
            parsed = self.parse_filename(filename)

            if parsed:
                artist, title, album = parsed
                content = self.find_content_by_filename(filename)

                if content:
                    current_artist = (
                        getattr(content.Artist, "Name", "Unknown")
                        if hasattr(content, "Artist") and content.Artist
                        else "Unknown"
                    )
                    current_title = getattr(content, "Title", "Unknown")
                    if current_title:
                        current_title = current_title.strip()
                    current_album = getattr(content, "AlbumName", "Unknown")
                    if current_album:
                        current_album = current_album.strip()

                    logger.info(f"{i+1}. {filename}")
                    logger.info(
                        f"   Parsed: Artist='{artist}', Title='{title}'"
                        + (f", Album='{album}'" if album else "")
                    )
                    logger.info(
                        f"   Current: Artist='{current_artist}', Title='{current_title}'"
                        + (f", Album='{current_album}'" if current_album else "")
                    )
                    logger.info(
                        f"   Would update: {'Yes' if current_artist != artist or current_title != title else 'No'}"
                    )
                else:
                    logger.info(f"{i+1}. {filename} - NOT FOUND IN DATABASE")
            else:
                logger.info(f"{i+1}. {filename} - PARSE ERROR")

            logger.info("")

        if len(audio_files) > max_files:
            logger.info(f"... and {len(audio_files) - max_files} more files")

    def find_content_by_filename(self, filename: str) -> Optional[Any]:
        """Find content in Rekordbox database by filename"""
        try:
            # Try to find by exact filename match
            content = self.db.get_content(FileNameL=filename).one_or_none()
            if content:
                return content

            # If not found, try case-insensitive search
            parsed = self.parse_filename(filename)
            if parsed:
                artist_name, title, _ = parsed
                content = self.db.get_content(ArtistName=artist_name, Title=title).one_or_none()
                if content:
                    # self.update_database_filename(content, filename)
                    return content

                # If not found, try to search by title
                all_content = self.db.get_content()
                for content in all_content:
                    if (
                        content.ArtistName
                        and self.normalize_string(content.ArtistName)
                        == self.normalize_string(artist_name)
                        and self.normalize_string(content.Title) == self.normalize_string(title)
                    ):
                        # self.update_database_filename(content, filename)
                        return content

            logger.info(f"Could not find content for {filename} by filename")
            return None
        except Exception as e:
            logger.error(f"Error finding content for {filename}: {e}")
            # TODO: get content differently and update filename
            return None

    def prompt_user_choice(
        self,
        filename: str,
        db_artist: str,
        db_title: str,
        db_album: str,
        file_artist: str,
        file_title: str,
        file_album: Optional[str],
    ) -> str:
        """
        Prompt user to choose between database or filename as source of truth
        Returns: 'database', 'filename', 'skip', or 'end'
        """
        print(f"\n{'='*80}")
        print(f"File: {filename}")
        print(f"{'='*80}")
        print(f"Database metadata:")
        print(f"  Artist: '{db_artist}'")
        print(f"  Title: '{db_title}'")
        print(f"  Album: '{db_album}'")
        print(f"\nFilename metadata:")
        print(f"  Artist: '{file_artist}'")
        print(f"  Title: '{file_title}'")
        print(f"  Album: '{file_album}'" if file_album else "  Album: None")
        print(f"\nOptions:")
        print(f"  [d] Use database metadata (rename file to match database)")
        print(f"  [f] Use filename metadata (update database to match filename)")
        print(f"  [s] Skip this file")
        print(f"  [e] End processing and commit all changes so far")

        while True:
            choice = input("\nChoose option (d/f/s/e): ").lower().strip()
            if choice in ["d", "database"]:
                return "database"
            elif choice in ["f", "filename"]:
                return "filename"
            elif choice in ["s", "skip"]:
                return "skip"
            elif choice in ["e", "end"]:
                return "end"
            else:
                print("Invalid choice. Please enter 'd', 'f', 's', or 'e'.")

    def update_filename_from_database(self, content: Any, file_path: Path) -> bool:
        """Update filename based on database metadata"""
        try:
            db_artist = (
                getattr(content.Artist, "Name", "Unknown")
                if hasattr(content, "Artist") and content.Artist
                else "Unknown"
            )
            db_title = getattr(content, "Title", "Unknown")
            db_album = getattr(content, "AlbumName", "Unknown")

            # Construct new filename
            if db_album and db_album != "Unknown":
                new_filename = f"{db_artist.strip()} - {db_album.strip()} - {db_title.strip()}{file_path.suffix}"
            else:
                new_filename = f"{db_artist.strip()} - {db_title.strip()}{file_path.suffix}"

            new_file_path = file_path.parent / new_filename

            if self.dry_run:
                logger.info(f"[DRY RUN] Would rename {file_path.name} -> {new_filename}")
                logger.info(
                    f"[DRY RUN] Would update database path: {content.FolderPath} -> {new_file_path}"
                )
                return True

            # Rename the physical file
            file_path.rename(new_file_path)
            logger.info(f"Renamed {file_path.name} -> {new_filename}")

            # Update the database path using pyrekordbox method
            # update_content_filename expects just the filename, not the full path
            self.update_database_filename(content, new_filename)

            return True
        except Exception as e:
            logger.error(f"Error renaming file {file_path.name}: {e}")
            return False

    def update_database_filename(self, content: Any, new_filename: str) -> bool:
        """Update the full path of a content item in the database"""
        try:
            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would update database filename: {content.FileNameL} -> {new_filename}"
                )
                return True

            previous_filename = content.FileNameL
            self.db.update_content_filename(
                content, new_filename, save=True, check_path=False, commit=False
            )
            content.OrgFolderPath = f"{str(self.collection_path)}/{new_filename}"
            logger.info(f"Updated database filename from {previous_filename} to {new_filename}")
            return True

        except Exception as e:
            logger.error(f"Error updating database path for {content.FileNameL}: {e}")
            return False

    def get_or_create_artist(self, artist_name: str) -> Optional[Any]:
        """Get existing artist or create new one"""
        try:
            # First try to find existing artist by name
            existing_artist = self.db.get_artist(Name=artist_name).one_or_none()
            if existing_artist:
                return existing_artist

            # If not found, create new artist
            if not self.dry_run:
                new_artist = self.db.add_artist(artist_name)
                logger.info(f"Created new artist: {artist_name}")
                return new_artist
            else:
                logger.info(f"[DRY RUN] Would create new artist: {artist_name}")
                return None

        except Exception as e:
            logger.error(f"Error getting/creating artist '{artist_name}': {e}")
            return None

    def get_or_create_album(self, album_name: str) -> Optional[Any]:
        """Get existing album or create new one"""
        try:
            # First try to find existing album by name
            existing_albums = self.db.get_album(Name=album_name).all()
            if len(existing_albums) > 0:
                logger.info(f"Found {len(existing_albums)} existing albums for {album_name}")
                return existing_albums[0]

            # If not found, create new album
            if not self.dry_run:
                new_album = self.db.add_album(album_name)
                logger.info(f"Created new album: {album_name}")
                return new_album
            else:
                logger.info(f"[DRY RUN] Would create new album: {album_name}")
                return None

        except Exception as e:
            logger.error(f"Error getting/creating album '{album_name}': {e}")
            return None

    def update_content_metadata(
        self, content: Any, artist: str, title: str, album: Optional[str] = None
    ) -> None:
        """Update content metadata in the database"""
        try:
            # Log what we're about to update
            current_artist = (
                getattr(content.Artist, "Name", "Unknown")
                if hasattr(content, "Artist") and content.Artist
                else "Unknown"
            )
            current_title = getattr(content, "Title", "Unknown")
            if current_title:
                current_title = current_title.strip()

            if self.dry_run:
                logger.info(f"[DRY RUN] Would update {content.FileNameL}:")
                logger.info(f"  Artist: '{current_artist}' -> '{artist}'")
                logger.info(f"  Title: '{current_title}' -> '{title}'")
                if album:
                    current_album = getattr(content, "Album", "Unknown")
                    if current_album:
                        current_album = current_album.strip()
                    logger.info(f"  Album: '{current_album}' -> '{album}'")
                return

            # Handle artist - get or create
            artist_obj = self.get_or_create_artist(artist)
            if artist_obj:
                content.Artist = artist_obj
            else:
                logger.warning(f"Could not get/create artist '{artist}' for {content.FileNameL}")

            # Update title
            if hasattr(content, "Title"):
                content.Title = title
            else:
                logger.warning(
                    f"Could not update title for {content.FileNameL}: Title attribute not found"
                )

            # Handle album - get or create
            if album:
                album_obj = self.get_or_create_album(album)
                if album_obj:
                    content.Album = album_obj
                else:
                    logger.warning(f"Could not get/create album '{album}' for {content.FileNameL}")

        except Exception as e:
            logger.error(f"Error updating metadata for {content.FileNameL}: {e}")

    def update_filenames_from_database(self) -> None:
        """Update filenames to match database metadata"""
        audio_files = self.get_audio_files()

        updated_count = 0
        not_found_count = 0
        error_count = 0

        for file_path in audio_files:
            filename = file_path.name

            # Find corresponding content in Rekordbox database
            content = self.find_content_by_filename(filename)
            if not content:
                logger.warning(f"Could not find content in database for: {filename}")
                not_found_count += 1
                continue

            # Update filename based on database metadata
            if self.update_filename_from_database(content, file_path):
                updated_count += 1
            else:
                error_count += 1

        # Summary
        logger.info(f"Filename update complete!")
        logger.info(f"Files updated: {updated_count}")
        logger.info(f"Files not found in database: {not_found_count}")
        logger.info(f"Files with errors: {error_count}")
        logger.info(f"Total files processed: {len(audio_files)}")

    def generate_statistics(
        self,
        updated_count: int,
        not_found_count: int,
        parse_error_count: int,
        skipped_count: int,
        total_files: int,
    ) -> Dict[str, Any]:
        """Generate detailed statistics about the processing run"""
        processed_count = updated_count + not_found_count + parse_error_count + skipped_count

        return {
            "total_files": total_files,
            "processed_files": processed_count,
            "updated_files": updated_count,
            "not_found_files": not_found_count,
            "parse_error_files": parse_error_count,
            "skipped_files": skipped_count,
            "dry_run": self.dry_run,
        }

    def print_summary(self, stats: Dict[str, Any]) -> None:
        """Print a formatted summary of the processing results"""
        print("\n" + "=" * 60)
        print("PROCESSING SUMMARY")
        print("=" * 60)
        print(f"Total files found: {stats['total_files']}")
        print(f"Files processed: {stats['processed_files']}")
        print(f"Files updated: {stats['updated_files']}")
        print(f"Files not found in database: {stats['not_found_files']}")
        print(f"Files with parsing errors: {stats['parse_error_files']}")
        print(f"Files skipped: {stats['skipped_files']}")
        print(f"Mode: {'DRY RUN' if stats['dry_run'] else 'LIVE'}")
        print("=" * 60)

    def process_collection(self, batch_mode: Optional[str] = None) -> None:
        """Main method to process the entire collection"""
        # Create backup before making changes (unless in dry run mode or skip-backup is specified)
        if not self.dry_run and not getattr(self, "skip_backup", False):
            logger.info("Creating backup before making changes...")
            backup_path = backup_rekordbox_db()
            if backup_path:
                logger.info(f"✓ Backup created successfully: {backup_path}")
                logger.info("You can restore from this backup if needed.")
            else:
                logger.error("❌ Failed to create backup. Aborting to prevent data loss.")
                return
        elif self.dry_run:
            logger.info("Dry run mode - no backup needed")
        elif getattr(self, "skip_backup", False):
            logger.warning("⚠️  Skipping backup as requested (use with caution)")

        audio_files = self.get_audio_files()
        total_files = len(audio_files)

        if total_files == 0:
            logger.warning("No audio files found in collection directory")
            return

        logger.info(f"Processing {total_files} audio files")

        updated_count = 0
        not_found_count = 0
        parse_error_count = 0
        skipped_count = 0

        for i, file_path in enumerate(audio_files, 1):
            filename = file_path.name

            # Show progress every 10 files
            if i % 10 == 0 or i == total_files:
                logger.info(f"Progress: {i}/{total_files} files processed")

            # Parse filename to extract metadata
            parsed = self.parse_filename(filename)
            if not parsed:
                parse_error_count += 1
                continue

            file_artist, file_title, file_album = parsed

            # Find corresponding content in Rekordbox database
            content = self.find_content_by_filename(filename)
            if not content:
                logger.warning(f"Could not find content in database for: {filename}")
                not_found_count += 1
                continue

            # Get current database metadata
            db_artist = (
                getattr(content.Artist, "Name", "Unknown")
                if hasattr(content, "Artist") and content.Artist
                else "Unknown"
            )
            db_title = getattr(content, "Title", "Unknown")
            db_album = getattr(content, "AlbumName", "Unknown")

            # Check if metadata differs
            if (
                self.normalize_string(db_artist) == self.normalize_string(file_artist)
                and self.normalize_string(db_title) == self.normalize_string(file_title)
                and (
                    file_album is None
                    or self.normalize_string(db_album) == self.normalize_string(file_album)
                )
            ):
                # No changes needed
                continue

            # Determine what to do based on batch mode or user choice
            if batch_mode == "database":
                choice = "database"
            elif batch_mode == "filename":
                choice = "filename"
            else:
                # Interactive mode - prompt user
                choice = self.prompt_user_choice(
                    filename,
                    db_artist,
                    db_title,
                    db_album,
                    file_artist,
                    file_title,
                    file_album,
                )

            if choice == "skip":
                skipped_count += 1
                continue
            elif choice == "database":
                # Use database metadata - update filename to match database
                if self.update_filename_from_database(content, file_path):
                    updated_count += 1
            elif choice == "filename":
                # Update database with filename metadata
                self.update_content_metadata(content, file_artist, file_title, file_album)
                updated_count += 1
            elif choice == "end":
                logger.info("Ending processing and committing all changes so far.")
                if not self.dry_run and updated_count > 0:
                    self.db.commit()
                    logger.info("Committed all database changes")
                return  # Exit the method entirely

        if not self.dry_run and updated_count > 0:
            logger.info("Committing all database changes")
            self.db.commit()

        # Summary
        stats = self.generate_statistics(
            updated_count,
            not_found_count,
            parse_error_count,
            skipped_count,
            total_files,
        )
        self.print_summary(stats)

        # Log summary for logging output
        logger.info(f"Processing complete!")
        logger.info(f"Files updated: {updated_count}")
        logger.info(f"Files not found in database: {not_found_count}")
        logger.info(f"Files with parsing errors: {parse_error_count}")
        logger.info(f"Files skipped: {skipped_count}")
        logger.info(f"Total files processed: {total_files}")

    def cleanup(self) -> None:
        """Clean up resources and close database connection"""
        try:
            if hasattr(self, "db"):
                self.db.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.warning(f"Error closing database connection: {e}")

    def __enter__(self) -> "RekordboxMetadataFixer":
        """Context manager entry"""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - cleanup resources"""
        self.cleanup()


def main() -> None:
    """Main function to run the metadata fixer"""
    parser = argparse.ArgumentParser(description="Fix Rekordbox metadata based on filename format")
    parser.add_argument(
        "--collection-path",
        default="/Users/tseitz/Dropbox/DJ/Dane Dubz DJ Music/Collection/",
        help="Path to your music collection",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--preview",
        "-p",
        action="store_true",
        help="Show preview of changes without processing",
    )
    parser.add_argument(
        "--preview-count",
        type=int,
        default=10,
        help="Number of files to preview (default: 10)",
    )
    parser.add_argument(
        "--batch-database",
        action="store_true",
        help="Use database metadata as source of truth for all files (batch mode)",
    )
    parser.add_argument(
        "--batch-filename",
        action="store_true",
        help="Use filename metadata as source of truth for all files (batch mode)",
    )
    parser.add_argument(
        "--update-filenames",
        action="store_true",
        help="Update filenames to match database metadata (reverse operation)",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip automatic backup before making changes (use with caution)",
    )
    parser.add_argument(
        "--list-backups",
        action="store_true",
        help="List available backups and exit",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to a JSON configuration file",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.batch_database and args.batch_filename:
        parser.error("Cannot use both --batch-database and --batch-filename")

    if args.update_filenames and (args.batch_database or args.batch_filename):
        parser.error("Cannot use --update-filenames with batch options")

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Starting metadata fixer...")
    logger.info(f"Collection path: {args.collection_path}")
    logger.info(f"Dry run mode: {args.dry_run}")

    # Determine batch mode
    batch_mode = None
    if args.batch_database:
        batch_mode = "database"
        logger.info("Batch mode: Using database metadata as source of truth")
    elif args.batch_filename:
        batch_mode = "filename"
        logger.info("Batch mode: Using filename metadata as source of truth")

    # Load configuration if provided
    if args.config:
        try:
            with open(args.config, "r") as f:
                config = json.load(f)
                if "collection_path" in config:
                    args.collection_path = config["collection_path"]
                if "dry_run" in config:
                    args.dry_run = config["dry_run"]
                if "skip_backup" in config:
                    args.skip_backup = config["skip_backup"]
                if "audio_extensions" in config:
                    args.audio_extensions = set(config["audio_extensions"])
                if "progress_interval" in config:
                    args.progress_interval = config["progress_interval"]
        except FileNotFoundError:
            logger.warning(f"Configuration file not found: {args.config}")
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON from configuration file: {args.config}")
        except Exception as e:
            logger.error(f"Error loading configuration file {args.config}: {e}")

    try:
        with RekordboxMetadataFixer(
            collection_path=args.collection_path, dry_run=args.dry_run
        ) as fixer:
            fixer.skip_backup = args.skip_backup

            if args.list_backups:
                list_backups()
            elif args.preview:
                fixer.preview_changes(max_files=args.preview_count)
            elif args.update_filenames:
                fixer.update_filenames_from_database()
            else:
                fixer.process_collection(batch_mode=batch_mode)
    except ValueError as e:
        logger.error(f"Error: {e}")
    except RuntimeError as e:
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    main()
