"""Per-run artifact directory: a screenshot per turn plus a machine-readable outcome.

Deliberately thin. The DEBUG log already carries the page snapshot, the criteria sent to
the model, its choice and its per-choice probabilities — this records only what the log
cannot: images, and a result file something other than a human can read.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from soundcloud_dl.config import get_runs_dir

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.run_artifacts")


class RunRecorder:
    """Collects screenshots and a result.json under logs/soundcloud_dl/runs/<gate>-<ts>/."""

    def __init__(self, gate_name: str) -> None:
        self.gate_name = gate_name
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        self.dir: Path = get_runs_dir() / f"{gate_name}-{stamp}"
        self.dir.mkdir(parents=True, exist_ok=True)
        logger.info("[%s] recording run → %s", gate_name, self.dir)

    async def screenshot(self, page: Page, label: str) -> None:
        try:
            await page.screenshot(path=str(self.dir / f"{label}.png"))
        except Exception:  # noqa: BLE001
            # Never let artifact collection end a run that is otherwise working.
            logger.warning("[%s] screenshot %r failed", self.gate_name, label, exc_info=True)

    def finish(self, **outcome: Any) -> None:  # noqa: ANN401
        payload = {
            "gate": self.gate_name,
            "finished_at": datetime.now(UTC).isoformat(),
            **outcome,
        }
        try:
            (self.dir / "result.json").write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )
        except OSError:
            logger.warning("[%s] could not write result.json", self.gate_name, exc_info=True)
        logger.info("[%s] run artifacts → %s", self.gate_name, self.dir)
