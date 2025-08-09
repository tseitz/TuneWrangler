"""
Validation utilities for configuration, file paths, and data structures.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple
import logging

logger = logging.getLogger(__name__)


def validate_file_path(
    path: Union[str, Path],
    must_exist: bool = True,
    must_be_file: bool = True,
    must_be_readable: bool = True,
) -> Tuple[bool, str]:
    """
    Validate a file path with various checks.

    Args:
        path: Path to validate
        must_exist: Whether the path must exist
        must_be_file: Whether the path must be a file (not directory)
        must_be_readable: Whether the file must be readable

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        path_obj = Path(path).expanduser().resolve()

        if must_exist and not path_obj.exists():
            return False, f"Path does not exist: {path_obj}"

        if path_obj.exists():
            if must_be_file and not path_obj.is_file():
                return False, f"Path is not a file: {path_obj}"

            if must_be_readable and not os.access(path_obj, os.R_OK):
                return False, f"File is not readable: {path_obj}"

        return True, ""

    except Exception as e:
        return False, f"Error validating path: {e}"


def validate_directory_path(
    path: Union[str, Path], must_exist: bool = True, must_be_writable: bool = False
) -> Tuple[bool, str]:
    """
    Validate a directory path.

    Args:
        path: Directory path to validate
        must_exist: Whether the directory must exist
        must_be_writable: Whether the directory must be writable

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        path_obj = Path(path).expanduser().resolve()

        if must_exist and not path_obj.exists():
            return False, f"Directory does not exist: {path_obj}"

        if path_obj.exists() and not path_obj.is_dir():
            return False, f"Path is not a directory: {path_obj}"

        if must_be_writable and path_obj.exists():
            import os

            if not os.access(path_obj, os.W_OK):
                return False, f"Directory is not writable: {path_obj}"

        return True, ""

    except Exception as e:
        return False, f"Error validating directory: {e}"


def validate_json_config(
    config_data: Dict[str, Any],
    required_fields: Optional[List[str]] = None,
    schema: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """
    Validate JSON configuration data.

    Args:
        config_data: Configuration dictionary to validate
        required_fields: List of required field names
        schema: Optional schema dictionary for validation

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    if not isinstance(config_data, dict):
        errors.append("Configuration data must be a dictionary")  # type: ignore[unreachable]
        return False, errors

    # Check required fields
    if required_fields:
        for field in required_fields:
            if field not in config_data:
                errors.append(f"Required field missing: {field}")
            elif config_data[field] is None:
                errors.append(f"Required field is null: {field}")

    # Basic schema validation if provided
    if schema:
        for field, expected_type in schema.items():
            if field in config_data:
                value = config_data[field]
                if not isinstance(value, expected_type):
                    errors.append(
                        f"Field '{field}' should be type {expected_type.__name__}, got {type(value).__name__}"
                    )

    return len(errors) == 0, errors


def validate_playlist_config(playlist_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate playlist configuration data structure.

    Args:
        playlist_data: Playlist configuration dictionary

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check top-level structure
    if "data" not in playlist_data:
        errors.append("Missing 'data' field in playlist configuration")
        return False, errors

    data = playlist_data["data"]
    if not isinstance(data, list):
        errors.append("'data' field must be a list")
        return False, errors

    # Validate each playlist category
    for i, category in enumerate(data):
        category_errors = validate_playlist_category(category, i)
        errors.extend(category_errors)

    return len(errors) == 0, errors


def validate_playlist_category(category: Dict[str, Any], index: int) -> List[str]:
    """
    Validate a single playlist category.

    Args:
        category: Category dictionary to validate
        index: Index of category for error reporting

    Returns:
        List of validation errors
    """
    errors = []
    prefix = f"Category {index}"

    # Required fields
    required_fields = ["parent", "mainConditions", "playlists"]
    for field in required_fields:
        if field not in category:
            errors.append(f"{prefix}: Missing required field '{field}'")

    # Validate field types
    if "parent" in category and not isinstance(category["parent"], str):
        errors.append(f"{prefix}: 'parent' must be a string")

    if "mainConditions" in category:
        if not isinstance(category["mainConditions"], list):
            errors.append(f"{prefix}: 'mainConditions' must be a list")
        else:
            for j, condition in enumerate(category["mainConditions"]):
                if not isinstance(condition, str):
                    errors.append(f"{prefix}: 'mainConditions[{j}]' must be a string")

    if "negativeConditions" in category:
        if not isinstance(category["negativeConditions"], list):
            errors.append(f"{prefix}: 'negativeConditions' must be a list")
        else:
            for j, condition in enumerate(category["negativeConditions"]):
                if not isinstance(condition, str):
                    errors.append(
                        f"{prefix}: 'negativeConditions[{j}]' must be a string"
                    )

    # Validate playlists
    if "playlists" in category:
        if not isinstance(category["playlists"], list):
            errors.append(f"{prefix}: 'playlists' must be a list")
        else:
            for j, playlist in enumerate(category["playlists"]):
                playlist_errors = validate_playlist_item(
                    playlist, f"{prefix}.playlists[{j}]"
                )
                errors.extend(playlist_errors)

    return errors


def validate_playlist_item(playlist: Dict[str, Any], prefix: str) -> List[str]:
    """
    Validate a single playlist item.

    Args:
        playlist: Playlist dictionary to validate
        prefix: Prefix for error messages

    Returns:
        List of validation errors
    """
    errors = []

    # Required fields
    required_fields = ["name", "operator"]
    for field in required_fields:
        if field not in playlist:
            errors.append(f"{prefix}: Missing required field '{field}'")

    # Validate field types and values
    if "name" in playlist:
        if not isinstance(playlist["name"], str):
            errors.append(f"{prefix}: 'name' must be a string")
        elif not playlist["name"].strip():
            errors.append(f"{prefix}: 'name' cannot be empty")

    if "operator" in playlist:
        if not isinstance(playlist["operator"], int):
            errors.append(f"{prefix}: 'operator' must be an integer")
        elif playlist["operator"] not in [1, 2]:  # 1=ALL, 2=ANY
            errors.append(f"{prefix}: 'operator' must be 1 (ALL) or 2 (ANY)")

    # Validate optional list fields
    list_fields = ["contains", "doesNotContain"]
    for field in list_fields:
        if field in playlist:
            if not isinstance(playlist[field], list):
                errors.append(f"{prefix}: '{field}' must be a list")
            else:
                for i, item in enumerate(playlist[field]):
                    if not isinstance(item, str):
                        errors.append(f"{prefix}: '{field}[{i}]' must be a string")

    # Validate rating field
    if "rating" in playlist:
        rating = playlist["rating"]
        if not isinstance(rating, list):
            errors.append(f"{prefix}: 'rating' must be a list")
        elif len(rating) != 2:
            errors.append(f"{prefix}: 'rating' must have exactly 2 elements")
        else:
            for i, value in enumerate(rating):
                if not isinstance(value, str):
                    errors.append(f"{prefix}: 'rating[{i}]' must be a string")

    # Validate dateCreated field
    if "dateCreated" in playlist:
        date_created = playlist["dateCreated"]
        if not isinstance(date_created, dict):
            errors.append(f"{prefix}: 'dateCreated' must be a dictionary")
        else:
            required_date_fields = ["time_period", "time_unit", "operator"]
            for field in required_date_fields:
                if field not in date_created:
                    errors.append(
                        f"{prefix}.dateCreated: Missing required field '{field}'"
                    )

            if "time_period" in date_created:
                if not isinstance(date_created["time_period"], int):
                    errors.append(
                        f"{prefix}.dateCreated: 'time_period' must be an integer"
                    )
                elif date_created["time_period"] <= 0:
                    errors.append(
                        f"{prefix}.dateCreated: 'time_period' must be positive"
                    )

            if "time_unit" in date_created:
                valid_units = ["day", "week", "month", "year"]
                if date_created["time_unit"] not in valid_units:
                    errors.append(
                        f"{prefix}.dateCreated: 'time_unit' must be one of {valid_units}"
                    )

    return errors


def validate_filename_format(
    filename: str, expected_patterns: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """
    Validate filename format against expected patterns.

    Args:
        filename: Filename to validate
        expected_patterns: List of regex patterns to match against

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not filename or not filename.strip():
        return False, "Filename cannot be empty"

    # Default patterns for music files
    if expected_patterns is None:
        expected_patterns = [
            r"^.+ - .+\.(mp3|wav|flac|aiff|m4a)$",  # Artist - Title.ext
            r"^.+ - .+ - .+\.(mp3|wav|flac|aiff|m4a)$",  # Artist - Album - Title.ext
        ]

    for pattern in expected_patterns:
        if re.match(pattern, filename, re.IGNORECASE):
            return True, ""

    return False, f"Filename does not match expected format: {filename}"


def validate_audio_file_extensions(
    filename: str, allowed_extensions: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """
    Validate that filename has an allowed audio file extension.

    Args:
        filename: Filename to validate
        allowed_extensions: List of allowed extensions (with dots)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if allowed_extensions is None:
        allowed_extensions = [".mp3", ".wav", ".flac", ".aiff", ".m4a"]

    file_path = Path(filename)
    extension = file_path.suffix.lower()

    if extension in [ext.lower() for ext in allowed_extensions]:
        return True, ""

    return (
        False,
        f"File extension '{extension}' not in allowed extensions: {allowed_extensions}",
    )


def validate_rekordbox_paths(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate Rekordbox-specific paths in configuration.

    Args:
        config: Configuration dictionary

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check Pioneer directories
    pioneer_paths = {
        "pioneer_app_support": "Pioneer Application Support directory",
        "pioneer_library": "Pioneer Library directory",
    }

    for path_key, description in pioneer_paths.items():
        if path_key in config:
            is_valid, error = validate_directory_path(
                config[path_key], must_exist=False
            )
            if not is_valid:
                errors.append(f"{description}: {error}")

    # Check collection path
    if "collection_path" in config:
        is_valid, error = validate_directory_path(
            config["collection_path"], must_exist=True
        )
        if not is_valid:
            errors.append(f"Collection path: {error}")

    # Check playlist data path
    if "playlist_data_path" in config:
        is_valid, error = validate_directory_path(
            config["playlist_data_path"], must_exist=True
        )
        if not is_valid:
            errors.append(f"Playlist data path: {error}")

    return len(errors) == 0, errors


if __name__ == "__main__":
    # Example usage and testing
    import logging

    logging.basicConfig(level=logging.DEBUG)

    # Test file path validation
    is_valid, error = validate_file_path(__file__)
    print(f"File validation: {is_valid}, {error}")

    # Test playlist config validation
    test_config = {
        "data": [
            {
                "parent": "Test",
                "mainConditions": ["House"],
                "playlists": [
                    {"name": "Test Playlist", "operator": 1, "contains": ["Deep House"]}
                ],
            }
        ]
    }

    is_valid, errors = validate_playlist_config(test_config)
    print(f"Playlist config validation: {is_valid}")
    if errors:
        for error in errors:
            print(f"  - {error}")

    print("Validation tests completed")
