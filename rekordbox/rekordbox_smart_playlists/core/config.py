"""
Configuration management for Rekordbox Smart Playlists.

Provides centralized configuration handling with support for:
- Environment variables
- Configuration files (JSON/TOML)
- Command-line overrides
- Default values
"""

import os
import json
import toml
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Configuration class with default values and validation."""

    # Paths
    collection_path: str = field(
        default_factory=lambda: os.path.expanduser("~/Dropbox/DJ/Dane Dubz DJ Music/Collection")
    )
    playlist_data_path: str = field(default_factory=lambda: "playlist-data")
    backup_base_path: str = field(
        default_factory=lambda: os.path.expanduser("~/Dropbox/DJ/Rekordbox DB Backup")
    )
    pioneer_install_dir: str = field(default_factory=lambda: "/Applications/rekordbox 6")

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

    # Audio file extensions
    audio_extensions: set = field(
        default_factory=lambda: {".mp3", ".wav", ".flac", ".aiff", ".m4a"}
    )

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None

    @classmethod
    def from_file(cls, config_path: Union[str, Path]) -> "Config":
        """Load configuration from a file (JSON or TOML)."""
        config_path = Path(config_path)

        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}")
            return cls()

        try:
            if config_path.suffix.lower() == ".json":
                with open(config_path, "r") as f:
                    config_data = json.load(f)
            elif config_path.suffix.lower() == ".toml":
                config_data = toml.load(config_path)
            else:
                logger.error(f"Unsupported configuration file format: {config_path.suffix}")
                return cls()

            return cls.from_dict(config_data)

        except (json.JSONDecodeError, toml.TomlDecodeError) as e:
            logger.error(f"Error parsing configuration file {config_path}: {e}")
            return cls()
        except Exception as e:
            logger.error(f"Error loading configuration file {config_path}: {e}")
            return cls()

    @classmethod
    def from_dict(cls, config_data: Dict[str, Any]) -> "Config":
        """Create Config instance from dictionary."""
        # Create instance with defaults
        config = cls()

        # Update with provided values
        for key, value in config_data.items():
            if hasattr(config, key):
                # Handle special cases
                if key == "audio_extensions" and isinstance(value, list):
                    setattr(config, key, set(value))
                else:
                    setattr(config, key, value)
            else:
                logger.warning(f"Unknown configuration key: {key}")

        return config

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        config = cls()

        env_mapping = {
            "REKORDBOX_COLLECTION_PATH": "collection_path",
            "REKORDBOX_PLAYLIST_DATA_PATH": "playlist_data_path",
            "REKORDBOX_BACKUP_PATH": "backup_base_path",
            "REKORDBOX_PIONEER_INSTALL": "pioneer_install_dir",
            "REKORDBOX_DRY_RUN": "dry_run",
            "REKORDBOX_VERBOSE": "verbose",
            "REKORDBOX_LOG_LEVEL": "log_level",
            "REKORDBOX_LOG_FILE": "log_file",
        }

        for env_var, config_key in env_mapping.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert string values to appropriate types
                if config_key in [
                    "dry_run",
                    "verbose",
                    "auto_backup",
                    "backup_before_changes",
                ]:
                    bool_value = value.lower() in ("true", "1", "yes", "on")
                    setattr(config, config_key, bool_value)
                elif config_key in ["max_backups", "progress_interval"]:
                    try:
                        int_value = int(value)
                        setattr(config, config_key, int_value)
                    except ValueError:
                        logger.warning(f"Invalid integer value for {env_var}: {value}")
                        continue
                else:
                    setattr(config, config_key, value)

        return config

    def merge_with(self, other: "Config") -> "Config":
        """Merge this configuration with another, giving priority to the other."""
        merged_data = {}

        # Start with this config's values
        for field_name in self.__dataclass_fields__:
            merged_data[field_name] = getattr(self, field_name)

        # Override with other config's non-default values
        for field_name in other.__dataclass_fields__:
            other_value = getattr(other, field_name)
            default_value = self.__dataclass_fields__[field_name].default

            # If other has a non-default value, use it
            if other_value != default_value:
                merged_data[field_name] = other_value

        return Config.from_dict(merged_data)

    def validate(self) -> bool:
        """Validate configuration values."""
        is_valid = True

        # Validate paths
        required_paths = {
            "collection_path": self.collection_path,
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        result = {}
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if isinstance(value, set):
                value = list(value)  # Convert sets to lists for serialization
            result[field_name] = value
        return result

    def save_to_file(self, config_path: Union[str, Path]) -> bool:
        """Save configuration to file."""
        config_path = Path(config_path)

        try:
            config_data = self.to_dict()

            if config_path.suffix.lower() == ".json":
                with open(config_path, "w") as f:
                    json.dump(config_data, f, indent=2)
            elif config_path.suffix.lower() == ".toml":
                with open(config_path, "w") as f:
                    toml.dump(config_data, f)
            else:
                logger.error(f"Unsupported configuration file format: {config_path.suffix}")
                return False

            logger.info(f"Configuration saved to: {config_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving configuration to {config_path}: {e}")
            return False

    def __str__(self) -> str:
        """String representation of configuration."""
        lines = ["Configuration:"]
        for field_name in sorted(self.__dataclass_fields__.keys()):
            value = getattr(self, field_name)
            lines.append(f"  {field_name}: {value}")
        return "\n".join(lines)


def load_config(
    config_file: Optional[Union[str, Path]] = None, use_env: bool = True, **overrides
) -> Config:
    """
    Load configuration from multiple sources with precedence:
    1. Command-line overrides (highest priority)
    2. Configuration file
    3. Environment variables
    4. Defaults (lowest priority)
    """
    # Start with defaults
    config = Config()

    # Apply environment variables
    if use_env:
        env_config = Config.from_env()
        config = config.merge_with(env_config)

    # Apply configuration file
    if config_file:
        file_config = Config.from_file(config_file)
        config = config.merge_with(file_config)

    # Apply command-line overrides
    if overrides:
        override_config = Config.from_dict(overrides)
        config = config.merge_with(override_config)

    # Validate final configuration
    if not config.validate():
        logger.warning("Configuration validation failed, some features may not work correctly")

    return config


def get_default_config_paths() -> list[Path]:
    """Get list of default configuration file locations to search."""
    return [
        Path.cwd() / "config.json",
        Path.cwd() / "config.toml",
        Path.cwd() / ".rekordbox-config.json",
        Path.cwd() / ".rekordbox-config.toml",
        Path.home() / ".config" / "rekordbox-smart-playlists" / "config.json",
        Path.home() / ".config" / "rekordbox-smart-playlists" / "config.toml",
    ]


def find_config_file() -> Optional[Path]:
    """Find the first existing configuration file in default locations."""
    for config_path in get_default_config_paths():
        if config_path.exists():
            return config_path
    return None


if __name__ == "__main__":
    # Example usage and testing
    config = load_config()
    print(config)
