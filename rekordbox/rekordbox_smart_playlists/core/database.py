"""
Database wrapper for Rekordbox operations.

Provides a clean interface to the Rekordbox database with proper error handling,
logging, and connection management.
"""

from typing import Optional, List, Any, Union
from pathlib import Path
from contextlib import contextmanager

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.smartlist import SmartList

from ..utils.logging import get_logger, log_exception, log_success
from .config import Config

logger = get_logger(__name__)


class DatabaseError(Exception):
    """Base exception for database operations."""

    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""

    pass


class DatabaseQueryError(DatabaseError):
    """Raised when database query fails."""

    pass


class RekordboxDatabase:
    """
    Wrapper around pyrekordbox database with enhanced error handling and logging.
    """

    def __init__(self, config: Optional[Config] = None):
        """
        Initialize database connection.

        Args:
            config: Configuration object with database settings

        Raises:
            DatabaseConnectionError: If database connection fails
        """
        self.config = config or Config()
        self._db: Optional[Rekordbox6Database] = None
        self._is_connected = False

        self._connect()

    def _connect(self) -> None:
        """Establish database connection with error handling."""
        try:
            logger.info("Connecting to Rekordbox database...")
            self._db = Rekordbox6Database()
            self._is_connected = True
            log_success(logger, "Database connection established")

        except Exception as e:
            self._is_connected = False
            log_exception(logger, e, "database connection")
            raise DatabaseConnectionError(f"Failed to connect to Rekordbox database: {e}") from e

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._is_connected and self._db is not None

    def ensure_connected(self) -> None:
        """Ensure database connection is active."""
        if not self.is_connected:
            self._connect()

    def close(self) -> None:
        """Close database connection."""
        if self._db is not None:
            try:
                self._db.close()
                log_success(logger, "Database connection closed")
            except Exception as e:
                log_exception(logger, e, "closing database connection")
            finally:
                self._db = None
                self._is_connected = False

    def commit(self) -> None:
        """Commit database changes."""
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            self._db.commit()
            log_success(logger, "Database changes committed")
        except Exception as e:
            log_exception(logger, e, "committing database changes")
            raise DatabaseError(f"Failed to commit changes: {e}") from e

    def rollback(self) -> None:
        """Rollback database changes."""
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            self._db.rollback()
            logger.info("Database changes rolled back")
        except Exception as e:
            log_exception(logger, e, "rolling back database changes")
            raise DatabaseError(f"Failed to rollback changes: {e}") from e

    # Content operations
    def get_content(self, **filters: Any) -> List[Any]:
        """
        Get content items with optional filters.

        Args:
            **filters: Filter criteria for content query

        Returns:
            List of content items

        Raises:
            DatabaseQueryError: If query fails
        """
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            if filters:
                query = self._db.get_content(**filters)
                return list(query.all())
            else:
                return list(self._db.get_content())

        except Exception as e:
            log_exception(logger, e, f"querying content with filters {filters}")
            raise DatabaseQueryError(f"Failed to query content: {e}") from e

    def get_content_by_id(self, content_id: int) -> Optional[Any]:
        """
        Get content item by ID.

        Args:
            content_id: Content ID to search for

        Returns:
            Content item or None if not found
        """
        try:
            return self.get_content(ID=content_id)[0] if self.get_content(ID=content_id) else None
        except (DatabaseQueryError, IndexError):
            return None

    def find_content_by_filename(self, filename: str) -> Optional[Any]:
        """
        Find content by filename with fallback strategies.

        Args:
            filename: Filename to search for

        Returns:
            Content item or None if not found
        """
        self.ensure_connected()

        try:
            # Try exact filename match first
            content_list = self.get_content(FileNameL=filename)
            if content_list:
                return content_list[0]

            # Try case-insensitive search by parsing filename
            from ..utils.validation import validate_filename_format

            is_valid, _ = validate_filename_format(filename)

            if is_valid:
                # Parse artist and title from filename
                stem = Path(filename).stem
                if " - " in stem:
                    parts = stem.split(" - ")
                    if len(parts) >= 2:
                        artist_name = parts[0].strip()
                        title = parts[-1].strip()  # Last part is title

                        # Search by artist and title
                        content_list = self.get_content(ArtistName=artist_name, Title=title)
                        if content_list:
                            return content_list[0]

                        # Fallback: case-insensitive search
                        all_content = self.get_content()
                        for content in all_content:
                            if (
                                hasattr(content, "ArtistName")
                                and content.ArtistName
                                and hasattr(content, "Title")
                                and content.Title
                            ):
                                if (
                                    content.ArtistName.lower().strip() == artist_name.lower()
                                    and content.Title.lower().strip() == title.lower()
                                ):
                                    return content

            logger.debug(f"Content not found for filename: {filename}")
            return None

        except Exception as e:
            log_exception(logger, e, f"searching for content by filename {filename}")
            return None

    # Playlist operations
    def get_playlists(self, **filters: Any) -> List[Any]:
        """
        Get playlists with optional filters.

        Args:
            **filters: Filter criteria for playlist query

        Returns:
            List of playlist items
        """
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            if filters:
                query = self._db.get_playlist(**filters)
                return list(query.all())
            else:
                return list(self._db.get_playlist())

        except Exception as e:
            log_exception(logger, e, f"querying playlists with filters {filters}")
            raise DatabaseQueryError(f"Failed to query playlists: {e}") from e

    def get_playlist_by_name(self, name: str, parent_id: Optional[str] = None) -> Optional[Any]:
        """
        Get playlist by name with optional parent filter.

        Args:
            name: Playlist name to search for
            parent_id: Optional parent playlist ID

        Returns:
            Playlist item or None if not found
        """
        try:
            filters = {"Name": name}
            if parent_id is not None:
                filters["ParentID"] = parent_id

            playlists = self.get_playlists(**filters)
            return playlists[0] if playlists else None

        except (DatabaseQueryError, IndexError):
            return None

    def create_playlist_folder(
        self, name: str, parent: Optional[Any] = None, sequence: Optional[int] = None
    ) -> Optional[Any]:
        """
        Create a playlist folder.

        Args:
            name: Folder name
            parent: Parent playlist object
            sequence: Optional sequence number

        Returns:
            Created folder object or None if failed
        """
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            folder = self._db.create_playlist_folder(name, parent, sequence)
            logger.info(f"Created playlist folder: {name}")
            return folder

        except Exception as e:
            log_exception(logger, e, f"creating playlist folder {name}")
            return None

    def create_smart_playlist(
        self,
        name: str,
        smart_list: SmartList,
        parent: Optional[Any] = None,
        sequence: Optional[int] = None,
    ) -> Optional[Any]:
        """
        Create a smart playlist.

        Args:
            name: Playlist name
            smart_list: SmartList object with conditions
            parent: Parent playlist object
            sequence: Optional sequence number

        Returns:
            Created playlist object or None if failed
        """
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            playlist = self._db.create_smart_playlist(
                name, smart_list=smart_list, parent=parent, seq=sequence
            )
            log_success(logger, f"Created smart playlist: {name}")
            return playlist

        except Exception as e:
            log_exception(logger, e, f"creating smart playlist {name}")
            return None

    def playlist_exists(self, name: str, parent_id: Optional[str] = None) -> bool:
        """
        Check if playlist exists.

        Args:
            name: Playlist name
            parent_id: Optional parent playlist ID

        Returns:
            True if playlist exists, False otherwise
        """
        return self.get_playlist_by_name(name, parent_id) is not None

    # Tag operations
    def get_tags(self, **filters: Any) -> List[Any]:
        """
        Get tags with optional filters.

        Args:
            **filters: Filter criteria for tag query

        Returns:
            List of tag items
        """
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            if filters:
                query = self._db.get_my_tag(**filters)
                return list(query.all())
            else:
                return list(self._db.get_my_tag())

        except Exception as e:
            log_exception(logger, e, f"querying tags with filters {filters}")
            raise DatabaseQueryError(f"Failed to query tags: {e}") from e

    def get_tag_by_name(self, name: str) -> Optional[Any]:
        """
        Get tag by name.

        Args:
            name: Tag name to search for

        Returns:
            Tag item or None if not found
        """
        try:
            tags = self.get_tags(Name=name)
            return tags[0] if tags else None
        except (DatabaseQueryError, IndexError):
            return None

    def get_tag_by_id(self, tag_id: Union[str, int]) -> Optional[Any]:
        """
        Get tag by ID.

        Args:
            tag_id: Tag ID to search for

        Returns:
            Tag item or None if not found
        """
        try:
            tags = self.get_tags(ID=str(tag_id))
            return tags[0] if tags else None
        except (DatabaseQueryError, IndexError):
            return None

    # Artist operations
    def get_artists(self, **filters: Any) -> List[Any]:
        """Get artists with optional filters."""
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            if filters:
                query = self._db.get_artist(**filters)
                return list(query.all())
            else:
                return list(self._db.get_artist())
        except Exception as e:
            log_exception(logger, e, f"querying artists with filters {filters}")
            raise DatabaseQueryError(f"Failed to query artists: {e}") from e

    def get_artist_by_name(self, name: str) -> Optional[Any]:
        """Get artist by name."""
        try:
            artists = self.get_artists(Name=name)
            return artists[0] if artists else None
        except (DatabaseQueryError, IndexError):
            return None

    def create_artist(self, name: str) -> Optional[Any]:
        """Create a new artist."""
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            artist = self._db.add_artist(name)
            log_success(logger, f"Created artist: {name}")
            return artist
        except Exception as e:
            log_exception(logger, e, f"creating artist {name}")
            return None

    # Album operations
    def get_albums(self, **filters: Any) -> List[Any]:
        """Get albums with optional filters."""
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            if filters:
                query = self._db.get_album(**filters)
                return list(query.all())
            else:
                return list(self._db.get_album())
        except Exception as e:
            log_exception(logger, e, f"querying albums with filters {filters}")
            raise DatabaseQueryError(f"Failed to query albums: {e}") from e

    def get_album_by_name(self, name: str) -> Optional[Any]:
        """Get album by name."""
        try:
            albums = self.get_albums(Name=name)
            return albums[0] if albums else None
        except (DatabaseQueryError, IndexError):
            return None

    def create_album(self, name: str) -> Optional[Any]:
        """Create a new album."""
        self.ensure_connected()
        assert self._db is not None  # ensured by ensure_connected()
        try:
            album = self._db.add_album(name)
            log_success(logger, f"Created album: {name}")
            return album
        except Exception as e:
            log_exception(logger, e, f"creating album {name}")
            return None

    # Context manager support
    def __enter__(self) -> "RekordboxDatabase":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if exc_type is not None:
            try:
                self.rollback()
            except Exception as rollback_error:
                log_exception(logger, rollback_error, "rollback during exception handling")

        self.close()

    @contextmanager
    def transaction(self) -> Any:
        """Context manager for database transactions."""
        try:
            yield self
            self.commit()
        except Exception as e:
            self.rollback()
            raise

    def __del__(self) -> None:
        """Cleanup on deletion."""
        if hasattr(self, "_db") and self._db is not None:
            try:
                self.close()
            except Exception:
                pass  # Ignore errors during cleanup
