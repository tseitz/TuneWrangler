"""Resume support: persist per-track processing state per playlist."""

from __future__ import annotations

import json
import logging
from typing import Literal

from soundcloud_dl.config import get_processed_file

logger = logging.getLogger("soundcloud_dl.resume")

#: Track state. "done" tracks are skipped on re-runs; all others are retried.
TrackState = Literal["done", "captcha_pending", "manual_review", "failed"]

#: States that should NOT be retried on re-run.
_SKIP_STATES: frozenset[str] = frozenset({"done"})


def _normalize_playlist_url(url: str) -> str:
    return url.rstrip("/")


def _read_raw() -> dict:
    path = get_processed_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read resume file %s: %s", path, e)
        return {}
    return data if isinstance(data, dict) else {}


def load_states(playlist_url: str) -> dict[str, str]:
    """
    Load track-state map for this playlist. Empty dict if none.

    Backward-compat: if the stored value is a list (old format), every entry
    is treated as "done".
    """
    data = _read_raw()
    key = _normalize_playlist_url(playlist_url)
    entry = data.get(key)
    if isinstance(entry, list):
        return {k: "done" for k in entry if isinstance(k, str)}
    if isinstance(entry, dict):
        return {k: v for k, v in entry.items() if isinstance(k, str) and isinstance(v, str)}
    return {}


def record_state(playlist_url: str, track_url: str, state: TrackState) -> None:
    """Set the state for one track in this playlist; overwrites prior state."""
    path = get_processed_file()
    key = _normalize_playlist_url(playlist_url)
    try:
        data = _read_raw()
        existing = data.get(key)
        if isinstance(existing, list):
            states: dict[str, str] = {k: "done" for k in existing if isinstance(k, str)}
        elif isinstance(existing, dict):
            states = {
                k: v
                for k, v in existing.items()
                if isinstance(k, str) and isinstance(v, str)
            }
        else:
            states = {}
        states[track_url] = state
        data[key] = states
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (OSError, TypeError) as e:
        logger.warning("Could not save resume file %s: %s", path, e)


def should_skip(track_url: str, states: dict[str, str]) -> bool:
    """True if a track should be skipped on this run based on its state."""
    return states.get(track_url) in _SKIP_STATES
