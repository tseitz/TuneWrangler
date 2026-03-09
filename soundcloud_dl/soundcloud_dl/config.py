"""Load environment and constants for SoundCloud free-download automation."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = TuneWrangler (parent of soundcloud_dl project dir)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(Path.cwd() / ".env")

# Required for Phase 1 (playlist extraction via API)
TUNEWRANGLER_SC_PLAYLIST_URL = os.getenv("TUNEWRANGLER_SC_PLAYLIST_URL")
SOUNDCLOUD_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID")
SOUNDCLOUD_CLIENT_SECRET = os.getenv("SOUNDCLOUD_CLIENT_SECRET")

# Optional (for Phase 2 / browser-use agent)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BROWSERLESS_WS_URL = os.getenv("BROWSERLESS_WS_URL", "wss://production-sfo.browserless.io")
BROWSERLESS_TOKEN = os.getenv("BROWSERLESS_TOKEN")

# SoundCloud download prompts (from .env)
DOWNLOAD_EMAIL = os.getenv("TUNEWRANGLER_SC_EMAIL", "tdseitz10@outlook.com")
SC_USERNAME = os.getenv("TUNEWRANGLER_SC_USERNAME", "")
DOWNLOAD_COMMENT = os.getenv("TUNEWRANGLER_SC_COMMENT", "🔥🔥🔥")

# Run browser with visible window (Phase 2 only)
HEADED = os.getenv("TUNEWRANGLER_SC_HEADED", "").lower() in ("1", "true", "yes")


def get_log_dir() -> Path:
    """Return project logs directory (created if needed)."""
    log_dir = _PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def validate_phase1_config() -> None:
    """Raise if config required for Phase 1 (SoundCloud API) is missing."""
    if not TUNEWRANGLER_SC_PLAYLIST_URL or not TUNEWRANGLER_SC_PLAYLIST_URL.strip():
        msg = "TUNEWRANGLER_SC_PLAYLIST_URL is required. Set it in .env or the environment."
        raise RuntimeError(msg)
    if "soundcloud.com" not in TUNEWRANGLER_SC_PLAYLIST_URL:
        msg = "TUNEWRANGLER_SC_PLAYLIST_URL must be a SoundCloud URL."
        raise ValueError(msg)
    if not SOUNDCLOUD_CLIENT_ID or not SOUNDCLOUD_CLIENT_SECRET:
        msg = (
            "SOUNDCLOUD_CLIENT_ID and SOUNDCLOUD_CLIENT_SECRET are required for the API. "
            "Register an app at https://soundcloud.com/you/apps and set them in .env."
        )
        raise RuntimeError(msg)
