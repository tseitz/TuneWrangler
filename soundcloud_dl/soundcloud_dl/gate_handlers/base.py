"""Base GateHandler: loads YAML step config and interprets steps presence-first."""

from __future__ import annotations

import logging
import random
import re
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.gate_handlers.base")


class StepResult(StrEnum):
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"


class GateStepError(RuntimeError):
    """Raised when a required step cannot find its element."""


class GateHandler:
    """
    Loads a YAML step config and executes steps against a Playwright page.

    Steps are presence-driven: each step queries for its trigger element before
    acting. Optional steps are silently skipped when absent. Steps with depends_on
    are skipped if their parent step was skipped.
    """

    #: Subclasses set this to the path of their YAML config file.
    config_path: Path | None = None

    def __init__(  # noqa: PLR0913
        self,
        *,
        config: dict | None = None,
        template_vars: dict[str, str] | None = None,
        action_delay_min_ms: int = 300,
        action_delay_max_ms: int = 900,
        type_delay_ms: int = 80,
        scroll_before_click: bool = True,
    ) -> None:
        if config is None:
            if self.config_path is None:
                msg = "Either pass config= or set config_path on the subclass."
                raise ValueError(msg)
            with self.config_path.open() as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                msg = f"YAML config at {self.config_path} is empty or not a mapping."
                raise TypeError(msg)

        self.gate_name: str = config["gate"]
        self.steps: list[dict] = config.get("steps", [])
        self.template_vars: dict[str, str] = template_vars or {}
        self.action_delay_min_ms = action_delay_min_ms
        self.action_delay_max_ms = action_delay_max_ms
        self.type_delay_ms = type_delay_ms
        self.scroll_before_click = scroll_before_click

    def resolve_value(self, value: str) -> str:
        """Substitute {{var}} placeholders from template_vars. Raises KeyError if missing."""

        def replace(m: re.Match[str]) -> str:
            key = m.group(1)
            if key not in self.template_vars:
                msg = f"Template var '{{{key}}}' not in template_vars"
                raise KeyError(msg)
            return self.template_vars[key]

        return re.sub(r"\{\{(\w+)\}\}", replace, value)

    async def _random_delay(self, page: Page) -> None:
        ms = random.randint(self.action_delay_min_ms, self.action_delay_max_ms)  # noqa: S311
        await page.wait_for_timeout(ms)

    async def _find_element(self, page: Page, trigger: str) -> Any | None:  # noqa: ANN401
        """Try each comma-separated selector; return first match or None."""
        for selector in [s.strip() for s in trigger.split(",")]:
            el = await page.query_selector(selector)
            if el:
                return el
        return None

    async def _execute_step(self, page: Page, step: dict) -> None:
        """Execute a single step action against the found element."""
        el = await self._find_element(page, step["trigger"])
        if el is None:
            return  # caller handles required/optional logic

        action = step["action"]
        if self.scroll_before_click and action in ("click", "fill"):
            await el.scroll_into_view_if_needed()

        await self._random_delay(page)

        if action == "click":
            await el.click()
        elif action == "fill":
            value = self.resolve_value(step.get("value", ""))
            await el.fill("")  # clear first
            await el.type(value, delay=self.type_delay_ms)
        elif action == "wait":
            timeout_ms = int(step.get("timeout_ms", 5000))
            await page.wait_for_selector(step["trigger"], timeout=timeout_ms)

    async def run(self, page: Page) -> dict[str, StepResult]:
        """
        Walk all steps. Return a dict of step_id → StepResult.

        Raises GateStepError if a required step's element is not found.
        """
        results: dict[str, StepResult] = {}

        for step in self.steps:
            step_id: str = step["id"]
            trigger: str = step["trigger"]
            is_required: bool = step.get("required", False)
            depends_on: str | None = step.get("depends_on")

            # Skip if parent step was skipped
            if depends_on and results.get(depends_on) == StepResult.SKIPPED:
                logger.debug(
                    "[%s] Skipping '%s' (depends_on '%s' was skipped)",
                    self.gate_name,
                    step_id,
                    depends_on,
                )
                results[step_id] = StepResult.SKIPPED
                continue

            el = await self._find_element(page, trigger)

            if el is None:
                if is_required:
                    msg = (
                        f"[{self.gate_name}] Required step '{step_id}' could not find "
                        f"trigger element: {trigger}"
                    )
                    raise GateStepError(msg)
                logger.debug(
                    "[%s] Skipping optional step '%s' (element not found)",
                    self.gate_name,
                    step_id,
                )
                results[step_id] = StepResult.SKIPPED
                continue

            logger.info(
                "[%s] Executing step '%s' (%s)", self.gate_name, step_id, step["action"]
            )
            await self._execute_step(page, step)
            results[step_id] = StepResult.EXECUTED

        return results
