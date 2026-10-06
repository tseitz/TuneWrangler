from pathlib import Path

import pytest

from rekordbox_smart_playlists.core.config import (
    DEFAULT_PLAYLIST_DATA_PATH,
    ConfigurationError,
    load_config,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "TUNEWRANGLER_RB_PLAYLIST_DATA_PATH",
        "TUNEWRANGLER_RB_BACKUP_PATH",
        "TUNEWRANGLER_RB_DRY_RUN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_cli_override_keeps_env_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("TUNEWRANGLER_RB_PLAYLIST_DATA_PATH", "/env/pd")
    monkeypatch.setenv("TUNEWRANGLER_RB_BACKUP_PATH", str(tmp_path))

    config = load_config(dry_run=True, log_level="DEBUG")

    assert config.dry_run is True
    assert config.playlist_data_path == "/env/pd"
    assert config.backup_base_path == str(tmp_path)


def test_playlist_data_defaults_to_the_package_folder():
    config = load_config()

    assert config.playlist_data_path == DEFAULT_PLAYLIST_DATA_PATH
    assert (Path(DEFAULT_PLAYLIST_DATA_PATH) / "_order.json").is_file()


@pytest.mark.parametrize("value", [None, "", "   "])
def test_backup_dir_refuses_unset_or_blank(monkeypatch, value):
    if value is not None:
        monkeypatch.setenv("TUNEWRANGLER_RB_BACKUP_PATH", value)

    with pytest.raises(ConfigurationError, match="TUNEWRANGLER_RB_BACKUP_PATH"):
        load_config().require_backup_dir()


def test_backup_dir_refuses_missing_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("TUNEWRANGLER_RB_BACKUP_PATH", str(tmp_path / "unplugged"))

    with pytest.raises(ConfigurationError, match="does not exist"):
        load_config().require_backup_dir()
    assert not (tmp_path / "unplugged").exists()


def test_backup_dir_refuses_relative_path(monkeypatch):
    monkeypatch.setenv("TUNEWRANGLER_RB_BACKUP_PATH", "logs")

    with pytest.raises(ConfigurationError, match="absolute"):
        load_config().require_backup_dir()


def test_misspelled_boolean_is_refused(monkeypatch):
    monkeypatch.setenv("TUNEWRANGLER_RB_DRY_RUN", "ture")

    with pytest.raises(ConfigurationError, match="TUNEWRANGLER_RB_DRY_RUN"):
        load_config()
