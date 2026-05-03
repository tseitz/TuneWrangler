"""Tests for config.py values and helpers."""

import importlib
import os


def _reload_config(**env_overrides):
    """Reload config module with patched env vars."""
    for k, v in env_overrides.items():
        os.environ[k] = v
    import soundcloud_dl.config as cfg
    importlib.reload(cfg)
    return cfg


def test_action_delay_defaults():
    cfg = _reload_config()
    assert cfg.ACTION_DELAY_MIN_MS == 300
    assert cfg.ACTION_DELAY_MAX_MS == 900


def test_action_delay_from_env():
    cfg = _reload_config(
        TUNEWRANGLER_SC_ACTION_DELAY_MIN_MS="100",
        TUNEWRANGLER_SC_ACTION_DELAY_MAX_MS="500",
    )
    assert cfg.ACTION_DELAY_MIN_MS == 100
    assert cfg.ACTION_DELAY_MAX_MS == 500


def test_type_delay_default():
    cfg = _reload_config()
    assert cfg.TYPE_DELAY_MS == 80


def test_download_name_default():
    cfg = _reload_config()
    assert cfg.DOWNLOAD_NAME == "Tom"


def test_validate_phase2_passes_with_no_extra_config():
    """validate_phase2_config should pass with no special config (no LLM required)."""
    import soundcloud_dl.config as cfg
    cfg.validate_phase2_config()  # should not raise — no LLM dependency


def test_chrome_path_default_macos():
    cfg = _reload_config()
    assert "/Applications/Google Chrome.app" in cfg.CHROME_PATH


def test_chrome_path_from_env():
    cfg = _reload_config(TUNEWRANGLER_SC_CHROME_PATH="/custom/chrome")
    assert cfg.CHROME_PATH == "/custom/chrome"


def test_chrome_debug_port_default():
    cfg = _reload_config()
    assert cfg.CHROME_DEBUG_PORT == 9222


def test_chrome_debug_port_from_env():
    cfg = _reload_config(TUNEWRANGLER_SC_CHROME_DEBUG_PORT="9333")
    assert cfg.CHROME_DEBUG_PORT == 9333


def test_chrome_profile_dir_default():
    cfg = _reload_config()
    assert str(cfg.CHROME_PROFILE_DIR).endswith("soundcloud_dl_chrome_profile")


def test_chrome_profile_dir_from_env(tmp_path):
    cfg = _reload_config(TUNEWRANGLER_SC_CHROME_PROFILE_DIR=str(tmp_path / "custom"))
    assert (tmp_path / "custom").resolve() == cfg.CHROME_PROFILE_DIR
