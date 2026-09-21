"""Resume support: persist per-track processing state per playlist."""

from __future__ import annotations

import json
import logging
from typing import Literal, cast

from soundcloud_dl.config import get_processed_file

logger = logging.getLogger("soundcloud_dl.resume")

#: Track state. "done" and "unsupported" are skipped on re-runs; all others are retried.
TrackState = Literal[
    "done", "unsupported", "captcha_pending", "login_required", "manual_review", "failed"
]

#: States that should NOT be retried on re-run.
_SKIP_STATES: frozenset[str] = frozenset({"done", "unsupported"})

#: States worth another go, but not forever. A gate that stopped for a transient reason —
#: a slow page, a slide that did not render that time — succeeds on a later run. One that
#: wants a person cannot, and retrying it costs a minute of every batch from then on.
_BUDGETED_STATES: frozenset[str] = frozenset({"manual_review"})
_MAX_ATTEMPTS = 3


def _entry_state(value: object) -> str | None:
    """The state from a stored entry, which is a bare string before attempts were kept."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Cast: ty narrows isinstance(x, dict) to dict[Unknown, Unknown], which rejects a
        # string-literal key. Same workaround as playlist_cache._item_to_track.
        state = cast("dict[str, object]", value).get("state")
        return state if isinstance(state, str) else None
    return None


def _entry_attempts(value: object) -> int:
    if isinstance(value, dict):
        attempts = cast("dict[str, object]", value).get("attempts")
        if isinstance(attempts, int):
            return attempts
    # A pre-migration entry has no count. Treating it as zero spends the budget from here
    # rather than retiring a track on the strength of runs nobody recorded.
    return 0


def _entry_reason(value: object) -> str:
    if isinstance(value, dict):
        reason = cast("dict[str, object]", value).get("reason")
        if isinstance(reason, str):
            return reason
    return ""


def load_reasons(playlist_url: str) -> dict[str, str]:
    """Why each track ended where it did, for the ones that said."""
    return _coerce_to_reason_map(_read_raw().get(_normalize_playlist_url(playlist_url)))


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


def _coerce_to_state_map(entry: object) -> dict[str, str]:
    """Normalize a stored playlist entry to a state map, tolerating legacy list format."""
    if isinstance(entry, list):
        return {k: "done" for k in entry if isinstance(k, str)}
    if isinstance(entry, dict):
        states = ((k, _entry_state(v)) for k, v in entry.items() if isinstance(k, str))
        return {k: v for k, v in states if v is not None}
    return {}


def _coerce_to_attempt_map(entry: object) -> dict[str, int]:
    if not isinstance(entry, dict):
        return {}
    return {k: _entry_attempts(v) for k, v in entry.items() if isinstance(k, str)}


def _coerce_to_reason_map(entry: object) -> dict[str, str]:
    if not isinstance(entry, dict):
        return {}
    return {k: _entry_reason(v) for k, v in entry.items() if isinstance(k, str)}


def _entry(state: str, attempts: int, reason: str) -> dict[str, object]:
    """One stored track record. The reason is omitted when there is nothing to say, so a
    file of successful tracks stays as readable as it was before reasons existed."""
    record: dict[str, object] = {"state": state, "attempts": attempts}
    if reason:
        record["reason"] = reason
    return record


def load_states(playlist_url: str) -> dict[str, str]:
    """
    Load track-state map for this playlist. Empty dict if none.

    Backward-compat: if the stored value is a list (old format), every entry
    is treated as "done".
    """
    data = _read_raw()
    key = _normalize_playlist_url(playlist_url)
    return _coerce_to_state_map(data.get(key))


def load_attempts(playlist_url: str) -> dict[str, int]:
    """How many times each track has landed in a state that is retried on a budget."""
    return _coerce_to_attempt_map(_read_raw().get(_normalize_playlist_url(playlist_url)))


def record_state(playlist_url: str, track_url: str, state: TrackState, reason: str = "") -> None:
    """Set the state for one track in this playlist; overwrites prior state.

    A budgeted state also bumps that track's attempt count, and any other state clears it:
    a track that got somewhere new has not spent an attempt on being stuck.

    The reason is kept alongside so a track that needs attention says what is wrong with
    it here, rather than only in a rotating log that ages the answer out.
    """
    path = get_processed_file()
    key = _normalize_playlist_url(playlist_url)
    try:
        data = _read_raw()
        entry = data.get(key)
        states = _coerce_to_state_map(entry)
        attempts = _coerce_to_attempt_map(entry)
        reasons = _coerce_to_reason_map(entry)
        states[track_url] = state
        attempts[track_url] = attempts.get(track_url, 0) + 1 if state in _BUDGETED_STATES else 0
        reasons[track_url] = reason
        data[key] = {
            url: _entry(s, attempts.get(url, 0), reasons.get(url, "")) for url, s in states.items()
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (OSError, TypeError) as e:
        logger.warning("Could not save resume file %s: %s", path, e)


def should_skip(
    track_url: str, states: dict[str, str], attempts: dict[str, int] | None = None
) -> bool:
    """True if a track should be skipped on this run based on its state."""
    return states.get(track_url) in _SKIP_STATES or is_given_up_on(track_url, states, attempts)


def is_given_up_on(
    track_url: str, states: dict[str, str], attempts: dict[str, int] | None = None
) -> bool:
    """True for a track skipped because it stayed stuck, rather than because it is done.

    Separate from should_skip so the run can name these: a gate nothing will raise again,
    and that only a person can decide to take further.
    """
    if attempts is None or states.get(track_url) not in _BUDGETED_STATES:
        return False
    return attempts.get(track_url, 0) >= _MAX_ATTEMPTS
