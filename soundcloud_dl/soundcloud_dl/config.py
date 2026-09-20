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

SOUNDCLOUD_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"  # noqa: S105
SOUNDCLOUD_API_BASE = "https://api.soundcloud.com"

# Must match a redirect URI registered on the SoundCloud app exactly, character for
# character, or the authorize step rejects the request before a sign-in is even offered.
SOUNDCLOUD_REDIRECT_URI = os.getenv("SOUNDCLOUD_REDIRECT_URI", "http://localhost:8080/callback")

# ── Judgment gate pilot (--jev) ────────────────────────────────────────────────
# Cross-cutting third-party key, not soundcloud_dl-specific — no TUNEWRANGLER_SC_ prefix,
# matching the SOUNDCLOUD_CLIENT_ID/SECRET precedent above.
TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY")

# ── Phase 2: Browser / gate form values ───────────────────────────────────────
# No default, and validated before any gate runs. A gate form belongs to a third party and
# the address typed into it is a real person's; a fallback here put one in the repo and sent
# it to every gate this was ever pointed at.
DOWNLOAD_EMAIL = os.getenv("TUNEWRANGLER_SC_EMAIL", "")
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


def get_runs_dir() -> Path:
    """Return per-run gate artifact directory (created if needed)."""
    runs_dir = get_log_dir() / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    return runs_dir


def get_processed_file() -> Path:
    """Path to JSON file storing processed track URLs per playlist (for resume)."""
    return get_log_dir() / "processed.json"


def get_playlist_cache_file() -> Path:
    """Path to JSON file storing cached playlist track lists (by playlist URL)."""
    return get_log_dir() / "playlist_cache.json"


def get_token_file() -> Path:
    """Path to the user OAuth token store. Under logs/, which is gitignored."""
    return get_log_dir() / "oauth_token.json"


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


def validate_gate_form_config() -> None:
    """Raise unless the values a gate form gets filled with are configured.

    Called by every path that drives a gate, because a missing address is only discovered
    when a form is already half-filled on someone else's site.
    """
    if not DOWNLOAD_EMAIL.strip():
        msg = (
            "TUNEWRANGLER_SC_EMAIL is required — gates ask for an email address, and there "
            "is deliberately no default. Set it in .env or the environment."
        )
        raise RuntimeError(msg)


def validate_phase2_config() -> None:
    """Raise if config required for Phase 2 (stealth Playwright) is invalid."""
    # No LLM required. Playwright + browser profile are enough.
    validate_gate_form_config()
    if DOWNLOAD_DIR is not None and not DOWNLOAD_DIR.parent.exists():
        msg = f"TUNEWRANGLER_SC_DOWNLOAD_DIR parent does not exist: {DOWNLOAD_DIR.parent}"
        raise RuntimeError(msg)


def validate_jev_config() -> None:
    """Raise if config required for the --jev judgment pilot is missing."""
    validate_gate_form_config()
    if not TYPESAFE_API_KEY or not TYPESAFE_API_KEY.strip():
        msg = "TYPESAFE_API_KEY is required for --jev. Set it in .env or the environment."
        raise RuntimeError(msg)
