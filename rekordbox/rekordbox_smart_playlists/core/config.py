"""
Configuration management for Rekordbox Smart Playlists.

Settings come from TUNEWRANGLER_RB_* environment variables (the repo-root .env is loaded),
then command-line overrides.
"""

import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent
DEFAULT_PLAYLIST_DATA_PATH = str(PACKAGE_ROOT / "playlist-data")

load_dotenv(REPO_ROOT / ".env")

BACKUP_PATH_ENV = "TUNEWRANGLER_RB_BACKUP_PATH"

_ENV_MAPPING = {
    "TUNEWRANGLER_RB_PLAYLIST_DATA_PATH": "playlist_data_path",
    BACKUP_PATH_ENV: "backup_base_path",
    "TUNEWRANGLER_RB_PARENT_PLAYLIST": "default_parent_playlist",
    "TUNEWRANGLER_RB_DRY_RUN": "dry_run",
    "TUNEWRANGLER_RB_VERBOSE": "verbose",
    "TUNEWRANGLER_RB_LOG_LEVEL": "log_level",
    "TUNEWRANGLER_RB_LOG_FILE": "log_file",
}
_BOOL_KEYS = {"dry_run", "verbose"}
_TRUE_WORDS = {"true", "1", "yes", "on"}
_FALSE_WORDS = {"false", "0", "no", "off"}


class ConfigurationError(Exception):
    """A required setting is missing or unusable."""


@dataclass
class Config:
    """Configuration class with default values and validation."""

    # Paths
    playlist_data_path: str = DEFAULT_PLAYLIST_DATA_PATH
    backup_base_path: str | None = None

    # Database paths (auto-detected based on OS)
    pioneer_app_support: str = field(
        default_factory=lambda: os.path.expanduser("~/Library/Application Support/Pioneer")
    )
    pioneer_library: str = field(default_factory=lambda: os.path.expanduser("~/Library/Pioneer"))

    # Playlist settings
    default_parent_playlist: str = "DaneDubz"
    auto_update_playlists: bool = True
    logical_operator_all: bool = True

    # Backup settings
    max_backups: int = 10
    auto_backup: bool = True
    backup_before_changes: bool = True

    # Processing settings
    dry_run: bool = False
    verbose: bool = False
    progress_interval: int = 10

    # Logging
    log_level: str = "INFO"
    log_file: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        """Build configuration from TUNEWRANGLER_RB_* environment variables."""
        values: dict[str, Any] = {}
        for env_var, key in _ENV_MAPPING.items():
            raw = os.getenv(env_var, "").strip()
            if not raw:
                continue
            if key in _BOOL_KEYS:
                if raw.lower() not in _TRUE_WORDS | _FALSE_WORDS:
                    raise ConfigurationError(f"{env_var} must be true or false, got {raw!r}")
                values[key] = raw.lower() in _TRUE_WORDS
            elif key == "playlist_data_path":
                values[key] = str(Path(raw).expanduser())
            else:
                values[key] = raw
        return cls(**values)

    def require_backup_dir(self) -> Path:
        """Return the backup directory, refusing an unset or missing one."""
        if not self.backup_base_path:
            raise ConfigurationError(
                f"{BACKUP_PATH_ENV} is not set. Point it at a folder used only for these "
                "backups: old backups in it are deleted beyond the newest max_backups."
            )
        path = Path(self.backup_base_path).expanduser()
        if not path.is_absolute():
            raise ConfigurationError(f"{BACKUP_PATH_ENV} must be an absolute path: {path}")
        if not path.is_dir():
            raise ConfigurationError(
                f"{BACKUP_PATH_ENV} does not exist or is not a directory: {path}"
            )
        return path

    def validate(self) -> bool:
        """Validate configuration values."""
        is_valid = True

        # Validate paths
        required_paths = {
            "playlist_data_path": self.playlist_data_path,
        }

        for path_name, path_value in required_paths.items():
            path_obj = Path(path_value)
            if not path_obj.exists():
                logger.error(f"Required path does not exist: {path_name} = {path_value}")
                is_valid = False

        # Validate numeric values
        if self.max_backups < 1:
            logger.error("max_backups must be at least 1")
            is_valid = False

        if self.progress_interval < 1:
            logger.error("progress_interval must be at least 1")
            is_valid = False

        # Validate log level
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_log_levels:
            logger.error(f"Invalid log level: {self.log_level}. Must be one of {valid_log_levels}")
            is_valid = False

        return is_valid

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        result = {}
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if isinstance(value, set):
                value = list(value)  # Convert sets to lists for serialization
            result[field_name] = value
        return result

    def __str__(self) -> str:
        """String representation of configuration."""
        lines = ["Configuration:"]
        for field_name in sorted(self.__dataclass_fields__.keys()):
            value = getattr(self, field_name)
            lines.append(f"  {field_name}: {value}")
        return "\n".join(lines)


def load_config(**overrides: Any) -> Config:
    """Load configuration from the environment, then apply command-line overrides."""
    config = replace(Config.from_env(), **overrides)

    if not config.validate():
        logger.warning("Configuration validation failed, some features may not work correctly")

    return config
