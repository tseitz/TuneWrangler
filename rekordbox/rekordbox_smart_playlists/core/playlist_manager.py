"""
Playlist management for Rekordbox Smart Playlists.

Handles creation and management of smart playlists based on JSON configuration files.
Provides high-level operations for playlist creation with proper error handling and logging.
"""

import json
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Set
from dataclasses import dataclass

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
from .database import RekordboxDatabase
from .config import Config

logger = get_logger(__name__)


class ExistingPlaylistStrategy(Enum):
    """Strategy for handling playlists that already exist."""

    OVERWRITE_ALL = "overwrite"
    SKIP_ALL = "skip"
    PROMPT_EACH = "prompt"


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
    skipped: bool = False
    skip_reason: Optional[str] = None
    created_playlists: Optional[List[str]] = None

    def __post_init__(self) -> None:
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
        self.existing_strategy = ExistingPlaylistStrategy.PROMPT_EACH
        self._created_playlists: List[str] = []
        self._skip_parents: Set[str] = set()
        self._tag_cache: Dict[str, Any] = {}
        self._load_tag_cache()

    def _load_tag_cache(self) -> None:
        """Load all tags into memory for fast lookup during playlist creation."""
        try:
            all_tags = self.db.get_tags()
            self._tag_cache = {tag.Name: tag for tag in all_tags}
            logger.info(f"Loaded {len(self._tag_cache)} tags into cache")
        except Exception as e:
            log_exception(logger, e, "loading tag cache")

    def create_playlists_from_file(
        self, config_file: Union[str, Path], start_sequence: Optional[int] = None
    ) -> List[PlaylistCreationResult]:
        """
        Create playlists from a JSON configuration file.

        Args:
            config_file: Path to JSON configuration file
            start_sequence: Optional starting sequence number for ordering

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
        return self.create_playlists_from_data(config_data["data"], start_sequence=start_sequence)

    def create_playlists_from_data(
        self,
        playlist_data: List[Dict[str, Any]],
        start_sequence: Optional[int] = None,
    ) -> List[PlaylistCreationResult]:
        """
        Create playlists from configuration data.

        Args:
            playlist_data: List of playlist category configurations
            start_sequence: Optional starting sequence number for ordering

        Returns:
            List of playlist creation results
        """
        results = []
        progress = create_progress_logger(len(playlist_data), "Creating playlist categories")

        for i, category_data in enumerate(playlist_data):
            try:
                sequence = (start_sequence + i) if start_sequence is not None else (i + 1)
                category_results = self._create_category_playlists(category_data, sequence)
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

        # Skip this category if the user declined to delete the existing folder
        if parent_name in self._skip_parents:
            logger.info(f"Skipping '{parent_name}' (user chose not to delete existing folder)")
            return [
                PlaylistCreationResult(
                    success=True,
                    playlist_name=parent_name,
                    skipped=True,
                    skip_reason="User chose to keep existing folder",
                )
            ]

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

        # Resolve base playlists and merge with category playlists
        base_playlists = self._resolve_base_playlists(category_data)
        playlists_config = base_playlists + category_data.get("playlists", [])
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

        # Check if playlist already exists in this specific parent context
        existing_playlist = self.db.get_playlist_by_name(playlist_name, parent_playlist.ID)
        if existing_playlist is not None:
            parent_name = getattr(parent_playlist, "Name", "Unknown")

            if self.existing_strategy == ExistingPlaylistStrategy.SKIP_ALL:
                logger.info(f"Skipping existing playlist: {playlist_name}")
                return PlaylistCreationResult(
                    success=True,
                    playlist_name=playlist_name,
                    skipped=True,
                    skip_reason="Playlist already exists (strategy: skip all)",
                )
            elif self.existing_strategy == ExistingPlaylistStrategy.PROMPT_EACH:
                response = input(
                    f"Playlist '{playlist_name}' already exists in '{parent_name}'. "
                    f"Overwrite or skip? (o/S): "
                )
                if response.lower() not in ["o", "overwrite"]:
                    logger.info(f"User chose to skip: {playlist_name}")
                    return PlaylistCreationResult(
                        success=True,
                        playlist_name=playlist_name,
                        skipped=True,
                        skip_reason="User chose to skip existing playlist",
                    )

            # OVERWRITE_ALL or user chose to overwrite in PROMPT_EACH
            logger.info(f"Overwriting existing playlist: {playlist_name}")
            self.db.delete_playlist(existing_playlist)

        # Handle folder type playlists
        playlist_type = playlist_config.get("playlistType")
        if playlist_type == "folder":
            return self._create_folder_playlist(
                playlist_config, parent_playlist, main_conditions, negative_conditions
            )

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
        self,
        playlist_config: Dict[str, Any],
        parent_playlist: Any,
        inherited_main_conditions: Set[str],
        inherited_negative_conditions: Set[str],
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

        # First, get or create the folder under the current parent
        folder_playlist = self.db.get_playlist_by_name(folder_name, parent_playlist.ID)
        folder_already_exists = folder_playlist is not None

        if folder_already_exists:
            child_count = self.db.count_playlist_children_recursive(folder_playlist)
            parent_name = getattr(parent_playlist, "Name", "Unknown")

            if self.existing_strategy == ExistingPlaylistStrategy.SKIP_ALL:
                logger.info(f"Skipping existing folder: {folder_name}")
                return PlaylistCreationResult(
                    success=True,
                    playlist_name=folder_name,
                    skipped=True,
                    skip_reason="Folder already exists (strategy: skip all)",
                )
            elif self.existing_strategy == ExistingPlaylistStrategy.PROMPT_EACH:
                child_str = f"{child_count} child playlist(s)" if child_count else "empty"
                response = input(
                    f"Folder '{folder_name}' already exists in '{parent_name}' ({child_str}). "
                    f"Overwrite or skip? (o/S): "
                )
                if response.lower() not in ["o", "overwrite"]:
                    logger.info(f"User chose to skip folder: {folder_name}")
                    return PlaylistCreationResult(
                        success=True,
                        playlist_name=folder_name,
                        skipped=True,
                        skip_reason="User chose to skip existing folder",
                    )

            # OVERWRITE_ALL or user chose to overwrite in PROMPT_EACH
            logger.info(f"Overwriting existing folder: {folder_name}")
            self.db.delete_playlist_recursive(folder_playlist)
            folder_playlist = None

        if folder_playlist is None:
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
            with open(link_path, "r", encoding="utf-8") as f:
                linked_config_data = json.load(f)

            linked_results = []

            # Use the inherited conditions from the parent context
            # These come from the category that contains this folder link
            # e.g., when "My Set" category processes "Late Night" folder link,
            # inherited_main_conditions contains ["My Set"]

            for category_data in linked_config_data["data"]:
                # Merge conditions: inherited + category + individual playlist
                category_main_conditions = set(category_data.get("mainConditions", []))
                category_negative_conditions = set(category_data.get("negativeConditions", []))

                # Final conditions = inherited (My Set) + category (Late Night) + individual
                final_main_conditions = inherited_main_conditions.copy()
                final_main_conditions.update(category_main_conditions)

                final_negative_conditions = inherited_negative_conditions.copy()
                final_negative_conditions.update(category_negative_conditions)

                # Resolve base playlists and merge with category playlists
                base_playlists = self._resolve_base_playlists(category_data)
                all_playlists = base_playlists + category_data.get("playlists", [])

                # Process each playlist in this category
                for playlist_data in all_playlists:
                    result = self._create_single_playlist(
                        playlist_data,
                        folder_playlist,
                        final_main_conditions,
                        final_negative_conditions,
                    )
                    linked_results.append(result)

            success_count = len([r for r in linked_results if r.success])

            # Determine if this folder operation was a skip or creation
            folder_skipped = folder_already_exists and all(
                r.skipped for r in linked_results if r.success
            )

            return PlaylistCreationResult(
                success=success_count > 0,
                playlist_name=folder_name,
                skipped=folder_skipped,
                skip_reason="Folder and all contents already exist" if folder_skipped else None,
                created_playlists=[
                    r.playlist_name for r in linked_results if r.success and not r.skipped
                ],
            )

        except Exception as e:
            return PlaylistCreationResult(
                success=False,
                playlist_name=folder_name,
                error_message=f"Failed to process linked config {link}: {e}",
            )

    def _resolve_base_playlists(self, category_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Resolve base playlists from a referenced base file.

        If the category_data contains a "base" field, load the referenced JSON file
        and return its playlists. These are prepended to the category's own playlists
        to avoid duplication across texture files.

        Args:
            category_data: Category configuration that may contain a "base" field

        Returns:
            List of playlist configurations from the base file, or empty list
        """
        base_ref = category_data.get("base")
        if not base_ref:
            return []

        base_path = Path(self.config.playlist_data_path) / base_ref
        try:
            with open(base_path, "r", encoding="utf-8") as f:
                base_data = json.load(f)
            playlists: List[Dict[str, Any]] = base_data.get("data", {}).get("playlists", [])
            logger.debug(f"Loaded {len(playlists)} base playlists from: {base_ref}")
            return playlists
        except FileNotFoundError:
            log_error(logger, f"Base playlist file not found: {base_path}")
            return []
        except json.JSONDecodeError as e:
            log_error(logger, f"Invalid JSON in base file {base_path}: {e}")
            return []
        except Exception as e:
            log_exception(logger, e, f"loading base playlists from {base_ref}")
            return []

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
        Add a tag condition to smart list using the pre-loaded tag cache.

        Args:
            smart_list: SmartList to add condition to
            tag_name: Name of tag to search for
            operator: Operator to use for condition

        Returns:
            True if condition was added successfully, False otherwise
        """
        try:
            tag = self._tag_cache.get(tag_name)
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

            mapped_unit = time_unit
            date_operator_map = {
                "IN_LAST": Operator.IN_LAST,
                "NOT_IN_LAST": Operator.NOT_IN_LAST,
            }
            date_operator = date_operator_map.get(operator, Operator.IN_LAST)

            smart_list.add_condition(
                Property.DATE_CREATED, date_operator, str(time_period), unit=mapped_unit
            )

            logger.debug(f"Added date condition: {time_period} {mapped_unit} ({operator})")
            return True

        except Exception as e:
            log_exception(logger, e, "adding date condition")
            return False

    def find_existing_root_folders(
        self, config_file: Optional[Union[str, Path]] = None
    ) -> List[Dict[str, Any]]:
        """
        Find root folders from config file(s) that already exist in the database.

        Scans the JSON configuration to extract the top-level 'parent' names,
        then checks if each one already exists as a playlist folder in Rekordbox.

        Args:
            config_file: Specific config file to check, or None to check all files
                         in the playlist data directory.

        Returns:
            List of dicts with 'name', 'playlist' (the db object), and 'child_count'.
        """
        existing = []

        # Collect all config files to scan
        if config_file:
            config_path = Path(config_file)
            if not config_path.is_absolute():
                config_path = Path(self.config.playlist_data_path) / config_path
            files_to_scan = [config_path] if config_path.exists() else []
        else:
            playlist_dir = Path(self.config.playlist_data_path)
            files_to_scan = sorted(playlist_dir.glob("*.json"))

        # Extract parent names from each file
        seen_parents: Set[str] = set()
        for json_file in files_to_scan:
            if json_file.name.startswith(".") or json_file.name.startswith("_"):
                continue
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    config_data = json.load(f)

                data = config_data.get("data", [])
                if not isinstance(data, list):
                    continue

                for category in data:
                    parent_name = category.get("parent", "")
                    if parent_name and parent_name not in seen_parents:
                        seen_parents.add(parent_name)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        # Check which parents exist in the database
        default_parent = self.db.get_playlist_by_name(self.config.default_parent_playlist)
        if not default_parent:
            return []

        for parent_name in sorted(seen_parents):
            playlist = self.db.get_playlist_by_name(parent_name, default_parent.ID)
            if playlist:
                child_count = self.db.count_playlist_children_recursive(playlist)
                existing.append(
                    {
                        "name": parent_name,
                        "playlist": playlist,
                        "child_count": child_count,
                    }
                )

        return existing

    def delete_root_folder(self, playlist: Any) -> int:
        """
        Delete a root folder and all its contents.

        Args:
            playlist: The playlist folder object to delete recursively.

        Returns:
            Number of playlists/folders deleted.
        """
        name = playlist.Name
        deleted = self.db.delete_playlist_recursive(playlist)
        if deleted > 0:
            log_success(logger, f"Deleted '{name}' and {deleted - 1} child playlists")
        return deleted

    def get_created_playlists(self) -> List[str]:
        """Get list of playlists created in this session."""
        return self._created_playlists.copy()

    def clear_created_playlists(self) -> None:
        """Clear the list of created playlists."""
        self._created_playlists.clear()

    def _load_file_order(self, directory: Path) -> Optional[Dict[str, Any]]:
        """
        Load file ordering configuration from _order.json.

        Args:
            directory: Directory to look for _order.json in

        Returns:
            Order configuration dict or None if not found
        """
        order_file = directory / "_order.json"
        if not order_file.exists():
            return None

        try:
            with open(order_file, "r", encoding="utf-8") as f:
                order_config = json.load(f)
            logger.debug(f"Loaded file ordering from: {order_file}")
            return order_config
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load order config {order_file}: {e}")
            return None

    def _sort_files_by_order(
        self, json_files: List[Path], order_config: Optional[Dict[str, Any]]
    ) -> List[Path]:
        """
        Sort JSON files according to _order.json configuration.

        Files listed in "first" come first in that order, then remaining files
        alphabetically, then files listed in "last" in that order.

        Args:
            json_files: List of JSON file paths
            order_config: Order configuration from _order.json

        Returns:
            Sorted list of file paths
        """
        if not order_config:
            return sorted(json_files)

        first_names = order_config.get("first", [])
        last_names = order_config.get("last", [])
        pinned_names = set(first_names + last_names)

        file_map = {f.name: f for f in json_files}

        first_files = [file_map[name] for name in first_names if name in file_map]
        last_files = [file_map[name] for name in last_names if name in file_map]
        middle_files = sorted(
            [f for f in json_files if f.name not in pinned_names],
        )

        return first_files + middle_files + last_files

    def create_playlists_from_directory(
        self, directory: Union[str, Path]
    ) -> List[PlaylistCreationResult]:
        """
        Create playlists from all JSON files in a directory.

        Respects _order.json for file processing order if present.
        Files listed in "first" are processed first, then remaining files
        alphabetically, then files listed in "last".

        Args:
            directory: Directory containing JSON configuration files

        Returns:
            List of playlist creation results
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise PlaylistCreationError(f"Directory not found: {dir_path}")

        json_files = [
            f for f in dir_path.glob("*.json")
            if not f.name.startswith(".") and not f.name.startswith("_")
        ]
        if not json_files:
            logger.warning(f"No JSON files found in: {dir_path}")
            return []

        order_config = self._load_file_order(dir_path)
        sorted_files = self._sort_files_by_order(json_files, order_config)

        all_results = []
        progress = create_progress_logger(len(sorted_files), "Processing playlist files")
        global_sequence = 1

        for json_file in sorted_files:
            try:
                file_results = self.create_playlists_from_file(
                    json_file, start_sequence=global_sequence
                )
                all_results.extend(file_results)

                # Count how many root categories this file contributed
                with open(json_file, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                category_count = len(file_data.get("data", []))
                global_sequence += max(category_count, 1)

                success_count = len([r for r in file_results if r.success])
                progress.update(message=f"Processed {json_file.name} ({success_count} playlists)")

            except Exception as e:
                log_exception(logger, e, f"processing file {json_file.name}")
                error_result = PlaylistCreationResult(
                    success=False, playlist_name=json_file.name, error_message=str(e)
                )
                all_results.append(error_result)
                global_sequence += 1

        total_success = len([r for r in all_results if r.success])
        progress.finish(f"Processed {len(sorted_files)} files, created {total_success} playlists")

        return all_results
