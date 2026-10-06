"""
File utilities for safe file operations and path handling.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Union, List, Callable, Any, Generator
from contextlib import contextmanager
import tempfile
import logging

logger = logging.getLogger(__name__)


def ensure_directory(path: Union[str, Path], create: bool = True) -> Path:
    """
    Ensure directory exists, optionally creating it.

    Args:
        path: Directory path
        create: Whether to create the directory if it doesn't exist

    Returns:
        Path object

    Raises:
        ValueError: If path exists but is not a directory
        OSError: If directory creation fails
    """
    path_obj = Path(path).expanduser().resolve()

    if path_obj.exists():
        if not path_obj.is_dir():
            raise ValueError(f"Path exists but is not a directory: {path_obj}")
        return path_obj

    if create:
        try:
            path_obj.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {path_obj}")
        except OSError as e:
            logger.error(f"Failed to create directory {path_obj}: {e}")
            raise

    return path_obj


def safe_file_operation(
    operation: Callable[[], Any],
    backup_path: Optional[Union[str, Path]] = None,
    description: str = "file operation",
) -> Any:
    """
    Perform a file operation with automatic backup and rollback on failure.

    Args:
        operation: Function to execute
        backup_path: Optional path to create backup before operation
        description: Description for logging

    Returns:
        Result of the operation

    Raises:
        Exception: Re-raises any exception from the operation after rollback
    """
    backup_created = False
    temp_backup = None

    try:
        # Create backup if requested
        if backup_path:
            backup_source = Path(backup_path)
            if backup_source.exists():
                temp_backup = backup_source.with_suffix(
                    backup_source.suffix + ".backup"
                )
                shutil.copy2(backup_source, temp_backup)
                backup_created = True
                logger.debug(f"Created backup: {temp_backup}")

        # Perform operation
        logger.debug(f"Executing {description}")
        result = operation()

        # Clean up backup on success
        if backup_created and temp_backup and temp_backup.exists():
            temp_backup.unlink()
            logger.debug(f"Removed backup: {temp_backup}")

        return result

    except Exception as e:
        logger.error(f"Failed {description}: {e}")

        # Restore from backup if available
        if backup_created and temp_backup and temp_backup.exists():
            try:
                shutil.move(str(temp_backup), str(backup_path))
                logger.info(f"Restored from backup: {backup_path}")
            except Exception as restore_error:
                logger.error(f"Failed to restore backup: {restore_error}")

        raise


@contextmanager
def temporary_directory(
    prefix: str = "rekordbox_", cleanup: bool = True
) -> Generator[Path, None, None]:
    """
    Context manager for creating temporary directories.

    Args:
        prefix: Prefix for temporary directory name
        cleanup: Whether to clean up directory on exit

    Yields:
        Path to temporary directory
    """
    temp_dir = None
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        logger.debug(f"Created temporary directory: {temp_dir}")
        yield temp_dir
    finally:
        if temp_dir and cleanup and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(
                    f"Failed to clean up temporary directory {temp_dir}: {e}"
                )


def safe_copy(
    source: Union[str, Path], destination: Union[str, Path], overwrite: bool = False
) -> bool:
    """
    Safely copy a file with error handling.

    Args:
        source: Source file path
        destination: Destination file path
        overwrite: Whether to overwrite existing files

    Returns:
        True if copy was successful, False otherwise
    """
    source_path = Path(source)
    dest_path = Path(destination)

    try:
        # Validate source
        if not source_path.exists():
            logger.error(f"Source file does not exist: {source_path}")
            return False

        if not source_path.is_file():
            logger.error(f"Source is not a file: {source_path}")
            return False

        # Check destination
        if dest_path.exists() and not overwrite:
            logger.error(f"Destination exists and overwrite=False: {dest_path}")
            return False

        # Ensure destination directory exists
        ensure_directory(dest_path.parent)

        # Perform copy
        shutil.copy2(source_path, dest_path)
        logger.debug(f"Copied {source_path} -> {dest_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to copy {source_path} -> {dest_path}: {e}")
        return False


def safe_move(
    source: Union[str, Path], destination: Union[str, Path], overwrite: bool = False
) -> bool:
    """
    Safely move/rename a file with error handling.

    Args:
        source: Source file path
        destination: Destination file path
        overwrite: Whether to overwrite existing files

    Returns:
        True if move was successful, False otherwise
    """
    source_path = Path(source)
    dest_path = Path(destination)

    try:
        # Validate source
        if not source_path.exists():
            logger.error(f"Source file does not exist: {source_path}")
            return False

        # Check destination
        if dest_path.exists() and not overwrite:
            logger.error(f"Destination exists and overwrite=False: {dest_path}")
            return False

        # Ensure destination directory exists
        ensure_directory(dest_path.parent)

        # Perform move
        shutil.move(str(source_path), str(dest_path))
        logger.debug(f"Moved {source_path} -> {dest_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to move {source_path} -> {dest_path}: {e}")
        return False


def find_files(
    directory: Union[str, Path], patterns: List[str], recursive: bool = True
) -> List[Path]:
    """
    Find files matching patterns in a directory.

    Args:
        directory: Directory to search
        patterns: List of glob patterns to match
        recursive: Whether to search recursively

    Returns:
        List of matching file paths
    """
    directory_path = Path(directory)
    if not directory_path.exists():
        logger.warning(f"Directory does not exist: {directory_path}")
        return []

    files = []
    for pattern in patterns:
        if recursive:
            matches = list(directory_path.rglob(pattern))
        else:
            matches = list(directory_path.glob(pattern))

        # Filter to only files (not directories)
        file_matches = [f for f in matches if f.is_file()]
        files.extend(file_matches)

    # Remove duplicates and sort
    unique_files = list(set(files))
    unique_files.sort()

    logger.debug(
        f"Found {len(unique_files)} files matching {patterns} in {directory_path}"
    )
    return unique_files


def get_file_size(path: Union[str, Path]) -> Optional[int]:
    """
    Get file size in bytes.

    Args:
        path: File path

    Returns:
        File size in bytes, or None if file doesn't exist
    """
    path_obj = Path(path)
    try:
        return path_obj.stat().st_size if path_obj.exists() else None
    except Exception as e:
        logger.error(f"Failed to get size of {path_obj}: {e}")
        return None


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted size string
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)

    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1

    return f"{size:.1f} {size_names[i]}"


def cleanup_empty_directories(root_path: Union[str, Path]) -> int:
    """
    Remove empty directories recursively.

    Args:
        root_path: Root directory to start cleanup from

    Returns:
        Number of directories removed
    """
    root_path_obj = Path(root_path)
    removed_count = 0

    if not root_path_obj.exists():
        return 0

    # Walk bottom-up to remove empty directories
    for dirpath, dirnames, filenames in os.walk(root_path_obj, topdown=False):
        dir_path = Path(dirpath)

        # Skip if not empty
        if filenames or dirnames:
            continue

        # Skip root directory
        if dir_path == root_path_obj:
            continue

        try:
            dir_path.rmdir()
            removed_count += 1
            logger.debug(f"Removed empty directory: {dir_path}")
        except Exception as e:
            logger.warning(f"Failed to remove empty directory {dir_path}: {e}")

    return removed_count


if __name__ == "__main__":
    # Example usage and testing
    import logging

    logging.basicConfig(level=logging.DEBUG)

    # Test directory operations
    test_dir = Path("test_directory")
    ensure_directory(test_dir)

    # Test file operations
    test_file = test_dir / "test.txt"
    test_file.write_text("Hello, world!")

    # Test finding files
    files = find_files(test_dir, ["*.txt"])
    print(f"Found files: {files}")

    # Cleanup
    shutil.rmtree(test_dir)
    print("Test completed")
