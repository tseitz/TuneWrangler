"""Load environment and constants for SoundCloud free-download automation."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = TuneWrangler (parent of soundcloud_dl project dir)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(Path.cwd() / ".env")


def _parse_int_env(name: str, default: int) -> int:
    val = os.getenv(name, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


# ── Phase 1: SoundCloud API ────────────────────────────────────────────────────
TUNEWRANGLER_SC_PLAYLIST_URL = os.getenv("TUNEWRANGLER_SC_PLAYLIST_URL")
SOUNDCLOUD_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID")
SOUNDCLOUD_CLIENT_SECRET = os.getenv("SOUNDCLOUD_CLIENT_SECRET")

# ── Phase 2: Browser / gate form values ───────────────────────────────────────
DOWNLOAD_EMAIL = os.getenv("TUNEWRANGLER_SC_EMAIL", "tdseitz10@outlook.com")
DOWNLOAD_NAME = os.getenv("TUNEWRANGLER_SC_NAME", "Tom")
DOWNLOAD_COMMENT = os.getenv("TUNEWRANGLER_SC_COMMENT", "🔥🔥🔥")

# Headed browser (visible window). Set TUNEWRANGLER_SC_HEADED=1 in .env.
HEADED = os.getenv("TUNEWRANGLER_SC_HEADED", "").lower() in ("1", "true", "yes")

# ── Phase 2: Chrome bring-up (CDP attach) ─────────────────────────────────────
CHROME_PATH: str = os.getenv(
    "TUNEWRANGLER_SC_CHROME_PATH",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

CHROME_DEBUG_PORT: int = _parse_int_env("TUNEWRANGLER_SC_CHROME_DEBUG_PORT", 9222)

_chrome_profile_env = os.getenv("TUNEWRANGLER_SC_CHROME_PROFILE_DIR", "").strip()
CHROME_PROFILE_DIR: Path = (
    Path(_chrome_profile_env).expanduser().resolve()
    if _chrome_profile_env
    else (_PROJECT_ROOT / "soundcloud_dl_chrome_profile").resolve()
)

# Optional download directory for browser-triggered downloads.
_download_dir = os.getenv("TUNEWRANGLER_SC_DOWNLOAD_DIR", "").strip()
DOWNLOAD_DIR: Path | None = Path(_download_dir).expanduser().resolve() if _download_dir else None

# Seconds between tracks (rate limiting).
try:
    DELAY_SECONDS = max(0.0, float(os.getenv("TUNEWRANGLER_SC_DELAY_SECONDS", "3")))
except ValueError:
    DELAY_SECONDS = 3.0

# ── Phase 2: Human-like timing ────────────────────────────────────────────────
# Random pause between Playwright actions (ms). Makes the bot look less robotic.
ACTION_DELAY_MIN_MS = _parse_int_env("TUNEWRANGLER_SC_ACTION_DELAY_MIN_MS", 300)
ACTION_DELAY_MAX_MS = _parse_int_env("TUNEWRANGLER_SC_ACTION_DELAY_MAX_MS", 900)

# Per-keystroke delay when filling text fields (ms).
TYPE_DELAY_MS = _parse_int_env("TUNEWRANGLER_SC_TYPE_DELAY_MS", 80)

# Scroll element into view before clicking (1 = enabled).
_scroll = os.getenv("TUNEWRANGLER_SC_SCROLL_BEFORE_CLICK", "1").strip()
SCROLL_BEFORE_CLICK = _scroll not in ("0", "false", "no")

# Seconds to wait after a SoundCloud track page load before interacting (SPA render time).
PAGE_LOAD_WAIT_SECONDS = max(0, _parse_int_env("TUNEWRANGLER_SC_PAGE_LOAD_WAIT", 3))

# ── Resume / cache ─────────────────────────────────────────────────────────────
_resume = os.getenv("TUNEWRANGLER_SC_RESUME", "1").strip().lower()
RESUME_ENABLED = _resume not in ("0", "false", "no")

_playlist_cache = os.getenv("TUNEWRANGLER_SC_PLAYLIST_CACHE", "1").strip().lower()
PLAYLIST_CACHE_ENABLED = _playlist_cache not in ("0", "false", "no")


# ── Path helpers ───────────────────────────────────────────────────────────────


def get_log_dir() -> Path:
    """Return soundcloud_dl logs directory (created if needed)."""
    log_dir = _PROJECT_ROOT / "logs" / "soundcloud_dl"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_debug_dir() -> Path:
    """Return debug screenshot directory (created if needed)."""
    debug_dir = get_log_dir() / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def get_processed_file() -> Path:
    """Path to JSON file storing processed track URLs per playlist (for resume)."""
    return get_log_dir() / "processed.json"


def get_playlist_cache_file() -> Path:
    """Path to JSON file storing cached playlist track lists (by playlist URL)."""
    return get_log_dir() / "playlist_cache.json"


# ── Validation ─────────────────────────────────────────────────────────────────


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


def validate_phase2_config() -> None:
    """Raise if config required for Phase 2 (stealth Playwright) is invalid."""
    # No LLM required. Playwright + browser profile are enough.
    if DOWNLOAD_DIR is not None and not DOWNLOAD_DIR.parent.exists():
        msg = f"TUNEWRANGLER_SC_DOWNLOAD_DIR parent does not exist: {DOWNLOAD_DIR.parent}"
        raise RuntimeError(msg)
