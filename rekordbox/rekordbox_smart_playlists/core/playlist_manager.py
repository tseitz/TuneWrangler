"""
Playlist management for Rekordbox Smart Playlists.

Handles creation and management of smart playlists based on JSON configuration files.
Provides high-level operations for playlist creation with proper error handling and logging.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Set
from dataclasses import dataclass
from enum import Enum

from pyrekordbox.db6.smartlist import (
    SmartList,
    Property,
    Operator,
    LogicalOperator,
    left_bitshift,
)

from ..utils.logging import (
    get_logger,
    log_success,
    log_error,
    log_exception,
    create_progress_logger,
)
from ..utils.validation import validate_playlist_config
from .database import RekordboxDatabase, DatabaseError
from .config import Config

logger = get_logger(__name__)


class PlaylistCreationError(Exception):
    """Raised when playlist creation fails."""

    pass


class PlaylistValidationError(Exception):
    """Raised when playlist configuration is invalid."""

    pass


@dataclass
class PlaylistCreationResult:
    """Result of playlist creation operation."""

    success: bool
    playlist_name: str
    error_message: Optional[str] = None
    created_playlists: Optional[List[str]] = None

    def __post_init__(self):
        if self.created_playlists is None:
            self.created_playlists = []


class PlaylistManager:
    """
    High-level manager for Rekordbox smart playlist operations.
    """

    def __init__(self, database: RekordboxDatabase, config: Config):
        """
        Initialize playlist manager.

        Args:
            database: Database connection instance
            config: Configuration object
        """
        self.db = database
        self.config = config
        self._created_playlists: List[str] = []

    def create_playlists_from_file(
        self, config_file: Union[str, Path]
    ) -> List[PlaylistCreationResult]:
        """
        Create playlists from a JSON configuration file.

        Args:
            config_file: Path to JSON configuration file

        Returns:
            List of playlist creation results

        Raises:
            PlaylistValidationError: If configuration is invalid
            PlaylistCreationError: If playlist creation fails
        """
        config_path = Path(config_file)

        if not config_path.exists():
            raise PlaylistCreationError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            raise PlaylistValidationError(f"Invalid JSON in {config_path}: {e}") from e
        except Exception as e:
            raise PlaylistCreationError(f"Failed to read {config_path}: {e}") from e

        # Validate configuration
        is_valid, errors = validate_playlist_config(config_data)
        if not is_valid:
            error_msg = f"Invalid playlist configuration in {config_path}:\n" + "\n".join(errors)
            raise PlaylistValidationError(error_msg)

        logger.info(f"Creating playlists from: {config_path.name}")
        return self.create_playlists_from_data(config_data["data"])

    def create_playlists_from_data(
        self, playlist_data: List[Dict[str, Any]]
    ) -> List[PlaylistCreationResult]:
        """
        Create playlists from configuration data.

        Args:
            playlist_data: List of playlist category configurations

        Returns:
            List of playlist creation results
        """
        results = []
        progress = create_progress_logger(len(playlist_data), "Creating playlist categories")

        for i, category_data in enumerate(playlist_data):
            try:
                category_results = self._create_category_playlists(category_data, i + 1)
                results.extend(category_results)

                progress.update(
                    message=f"Created category: {category_data.get('parent', 'Unknown')}"
                )

            except Exception as e:
                log_exception(logger, e, f"creating category {i}")
                error_result = PlaylistCreationResult(
                    success=False,
                    playlist_name=category_data.get("parent", f"Category {i}"),
                    error_message=str(e),
                )
                results.append(error_result)

        progress.finish(f"Created {len([r for r in results if r.success])} playlists")
        return results

    def _create_category_playlists(
        self, category_data: Dict[str, Any], sequence: Optional[int] = None
    ) -> List[PlaylistCreationResult]:
        """
        Create playlists for a single category.

        Args:
            category_data: Category configuration data
            sequence: Optional sequence number for ordering

        Returns:
            List of playlist creation results
        """
        results = []
        parent_name = category_data.get("parent", "")
        main_conditions = set(category_data.get("mainConditions", []))
        negative_conditions = set(category_data.get("negativeConditions", []))

        # Get or create parent folder
        parent_playlist = self._get_or_create_parent_folder(parent_name, sequence)
        if not parent_playlist:
            error_result = PlaylistCreationResult(
                success=False,
                playlist_name=parent_name,
                error_message="Failed to create parent folder",
            )
            return [error_result]

        # Create individual playlists
        playlists_config = category_data.get("playlists", [])
        for playlist_config in playlists_config:
            try:
                result = self._create_single_playlist(
                    playlist_config,
                    parent_playlist,
                    main_conditions,
                    negative_conditions,
                )
                results.append(result)

            except Exception as e:
                log_exception(
                    logger,
                    e,
                    f"creating playlist {playlist_config.get('name', 'Unknown')}",
                )
                error_result = PlaylistCreationResult(
                    success=False,
                    playlist_name=playlist_config.get("name", "Unknown"),
                    error_message=str(e),
                )
                results.append(error_result)

        return results

    def _get_or_create_parent_folder(
        self, parent_name: str, sequence: Optional[int] = None
    ) -> Optional[Any]:
        """
        Get existing parent folder or create new one.

        Args:
            parent_name: Name of parent folder
            sequence: Optional sequence number

        Returns:
            Parent folder object or None if failed
        """
        if not parent_name:
            # Use default parent playlist
            default_parent = self.db.get_playlist_by_name(self.config.default_parent_playlist)
            if not default_parent:
                log_error(
                    logger,
                    f"Default parent playlist not found: {self.config.default_parent_playlist}",
                )
                return None
            return default_parent

        # Get default parent for hierarchy
        default_parent = self.db.get_playlist_by_name(self.config.default_parent_playlist)
        if not default_parent:
            log_error(
                logger,
                f"Default parent playlist not found: {self.config.default_parent_playlist}",
            )
            return None

        # Check if folder already exists
        existing_folder = self.db.get_playlist_by_name(parent_name, default_parent.ID)
        if existing_folder:
            logger.debug(f"Using existing folder: {parent_name}")
            return existing_folder

        # Create new folder
        new_folder = self.db.create_playlist_folder(parent_name, default_parent, sequence)
        if new_folder:
            log_success(logger, f"Created parent folder: {parent_name}")
        else:
            log_error(logger, f"Failed to create parent folder: {parent_name}")

        return new_folder

    def _create_single_playlist(
        self,
        playlist_config: Dict[str, Any],
        parent_playlist: Any,
        main_conditions: Set[str],
        negative_conditions: Set[str],
    ) -> PlaylistCreationResult:
        """
        Create a single smart playlist.

        Args:
            playlist_config: Playlist configuration
            parent_playlist: Parent playlist object
            main_conditions: Main tag conditions to include
            negative_conditions: Tag conditions to exclude

        Returns:
            Playlist creation result
        """
        playlist_name = playlist_config.get("name", "")
        if not playlist_name:
            return PlaylistCreationResult(
                success=False,
                playlist_name="",
                error_message="Playlist name is required",
            )

        # Check if playlist already exists
        if self.db.playlist_exists(playlist_name, parent_playlist.ID):
            logger.info(f"Playlist already exists: {playlist_name}")
            return PlaylistCreationResult(
                success=True,
                playlist_name=playlist_name,
                error_message="Playlist already exists (skipped)",
            )

        # Handle folder type playlists
        playlist_type = playlist_config.get("playlistType")
        if playlist_type == "folder":
            return self._create_folder_playlist(playlist_config, parent_playlist)

        # Create smart list with conditions
        smart_list = self._build_smart_list(playlist_config, main_conditions, negative_conditions)
        if not smart_list:
            return PlaylistCreationResult(
                success=False,
                playlist_name=playlist_name,
                error_message="Failed to build smart list conditions",
            )

        # Create the playlist
        created_playlist = self.db.create_smart_playlist(playlist_name, smart_list, parent_playlist)

        if created_playlist:
            self._created_playlists.append(playlist_name)
            return PlaylistCreationResult(
                success=True,
                playlist_name=playlist_name,
                created_playlists=[playlist_name],
            )
        else:
            return PlaylistCreationResult(
                success=False,
                playlist_name=playlist_name,
                error_message="Failed to create playlist in database",
            )

    def _create_folder_playlist(
        self, playlist_config: Dict[str, Any], parent_playlist: Any
    ) -> PlaylistCreationResult:
        """
        Create a folder-type playlist by processing linked configuration.

        Args:
            playlist_config: Playlist configuration with link to other config
            parent_playlist: Parent playlist object

        Returns:
            Playlist creation result
        """
        link = playlist_config.get("link")
        folder_name = playlist_config.get("name", "")

        if not link:
            return PlaylistCreationResult(
                success=False,
                playlist_name=folder_name,
                error_message="Folder playlist requires 'link' field",
            )

        if not folder_name:
            return PlaylistCreationResult(
                success=False,
                playlist_name="",
                error_message="Folder playlist requires 'name' field",
            )

        # First, create the folder under the current parent
        if self.db.playlist_exists(folder_name, parent_playlist.ID):
            logger.info(f"Folder already exists: {folder_name}")
            # Get the existing folder to use as parent for linked playlists
            folder_playlist = self.db.get_playlist_by_name(folder_name, parent_playlist.ID)
        else:
            # Create new folder
            folder_playlist = self.db.create_playlist_folder(folder_name, parent_playlist)
            if not folder_playlist:
                return PlaylistCreationResult(
                    success=False,
                    playlist_name=folder_name,
                    error_message=f"Failed to create folder: {folder_name}",
                )

        # Load linked configuration and process it with the folder as parent
        link_path = Path(self.config.playlist_data_path) / link
        try:
            # Load the linked file data
            with open(link_path, "r", encoding="utf-8") as f:
                linked_config_data = json.load(f)

            # Process each category in the linked file, using our folder as parent
            linked_results = []
            for category_data in linked_config_data["data"]:
                # Override the parent to be our folder instead of the one in the linked file
                modified_category = category_data.copy()
                modified_category["parent"] = ""  # No parent name, use the folder_playlist directly

                category_result = self._create_category_playlists(
                    modified_category, folder_playlist
                )
                linked_results.extend(category_result)

            success_count = len([r for r in linked_results if r.success])

            return PlaylistCreationResult(
                success=success_count > 0,
                playlist_name=folder_name,
                created_playlists=[r.playlist_name for r in linked_results if r.success],
            )

        except Exception as e:
            return PlaylistCreationResult(
                success=False,
                playlist_name=folder_name,
                error_message=f"Failed to process linked config {link}: {e}",
            )

    def _build_smart_list(
        self,
        playlist_config: Dict[str, Any],
        main_conditions: Set[str],
        negative_conditions: Set[str],
    ) -> Optional[SmartList]:
        """
        Build SmartList object from playlist configuration.

        Args:
            playlist_config: Playlist configuration
            main_conditions: Main tag conditions
            negative_conditions: Negative tag conditions

        Returns:
            SmartList object or None if failed
        """
        try:
            # Determine logical operator
            operator_value = playlist_config.get("operator", 1)
            logical_operator = LogicalOperator.ALL if operator_value == 1 else LogicalOperator.ANY

            smart_list = SmartList(logical_operator=logical_operator)

            # Add main conditions
            all_conditions = main_conditions.copy()
            all_conditions.update(playlist_config.get("contains", []))

            for condition in all_conditions:
                if not self._add_tag_condition(smart_list, condition, Operator.CONTAINS):
                    logger.warning(f"Failed to add condition: {condition}")

            # Add negative conditions (only for ALL operator)
            if logical_operator == LogicalOperator.ALL:
                all_negative = negative_conditions.copy()
                all_negative.update(playlist_config.get("doesNotContain", []))

                for condition in all_negative:
                    if not self._add_tag_condition(smart_list, condition, Operator.NOT_CONTAINS):
                        logger.warning(f"Failed to add negative condition: {condition}")

            # Add rating condition
            rating = playlist_config.get("rating")
            if rating and len(rating) == 2:
                smart_list.add_condition(Property.RATING, Operator.IN_RANGE, rating[0], rating[1])

            # Add date created condition
            date_created = playlist_config.get("dateCreated")
            if date_created:
                self._add_date_condition(smart_list, date_created)

            return smart_list

        except Exception as e:
            log_exception(logger, e, "building smart list")
            return None

    def _add_tag_condition(self, smart_list: SmartList, tag_name: str, operator: Operator) -> bool:
        """
        Add a tag condition to smart list.

        Args:
            smart_list: SmartList to add condition to
            tag_name: Name of tag to search for
            operator: Operator to use for condition

        Returns:
            True if condition was added successfully, False otherwise
        """
        try:
            tag = self.db.get_tag_by_name(tag_name)
            if not tag:
                log_error(logger, f"Tag not found: {tag_name}")
                return False

            smart_list.add_condition(Property.MYTAG, operator, left_bitshift(int(tag.ID)))

            logger.debug(f"Added tag condition: {tag_name} ({operator.name})")
            return True

        except Exception as e:
            log_exception(logger, e, f"adding tag condition {tag_name}")
            return False

    def _add_date_condition(self, smart_list: SmartList, date_config: Dict[str, Any]) -> bool:
        """
        Add a date created condition to smart list.

        Args:
            smart_list: SmartList to add condition to
            date_config: Date condition configuration

        Returns:
            True if condition was added successfully, False otherwise
        """
        try:
            time_period = date_config.get("time_period", 1)
            time_unit = date_config.get("time_unit", "months")
            operator = date_config.get("operator", "IN_LAST")

            # pyrekordbox expects singular forms - no mapping needed
            mapped_unit = time_unit
            date_operator = Operator.IN_LAST if operator == "IN_LAST" else Operator.IN_LAST

            smart_list.add_condition(
                Property.DATE_CREATED, date_operator, str(time_period), unit=mapped_unit
            )

            logger.debug(f"Added date condition: {time_period} {mapped_unit} ({operator})")
            return True

        except Exception as e:
            log_exception(logger, e, "adding date condition")
            return False

    def get_created_playlists(self) -> List[str]:
        """Get list of playlists created in this session."""
        return self._created_playlists.copy()

    def clear_created_playlists(self) -> None:
        """Clear the list of created playlists."""
        self._created_playlists.clear()

    def create_playlists_from_directory(
        self, directory: Union[str, Path]
    ) -> List[PlaylistCreationResult]:
        """
        Create playlists from all JSON files in a directory.

        Args:
            directory: Directory containing JSON configuration files

        Returns:
            List of playlist creation results
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise PlaylistCreationError(f"Directory not found: {dir_path}")

        json_files = list(dir_path.glob("*.json"))
        if not json_files:
            logger.warning(f"No JSON files found in: {dir_path}")
            return []

        all_results = []
        progress = create_progress_logger(len(json_files), "Processing playlist files")

        for json_file in sorted(json_files):
            try:
                if json_file.name.startswith("."):
                    continue  # Skip hidden files

                file_results = self.create_playlists_from_file(json_file)
                all_results.extend(file_results)

                success_count = len([r for r in file_results if r.success])
                progress.update(message=f"Processed {json_file.name} ({success_count} playlists)")

            except Exception as e:
                log_exception(logger, e, f"processing file {json_file.name}")
                error_result = PlaylistCreationResult(
                    success=False, playlist_name=json_file.name, error_message=str(e)
                )
                all_results.append(error_result)

        total_success = len([r for r in all_results if r.success])
        progress.finish(f"Processed {len(json_files)} files, created {total_success} playlists")

        return all_results
