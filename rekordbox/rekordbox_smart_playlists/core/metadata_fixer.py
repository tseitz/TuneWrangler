"""
Metadata synchronization for Rekordbox and file system.

Handles synchronization of metadata between Rekordbox database and file names,
providing options to use either source as the authority.
"""

import unicodedata
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum

from ..utils.logging import (
    get_logger,
    log_success,
    log_error,
    log_exception,
    create_progress_logger,
)
from ..utils.validation import validate_filename_format, validate_file_path
from ..utils.file_utils import find_files, safe_move
from .database import RekordboxDatabase, DatabaseError
from .backup_manager import BackupManager
from .config import Config

logger = get_logger(__name__)


class MetadataSource(Enum):
    """Source of metadata authority."""

    DATABASE = "database"
    FILENAME = "filename"


class MetadataAction(Enum):
    """Action to take for metadata discrepancy."""

    UPDATE_DATABASE = "update_database"
    UPDATE_FILENAME = "update_filename"
    SKIP = "skip"


@dataclass
class MetadataComparison:
    """Comparison of metadata between database and filename."""

    filename: str
    file_path: Path

    # Database metadata
    db_artist: str
    db_title: str
    db_album: str

    # Filename metadata
    file_artist: str
    file_title: str
    file_album: Optional[str]

    # Comparison result
    matches: bool
    needs_update: bool
    content_object: Optional[Any] = None


@dataclass
class MetadataFixResult:
    """Result of metadata fix operation."""

    filename: str
    success: bool
    action_taken: MetadataAction
    error_message: Optional[str] = None
    old_values: Optional[Dict[str, str]] = None
    new_values: Optional[Dict[str, str]] = None


class MetadataFixer:
    """
    Handles metadata synchronization between Rekordbox database and file system.
    """

    def __init__(self, database: RekordboxDatabase, config: Config):
        """
        Initialize metadata fixer.

        Args:
            database: Database connection instance
            config: Configuration object
        """
        self.db = database
        self.config = config
        self.collection_path = Path(config.collection_path)

        # Validate collection path
        if not self.collection_path.exists():
            raise ValueError(f"Collection path does not exist: {self.collection_path}")

    def fix_metadata_interactive(self) -> List[MetadataFixResult]:
        """
        Fix metadata with interactive prompts for each discrepancy.

        Returns:
            List of metadata fix results
        """
        logger.info("Starting interactive metadata fixing...")

        # Create backup if not in dry run mode
        if not self.config.dry_run and self.config.backup_before_changes:
            backup_manager = BackupManager(self.config)
            backup_path = backup_manager.create_backup("before_metadata_fix")
            if backup_path:
                log_success(logger, f"Backup created: {backup_path}")
            else:
                log_error(logger, "Failed to create backup, aborting")
                return []

        audio_files = self._get_audio_files()
        results = []

        progress = create_progress_logger(len(audio_files), "Processing audio files")

        for file_path in audio_files:
            try:
                comparison = self._compare_metadata(file_path)
                if not comparison:
                    continue  # Skip files that can't be processed

                if not comparison.needs_update:
                    continue  # Skip files that don't need updates

                # Prompt user for action
                action = self._prompt_user_action(comparison)

                if action == MetadataAction.SKIP:
                    result = MetadataFixResult(
                        filename=comparison.filename,
                        success=True,
                        action_taken=MetadataAction.SKIP,
                    )
                elif action == MetadataAction.UPDATE_DATABASE:
                    result = self._update_database_metadata(comparison)
                elif action == MetadataAction.UPDATE_FILENAME:
                    result = self._update_filename_metadata(comparison)
                else:
                    # User chose to end processing
                    break

                results.append(result)
                progress.update(message=f"Processed {comparison.filename}")

            except Exception as e:
                log_exception(logger, e, f"processing {file_path.name}")
                result = MetadataFixResult(
                    filename=file_path.name,
                    success=False,
                    action_taken=MetadataAction.SKIP,
                    error_message=str(e),
                )
                results.append(result)

        progress.finish("Interactive metadata fixing completed")

        # Commit database changes if any were made
        if not self.config.dry_run:
            db_updates = [
                r
                for r in results
                if r.action_taken == MetadataAction.UPDATE_DATABASE and r.success
            ]
            if db_updates:
                try:
                    self.db.commit()
                    log_success(logger, f"Committed {len(db_updates)} database updates")
                except DatabaseError as e:
                    log_error(logger, f"Failed to commit database changes: {e}")

        self._print_results_summary(results)
        return results

    def fix_metadata_batch(self, source: MetadataSource) -> List[MetadataFixResult]:
        """
        Fix metadata in batch mode using specified source as authority.

        Args:
            source: Source to use as authority (database or filename)

        Returns:
            List of metadata fix results
        """
        logger.info(f"Starting batch metadata fixing (source: {source.value})...")

        # Create backup if not in dry run mode
        if not self.config.dry_run and self.config.backup_before_changes:
            backup_manager = BackupManager(self.config)
            backup_path = backup_manager.create_backup("before_metadata_fix")
            if backup_path:
                log_success(logger, f"Backup created: {backup_path}")
            else:
                log_error(logger, "Failed to create backup, aborting")
                return []

        audio_files = self._get_audio_files()
        results = []

        progress = create_progress_logger(
            len(audio_files), f"Processing files ({source.value} authority)"
        )

        for file_path in audio_files:
            try:
                comparison = self._compare_metadata(file_path)
                if not comparison or not comparison.needs_update:
                    continue

                # Apply batch action based on source
                if source == MetadataSource.DATABASE:
                    result = self._update_filename_metadata(comparison)
                else:  # MetadataSource.FILENAME
                    result = self._update_database_metadata(comparison)

                results.append(result)
                progress.update(message=f"Processed {comparison.filename}")

            except Exception as e:
                log_exception(logger, e, f"processing {file_path.name}")
                result = MetadataFixResult(
                    filename=file_path.name,
                    success=False,
                    action_taken=MetadataAction.SKIP,
                    error_message=str(e),
                )
                results.append(result)

        progress.finish("Batch metadata fixing completed")

        # Commit database changes if any were made
        if not self.config.dry_run:
            db_updates = [
                r
                for r in results
                if r.action_taken == MetadataAction.UPDATE_DATABASE and r.success
            ]
            if db_updates:
                try:
                    self.db.commit()
                    log_success(logger, f"Committed {len(db_updates)} database updates")
                except DatabaseError as e:
                    log_error(logger, f"Failed to commit database changes: {e}")

        self._print_results_summary(results)
        return results

    def preview_metadata_changes(self, max_files: int = 20) -> List[MetadataComparison]:
        """
        Preview metadata discrepancies without making changes.

        Args:
            max_files: Maximum number of files to preview

        Returns:
            List of metadata comparisons
        """
        logger.info(f"Previewing metadata discrepancies (max {max_files} files)...")

        audio_files = self._get_audio_files()
        comparisons = []

        for i, file_path in enumerate(audio_files):
            if i >= max_files:
                break

            try:
                comparison = self._compare_metadata(file_path)
                if comparison and comparison.needs_update:
                    comparisons.append(comparison)
            except Exception as e:
                log_exception(logger, e, f"comparing metadata for {file_path.name}")

        # Print preview
        self._print_preview(comparisons)
        return comparisons

    def _get_audio_files(self) -> List[Path]:
        """Get list of audio files from collection directory."""
        patterns = [f"*{ext}" for ext in self.config.audio_extensions]
        return find_files(self.collection_path, patterns, recursive=True)

    def _compare_metadata(self, file_path: Path) -> Optional[MetadataComparison]:
        """
        Compare metadata between database and filename.

        Args:
            file_path: Path to audio file

        Returns:
            MetadataComparison object or None if comparison failed
        """
        filename = file_path.name

        # Parse filename
        parsed = self._parse_filename(filename)
        if not parsed:
            logger.debug(f"Could not parse filename: {filename}")
            return None

        file_artist, file_title, file_album = parsed

        # Find content in database
        content = self.db.find_content_by_filename(filename)
        if not content:
            logger.debug(f"Content not found in database: {filename}")
            return None

        # Get database metadata
        db_artist = (
            getattr(content.Artist, "Name", "Unknown")
            if hasattr(content, "Artist") and content.Artist
            else "Unknown"
        )
        db_title = getattr(content, "Title", "Unknown")
        db_album = getattr(content, "AlbumName", "Unknown")

        # Compare metadata
        artist_matches = self._normalize_string(db_artist) == self._normalize_string(
            file_artist
        )
        title_matches = self._normalize_string(db_title) == self._normalize_string(
            file_title
        )
        album_matches = file_album is None or self._normalize_string(
            db_album
        ) == self._normalize_string(file_album or "")

        matches = artist_matches and title_matches and album_matches

        return MetadataComparison(
            filename=filename,
            file_path=file_path,
            db_artist=db_artist,
            db_title=db_title,
            db_album=db_album,
            file_artist=file_artist,
            file_title=file_title,
            file_album=file_album,
            matches=matches,
            needs_update=not matches,
            content_object=content,
        )

    def _parse_filename(
        self, filename: str
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """
        Parse filename to extract artist, title, and optional album.

        Args:
            filename: Filename to parse

        Returns:
            Tuple of (artist, title, album) or None if parsing failed
        """
        stem = Path(filename).stem

        # Split by " - " separator
        parts = stem.split(" - ")

        if len(parts) == 2:
            # Format: Artist - Title
            return parts[0].strip(), parts[1].strip(), None
        elif len(parts) == 3:
            # Format: Artist - Album - Title
            return parts[0].strip(), parts[2].strip(), parts[1].strip()
        else:
            return None

    def _normalize_string(self, text: str) -> str:
        """Normalize string for comparison."""
        if not text:
            return ""
        return unicodedata.normalize("NFC", str(text).lower().strip())

    def _prompt_user_action(
        self, comparison: MetadataComparison
    ) -> Union[MetadataAction, str]:
        """
        Prompt user to choose action for metadata discrepancy.

        Args:
            comparison: Metadata comparison object

        Returns:
            MetadataAction or "end" to stop processing
        """
        print(f"\n{'='*80}")
        print(f"File: {comparison.filename}")
        print(f"{'='*80}")
        print(f"Database metadata:")
        print(f"  Artist: '{comparison.db_artist}'")
        print(f"  Title:  '{comparison.db_title}'")
        print(f"  Album:  '{comparison.db_album}'")
        print(f"\nFilename metadata:")
        print(f"  Artist: '{comparison.file_artist}'")
        print(f"  Title:  '{comparison.file_title}'")
        print(f"  Album:  '{comparison.file_album or 'None'}'")
        print(f"\nOptions:")
        print(f"  [d] Use database metadata (rename file)")
        print(f"  [f] Use filename metadata (update database)")
        print(f"  [s] Skip this file")
        print(f"  [e] End processing")

        while True:
            choice = input("\nChoose option (d/f/s/e): ").lower().strip()
            if choice in ["d", "database"]:
                return MetadataAction.UPDATE_FILENAME
            elif choice in ["f", "filename"]:
                return MetadataAction.UPDATE_DATABASE
            elif choice in ["s", "skip"]:
                return MetadataAction.SKIP
            elif choice in ["e", "end"]:
                return "end"
            else:
                print("Invalid choice. Please enter 'd', 'f', 's', or 'e'.")

    def _update_database_metadata(
        self, comparison: MetadataComparison
    ) -> MetadataFixResult:
        """
        Update database metadata to match filename.

        Args:
            comparison: Metadata comparison object

        Returns:
            MetadataFixResult
        """
        content = comparison.content_object
        if not content:
            return MetadataFixResult(
                filename=comparison.filename,
                success=False,
                action_taken=MetadataAction.UPDATE_DATABASE,
                error_message="Content object not available",
            )

        old_values = {
            "artist": comparison.db_artist,
            "title": comparison.db_title,
            "album": comparison.db_album,
        }

        new_values = {
            "artist": comparison.file_artist,
            "title": comparison.file_title,
            "album": comparison.file_album or "",
        }

        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would update database for {comparison.filename}")
            logger.info(
                f"  Artist: '{old_values['artist']}' -> '{new_values['artist']}'"
            )
            logger.info(f"  Title: '{old_values['title']}' -> '{new_values['title']}'")
            if comparison.file_album:
                logger.info(
                    f"  Album: '{old_values['album']}' -> '{new_values['album']}'"
                )

            return MetadataFixResult(
                filename=comparison.filename,
                success=True,
                action_taken=MetadataAction.UPDATE_DATABASE,
                old_values=old_values,
                new_values=new_values,
            )

        try:
            # Update artist
            artist_obj = self.db.get_artist_by_name(comparison.file_artist)
            if not artist_obj:
                artist_obj = self.db.create_artist(comparison.file_artist)

            if artist_obj:
                content.Artist = artist_obj

            # Update title
            content.Title = comparison.file_title

            # Update album if provided
            if comparison.file_album:
                album_obj = self.db.get_album_by_name(comparison.file_album)
                if not album_obj:
                    album_obj = self.db.create_album(comparison.file_album)

                if album_obj:
                    content.Album = album_obj

            log_success(logger, f"Updated database metadata for {comparison.filename}")

            return MetadataFixResult(
                filename=comparison.filename,
                success=True,
                action_taken=MetadataAction.UPDATE_DATABASE,
                old_values=old_values,
                new_values=new_values,
            )

        except Exception as e:
            log_exception(
                logger, e, f"updating database metadata for {comparison.filename}"
            )
            return MetadataFixResult(
                filename=comparison.filename,
                success=False,
                action_taken=MetadataAction.UPDATE_DATABASE,
                error_message=str(e),
                old_values=old_values,
                new_values=new_values,
            )

    def _update_filename_metadata(
        self, comparison: MetadataComparison
    ) -> MetadataFixResult:
        """
        Update filename to match database metadata.

        Args:
            comparison: Metadata comparison object

        Returns:
            MetadataFixResult
        """
        old_values = {"filename": comparison.filename}

        # Construct new filename
        if comparison.db_album and comparison.db_album != "Unknown":
            new_filename = f"{comparison.db_artist} - {comparison.db_album} - {comparison.db_title}{comparison.file_path.suffix}"
        else:
            new_filename = f"{comparison.db_artist} - {comparison.db_title}{comparison.file_path.suffix}"

        new_values = {"filename": new_filename}

        if self.config.dry_run:
            logger.info(
                f"[DRY RUN] Would rename {comparison.filename} -> {new_filename}"
            )

            return MetadataFixResult(
                filename=comparison.filename,
                success=True,
                action_taken=MetadataAction.UPDATE_FILENAME,
                old_values=old_values,
                new_values=new_values,
            )

        try:
            new_file_path = comparison.file_path.parent / new_filename

            # Rename file
            if safe_move(comparison.file_path, new_file_path):
                # Update database filename reference
                content = comparison.content_object
                if content:
                    try:
                        # Update database filename reference
                        if hasattr(self.db._db, "update_content_filename"):
                            self.db._db.update_content_filename(
                                content,
                                new_filename,
                                save=True,
                                check_path=False,
                                commit=False,
                            )
                        log_success(
                            logger, f"Renamed {comparison.filename} -> {new_filename}"
                        )
                    except Exception as e:
                        log_exception(
                            logger, e, f"updating database filename reference"
                        )
                        # File was renamed but database update failed
                        # Try to rename back
                        safe_move(new_file_path, comparison.file_path)
                        raise

                return MetadataFixResult(
                    filename=comparison.filename,
                    success=True,
                    action_taken=MetadataAction.UPDATE_FILENAME,
                    old_values=old_values,
                    new_values=new_values,
                )
            else:
                return MetadataFixResult(
                    filename=comparison.filename,
                    success=False,
                    action_taken=MetadataAction.UPDATE_FILENAME,
                    error_message="Failed to rename file",
                    old_values=old_values,
                    new_values=new_values,
                )

        except Exception as e:
            log_exception(logger, e, f"updating filename for {comparison.filename}")
            return MetadataFixResult(
                filename=comparison.filename,
                success=False,
                action_taken=MetadataAction.UPDATE_FILENAME,
                error_message=str(e),
                old_values=old_values,
                new_values=new_values,
            )

    def _print_preview(self, comparisons: List[MetadataComparison]) -> None:
        """Print preview of metadata discrepancies."""
        if not comparisons:
            logger.info("No metadata discrepancies found in preview")
            return

        print(f"\nMetadata Discrepancies Preview ({len(comparisons)} files)")
        print("=" * 80)

        for i, comp in enumerate(comparisons, 1):
            print(f"\n{i}. {comp.filename}")
            print(f"   Database: {comp.db_artist} - {comp.db_title}")
            print(f"   Filename: {comp.file_artist} - {comp.file_title}")

    def _print_results_summary(self, results: List[MetadataFixResult]) -> None:
        """Print summary of metadata fix results."""
        if not results:
            return

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        skipped = [r for r in results if r.action_taken == MetadataAction.SKIP]
        db_updates = [
            r for r in successful if r.action_taken == MetadataAction.UPDATE_DATABASE
        ]
        file_updates = [
            r for r in successful if r.action_taken == MetadataAction.UPDATE_FILENAME
        ]

        print(f"\nMetadata Fix Summary")
        print("=" * 50)
        print(f"Total files processed: {len(results)}")
        print(f"Successful operations: {len(successful)}")
        print(f"Failed operations: {len(failed)}")
        print(f"Skipped files: {len(skipped)}")
        print(f"Database updates: {len(db_updates)}")
        print(f"File renames: {len(file_updates)}")

        if failed:
            print(f"\nFailed operations:")
            for result in failed:
                print(f"  - {result.filename}: {result.error_message}")

        mode_str = "DRY RUN" if self.config.dry_run else "LIVE"
        print(f"\nMode: {mode_str}")
        print("=" * 50)
