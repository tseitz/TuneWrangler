"""How the last batch run ended, for a scheduler that only sees the exit code.

The batch exits 0 even when tracks got stuck or the run stopped early, so the outcome is
written to last_run.json. It is deleted when a batch starts, so a file that is present was
written by the run that just ended.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TypedDict

from soundcloud_dl.config import get_last_run_file

logger = logging.getLogger("soundcloud_dl.run_record")

VERSION = 1


class Item(TypedDict):
    title: str
    url: str
    state: str
    reason: str


def _zero_counts() -> dict[str, int]:
    return {
        "done": 0,
        "unsupported": 0,
        "captcha_pending": 0,
        "login_required": 0,
        "manual_review": 0,
        "failed": 0,
    }


@dataclass
class RunRecord:
    run_started_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    finished: bool = False
    stopped_early: bool = False
    error: str | None = None
    untried: int = 0
    counts: dict[str, int] = field(default_factory=_zero_counts)
    needs_attention: list[Item] = field(default_factory=list)
    gave_up: list[Item] = field(default_factory=list)


def clear() -> None:
    get_last_run_file().unlink(missing_ok=True)


def write(record: RunRecord) -> None:
    """Never raises: it runs in a finally, and must not replace the error that got it there."""
    path = get_last_run_file()
    try:
        body = {"version": VERSION, **asdict(record)}
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except (OSError, TypeError) as exc:
        logger.warning("Could not write the run record %s: %s", path, exc)
