# SoundCloud Gate Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flaky LLM browser-use agent with a deterministic, config-driven gate handler
system that uses stealth Playwright to automate Hypeddit/Toneden free download flows.

**Architecture:** Phase 1 (SoundCloud API playlist extraction) is unchanged. Phase 2 is rewritten:
stealth Playwright navigates to each SoundCloud track, clicks the free download button, detects
which gate service opened in the new tab, and executes that service's YAML-defined steps
presence-first (each step checks for its element before acting, so form ordering variations are
handled automatically).

**Tech Stack:** Python 3.12, `playwright` (async), `playwright-stealth`, `pyyaml`, `pytest`,
`pytest-asyncio`, `unittest.mock`

---

## File Map

### New files

| File | Responsibility |
|---|---|
| `soundcloud_dl/soundcloud_dl/gate_handlers/__init__.py` | Registry: URL pattern → handler class |
| `soundcloud_dl/soundcloud_dl/gate_handlers/base.py` | `GateHandler` ABC + YAML step interpreter |
| `soundcloud_dl/soundcloud_dl/gate_handlers/hypeddit.py` | Thin Hypeddit subclass |
| `soundcloud_dl/soundcloud_dl/gate_handlers/hypeddit.yaml` | Hypeddit step definitions |
| `soundcloud_dl/soundcloud_dl/gate_handlers/toneden.py` | Thin Toneden subclass |
| `soundcloud_dl/soundcloud_dl/gate_handlers/toneden.yaml` | Toneden step definitions |
| `soundcloud_dl/soundcloud_dl/playwright_browser.py` | Stealth browser/context setup |
| `soundcloud_dl/soundcloud_dl/soundcloud_page.py` | SoundCloud track page interactions |
| `soundcloud_dl/soundcloud_dl/recorder.py` | `--record` mode: codegen wrapper + YAML scaffold |
| `soundcloud_dl/tests/__init__.py` | Test package marker |
| `soundcloud_dl/tests/test_gate_base.py` | Unit tests for step interpreter |
| `soundcloud_dl/tests/test_gate_registry.py` | Unit tests for handler registry |
| `soundcloud_dl/tests/test_config.py` | Unit tests for new config values |

### Modified files

| File | Change |
|---|---|
| `soundcloud_dl/pyproject.toml` | Remove `browser-use`, add `playwright`, `playwright-stealth`, `pyyaml`, `pytest`, `pytest-asyncio` |
| `soundcloud_dl/soundcloud_dl/config.py` | Strip LLM vars; add human-behavior timing vars |
| `soundcloud_dl/soundcloud_dl/main.py` | New Phase 2 orchestration; add `--record` flag; remove LLM flags |
| `soundcloud_dl/README.md` | Update setup + usage instructions |

### Deleted files

| File | Reason |
|---|---|
| `soundcloud_dl/soundcloud_dl/agent_task.py` | Replaced by `playwright_browser.py` + gate handlers |

---

## Task 1: Update Dependencies

**Files:**
- Modify: `soundcloud_dl/pyproject.toml`

- [ ] **Step 1: Update pyproject.toml**

Replace the `dependencies` block and add `pytest`/`pytest-asyncio` to dev deps:

```toml
[project]
name = "soundcloud-dl"
version = "0.2.0"
description = "SoundCloud free-download automation (API + stealth Playwright)"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.40.0",
    "playwright-stealth>=1.0.6",
    "pyyaml>=6.0",
    "httpx>=0.28.0",
    "python-dotenv>=1.2.1",
]

[project.scripts]
soundcloud-dl = "soundcloud_dl.main:main"

[dependency-groups]
dev = [
    "ruff>=0.15.5",
    "ty>=0.0.21",
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["ALL"]
ignore = ["D", "COM812", "ISC001"]

[tool.ty.environment]
python-version = "3.12"
```

- [ ] **Step 2: Sync the lockfile and install Playwright browsers**

```bash
cd soundcloud_dl
uv sync
uv run playwright install chromium
```

Expected: no errors, `.venv` updated.

- [ ] **Step 3: Commit**

```bash
git add soundcloud_dl/pyproject.toml soundcloud_dl/uv.lock
git commit -m "build(soundcloud-dl): replace browser-use with playwright + stealth + pyyaml"
```

---

## Task 2: Clean Up config.py

Remove all LLM-specific variables. Add human-behavior timing variables for the new stealth
Playwright layer.

**Files:**
- Modify: `soundcloud_dl/soundcloud_dl/config.py`
- Create: `soundcloud_dl/tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `soundcloud_dl/tests/__init__.py` (empty), then write
`soundcloud_dl/tests/test_config.py`:

```python
"""Tests for config.py values and helpers."""

import os
import importlib


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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd soundcloud_dl
uv run pytest tests/test_config.py -v
```

Expected: `AttributeError` or `ImportError` (ACTION_DELAY_MIN_MS not defined yet).

- [ ] **Step 3: Rewrite config.py**

Replace the full contents of `soundcloud_dl/soundcloud_dl/config.py`:

```python
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

# Persistent browser profile. Unset = default path. Set to "0" to disable.
BROWSER_PROFILE_ENV = os.getenv("TUNEWRANGLER_SC_BROWSER_PROFILE", "").strip()

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
    """Return project logs directory (created if needed)."""
    log_dir = _PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_processed_file() -> Path:
    """Path to JSON file storing processed track URLs per playlist (for resume)."""
    return get_log_dir() / "soundcloud_dl_processed.json"


def get_playlist_cache_file() -> Path:
    """Path to JSON file storing cached playlist track lists (by playlist URL)."""
    return get_log_dir() / "soundcloud_dl_playlist_cache.json"


def get_browser_profile_dir() -> Path | None:
    """Return persistent browser profile directory, or None if disabled."""
    if BROWSER_PROFILE_ENV.lower() in ("0", "false", "no"):
        return None
    if BROWSER_PROFILE_ENV:
        return Path(BROWSER_PROFILE_ENV).expanduser().resolve()
    return (_PROJECT_ROOT / "soundcloud_browser_profile").resolve()


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
```

- [ ] **Step 4: Run tests and verify passing**

```bash
cd soundcloud_dl
uv run pytest tests/test_config.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/config.py soundcloud_dl/tests/
git commit -m "ref(soundcloud-dl): strip LLM config, add human-behavior timing vars"
```

---

## Task 3: YAML Step Interpreter (base.py)

This is the core engine. `GateHandler` loads its YAML config, resolves template vars, and walks
steps presence-first with `depends_on` support.

**Files:**
- Create: `soundcloud_dl/soundcloud_dl/gate_handlers/__init__.py` (empty for now)
- Create: `soundcloud_dl/soundcloud_dl/gate_handlers/base.py`
- Create: `soundcloud_dl/tests/test_gate_base.py`

- [ ] **Step 1: Write failing tests**

Create `soundcloud_dl/soundcloud_dl/gate_handlers/__init__.py` (empty file).

Write `soundcloud_dl/tests/test_gate_base.py`:

```python
"""Unit tests for GateHandler YAML step interpreter (base.py)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from soundcloud_dl.gate_handlers.base import GateHandler, GateStepError, StepResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

SIMPLE_CONFIG = """
gate: test
url_pattern: "test.example.com"
steps:
  - id: required_click
    trigger: "#submit"
    action: click
    required: true
  - id: optional_fill
    trigger: "input[name='email']"
    action: fill
    value: "{{email}}"
    optional: true
  - id: depends_step
    trigger: "textarea"
    action: fill
    value: "hello"
    depends_on: optional_fill
  - id: final
    trigger: "button:has-text('Download')"
    action: click
    required: true
"""


def make_handler(yaml_str: str, template_vars: dict | None = None) -> GateHandler:
    config = yaml.safe_load(yaml_str)
    return GateHandler(config=config, template_vars=template_vars or {"email": "test@test.com"})


def make_page(found_selectors: set[str]) -> MagicMock:
    """Return a mock Playwright page that finds elements in found_selectors."""
    page = MagicMock()

    async def query_selector(sel):
        # Return a mock element if selector matches, else None
        for s in found_selectors:
            if s in sel or sel in s:
                el = MagicMock()
                el.scroll_into_view_if_needed = AsyncMock()
                el.click = AsyncMock()
                el.fill = AsyncMock()
                return el
        return None

    page.query_selector = query_selector
    page.wait_for_timeout = AsyncMock()
    return page


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_required_step_passes_when_found():
    handler = make_handler(SIMPLE_CONFIG)
    page = make_page({"#submit", "button:has-text('Download')"})
    results = await handler.run(page)
    assert results["required_click"] == StepResult.EXECUTED
    assert results["final"] == StepResult.EXECUTED


@pytest.mark.asyncio
async def test_required_step_raises_when_missing():
    handler = make_handler(SIMPLE_CONFIG)
    page = make_page(set())  # nothing found
    with pytest.raises(GateStepError, match="required_click"):
        await handler.run(page)


@pytest.mark.asyncio
async def test_optional_step_skipped_when_missing():
    handler = make_handler(SIMPLE_CONFIG)
    page = make_page({"#submit", "button:has-text('Download')"})
    results = await handler.run(page)
    assert results["optional_fill"] == StepResult.SKIPPED


@pytest.mark.asyncio
async def test_depends_on_skipped_when_parent_skipped():
    handler = make_handler(SIMPLE_CONFIG)
    # optional_fill not found → depends_step should also be skipped
    page = make_page({"#submit", "button:has-text('Download')"})
    results = await handler.run(page)
    assert results["depends_step"] == StepResult.SKIPPED


@pytest.mark.asyncio
async def test_depends_on_runs_when_parent_ran():
    handler = make_handler(SIMPLE_CONFIG)
    # optional_fill found → depends_step should run
    page = make_page({"#submit", "input[name='email']", "textarea",
                      "button:has-text('Download')"})
    results = await handler.run(page)
    assert results["optional_fill"] == StepResult.EXECUTED
    assert results["depends_step"] == StepResult.EXECUTED


def test_template_var_substitution():
    handler = make_handler(SIMPLE_CONFIG, template_vars={"email": "me@example.com"})
    step = next(s for s in handler.steps if s["id"] == "optional_fill")
    assert handler.resolve_value(step.get("value", "")) == "me@example.com"


def test_missing_template_var_raises():
    handler = make_handler(SIMPLE_CONFIG, template_vars={})
    step = next(s for s in handler.steps if s["id"] == "optional_fill")
    with pytest.raises(KeyError):
        handler.resolve_value("{{email}}")
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd soundcloud_dl
uv run pytest tests/test_gate_base.py -v
```

Expected: `ImportError` — `gate_handlers.base` doesn't exist yet.

- [ ] **Step 3: Implement base.py**

Create `soundcloud_dl/soundcloud_dl/gate_handlers/base.py`:

```python
"""Base GateHandler: loads YAML step config and interprets steps presence-first."""

from __future__ import annotations

import logging
import random
import re
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.gate_handlers.base")


class StepResult(str, Enum):
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

    def __init__(
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
                raise KeyError(f"Template var '{{{{key}}}}' not in template_vars")
            return self.template_vars[key]
        return re.sub(r"\{\{(\w+)\}\}", replace, value)

    async def _random_delay(self, page: Page) -> None:
        ms = random.randint(self.action_delay_min_ms, self.action_delay_max_ms)  # noqa: S311
        await page.wait_for_timeout(ms)

    async def _find_element(self, page: Page, trigger: str) -> object | None:
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
                logger.debug("[%s] Skipping '%s' (depends_on '%s' was skipped)",
                             self.gate_name, step_id, depends_on)
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
                logger.debug("[%s] Skipping optional step '%s' (element not found)",
                             self.gate_name, step_id)
                results[step_id] = StepResult.SKIPPED
                continue

            logger.info("[%s] Executing step '%s' (%s)", self.gate_name, step_id, step["action"])
            await self._execute_step(page, step)
            results[step_id] = StepResult.EXECUTED

        return results
```

- [ ] **Step 4: Run tests and verify passing**

```bash
cd soundcloud_dl
uv run pytest tests/test_gate_base.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/gate_handlers/ soundcloud_dl/tests/test_gate_base.py
git commit -m "feat(soundcloud-dl): add YAML step interpreter (GateHandler base)"
```

---

## Task 4: Gate Handler Registry

The registry maps URL patterns to handler classes. Given a gate URL like
`https://hypeddit.com/artist/trackname`, it returns the right handler.

**Files:**
- Modify: `soundcloud_dl/soundcloud_dl/gate_handlers/__init__.py`
- Create: `soundcloud_dl/tests/test_gate_registry.py`

- [ ] **Step 1: Write failing tests**

Write `soundcloud_dl/tests/test_gate_registry.py`:

```python
"""Unit tests for the gate handler registry."""

import pytest
from soundcloud_dl.gate_handlers import get_handler_for_url, GateNotSupportedError


def test_hypeddit_url_returns_handler():
    handler_class = get_handler_for_url("https://hypeddit.com/l8nite/sometrack")
    assert handler_class is not None
    assert handler_class.__name__ == "HypedditHandler"


def test_toneden_url_returns_handler():
    handler_class = get_handler_for_url("https://toneden.io/artist/sometrack")
    assert handler_class is not None
    assert handler_class.__name__ == "TonedenHandler"


def test_unknown_url_raises():
    with pytest.raises(GateNotSupportedError, match="unknown-gate.com"):
        get_handler_for_url("https://unknown-gate.com/track")


def test_url_matching_is_case_insensitive():
    handler_class = get_handler_for_url("https://HYPEDDIT.COM/artist/track")
    assert handler_class.__name__ == "HypedditHandler"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd soundcloud_dl
uv run pytest tests/test_gate_registry.py -v
```

Expected: `ImportError` — registry not implemented yet.

- [ ] **Step 3: Implement registry in `__init__.py`**

Write `soundcloud_dl/soundcloud_dl/gate_handlers/__init__.py`:

```python
"""Gate handler registry: maps gate service URLs to handler classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soundcloud_dl.gate_handlers.base import GateHandler


class GateNotSupportedError(ValueError):
    """Raised when no handler is registered for a given URL."""


def get_handler_for_url(url: str) -> type[GateHandler]:
    """
    Return the GateHandler subclass for the given gate URL.

    Imports are deferred so that adding a new handler only requires registering
    its URL pattern here — no changes to any other file.

    Raises GateNotSupportedError if no handler matches.
    """
    lower = url.lower()

    if "hypeddit.com" in lower:
        from soundcloud_dl.gate_handlers.hypeddit import HypedditHandler
        return HypedditHandler

    if "toneden.io" in lower:
        from soundcloud_dl.gate_handlers.toneden import TonedenHandler
        return TonedenHandler

    from urllib.parse import urlparse
    domain = urlparse(url).netloc or url
    msg = f"No gate handler registered for: {domain}"
    raise GateNotSupportedError(msg)
```

Note: `HypedditHandler` and `TonedenHandler` are stub-imported here — create stub files to
unblock tests before adding the YAML configs in the next task.

Create stub `soundcloud_dl/soundcloud_dl/gate_handlers/hypeddit.py`:

```python
"""Hypeddit gate handler."""

from pathlib import Path
from soundcloud_dl.gate_handlers.base import GateHandler


class HypedditHandler(GateHandler):
    config_path = Path(__file__).parent / "hypeddit.yaml"
```

Create stub `soundcloud_dl/soundcloud_dl/gate_handlers/toneden.py`:

```python
"""Toneden gate handler."""

from pathlib import Path
from soundcloud_dl.gate_handlers.base import GateHandler


class TonedenHandler(GateHandler):
    config_path = Path(__file__).parent / "toneden.yaml"
```

Create placeholder YAML files (real selectors come in Task 5):

`soundcloud_dl/soundcloud_dl/gate_handlers/hypeddit.yaml`:

```yaml
gate: hypeddit
url_pattern: "hypeddit.com"
steps: []
```

`soundcloud_dl/soundcloud_dl/gate_handlers/toneden.yaml`:

```yaml
gate: toneden
url_pattern: "toneden.io"
steps: []
```

- [ ] **Step 4: Run tests and verify passing**

```bash
cd soundcloud_dl
uv run pytest tests/test_gate_registry.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/gate_handlers/ soundcloud_dl/tests/test_gate_registry.py
git commit -m "feat(soundcloud-dl): add gate handler registry and stub handlers"
```

---

## Task 5: Hypeddit Gate Config (Real Selectors)

Fill in `hypeddit.yaml` with real selectors from Hypeddit's DOM. The element shared in the
design doc (`#gateDownloadButton`) gives us a solid starting point.

**Files:**
- Modify: `soundcloud_dl/soundcloud_dl/gate_handlers/hypeddit.yaml`

- [ ] **Step 1: Write the Hypeddit YAML config**

```yaml
gate: hypeddit
url_pattern: "hypeddit.com"

steps:
  # Click the main gated download button to open the form/flow
  - id: click_gate_button
    trigger: "#gateDownloadButton, .hype-btn-green, a[data-type='gate']"
    action: click
    required: true

  # Email field (present on most Hypeddit gates)
  - id: fill_email
    trigger: "input[type='email'], input[placeholder*='email' i], input[name*='email' i]"
    action: fill
    value: "{{email}}"
    optional: true

  # Name field (present on some gates)
  - id: fill_name
    trigger: >-
      input[name='name'], input[placeholder*='name' i],
      input[placeholder*='first name' i], input[name='firstName']
    action: fill
    value: "{{name}}"
    optional: true

  # "Share a comment" gate — click to reveal textarea
  - id: share_comment_gate
    trigger: >-
      button:has-text('Share a comment'), button:has-text('Leave a comment'),
      .comment-gate-btn
    action: click
    optional: true

  # Comment textarea — only shown after comment gate is opened
  - id: fill_comment
    trigger: "textarea[placeholder*='comment' i], textarea.hype-textarea, textarea"
    action: fill
    value: "{{comment}}"
    optional: true
    depends_on: share_comment_gate

  # Submit the comment (separate button on some gates)
  - id: submit_comment
    trigger: >-
      button:has-text('Share a comment'), button:has-text('Submit comment'),
      button:has-text('Post comment')
    action: click
    optional: true
    depends_on: fill_comment

  # Repost on SoundCloud gate
  - id: repost_soundcloud
    trigger: >-
      button:has-text('Repost'), a:has-text('Repost on SoundCloud'),
      .repost-gate-btn
    action: click
    optional: true

  # Follow on SoundCloud gate
  - id: follow_soundcloud
    trigger: >-
      button:has-text('Follow'), a:has-text('Follow on SoundCloud'),
      .follow-gate-btn
    action: click
    optional: true

  # Final download button (after all gates are satisfied)
  - id: final_download
    trigger: >-
      a#gateDownloadButton:not([data-type='gate']),
      button:has-text('Download'), a:has-text('Download Now'),
      a:has-text('Get Download'), .download-link
    action: click
    required: true
```

- [ ] **Step 2: Verify YAML is valid**

```bash
cd soundcloud_dl
uv run python -c "
import yaml
from pathlib import Path
config = yaml.safe_load(Path('soundcloud_dl/gate_handlers/hypeddit.yaml').read_text())
print(f'Gate: {config[\"gate\"]}, Steps: {len(config[\"steps\"])}')
for s in config['steps']:
    print(f'  {s[\"id\"]} ({s[\"action\"]})')
"
```

Expected: prints all 9 steps with no errors.

- [ ] **Step 3: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/gate_handlers/hypeddit.yaml
git commit -m "feat(soundcloud-dl): add Hypeddit gate step config"
```

---

## Task 6: Toneden Gate Config (Real Selectors)

Toneden has a different form layout. These selectors are best-effort — use `--record toneden`
(Task 9) to refine after implementation.

**Files:**
- Modify: `soundcloud_dl/soundcloud_dl/gate_handlers/toneden.yaml`

- [ ] **Step 1: Write the Toneden YAML config**

```yaml
gate: toneden
url_pattern: "toneden.io"

steps:
  # Initial "Get Download" / unlock button
  - id: click_unlock
    trigger: >-
      button:has-text('Get Download'), button:has-text('Unlock'),
      button:has-text('Free Download'), .unlock-btn
    action: click
    required: true

  # Email input
  - id: fill_email
    trigger: "input[type='email'], input[placeholder*='email' i]"
    action: fill
    value: "{{email}}"
    optional: true

  # Name input
  - id: fill_name
    trigger: "input[placeholder*='name' i], input[name='name']"
    action: fill
    value: "{{name}}"
    optional: true

  # Submit the email form (if separate from unlock button)
  - id: submit_email_form
    trigger: "button[type='submit'], button:has-text('Submit'), button:has-text('Continue')"
    action: click
    optional: true
    depends_on: fill_email

  # Follow on SoundCloud gate
  - id: follow_soundcloud
    trigger: >-
      button:has-text('Follow'), a:has-text('Follow on SoundCloud'),
      .follow-btn
    action: click
    optional: true

  # Repost gate
  - id: repost_soundcloud
    trigger: "button:has-text('Repost'), a:has-text('Repost')"
    action: click
    optional: true

  # Final download link
  - id: final_download
    trigger: >-
      a:has-text('Download'), button:has-text('Download'),
      a:has-text('Click here to download'), .download-link
    action: click
    required: true
```

- [ ] **Step 2: Verify YAML is valid**

```bash
cd soundcloud_dl
uv run python -c "
import yaml
from pathlib import Path
config = yaml.safe_load(Path('soundcloud_dl/gate_handlers/toneden.yaml').read_text())
print(f'Gate: {config[\"gate\"]}, Steps: {len(config[\"steps\"])}')
"
```

- [ ] **Step 3: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/gate_handlers/toneden.yaml
git commit -m "feat(soundcloud-dl): add Toneden gate step config"
```

---

## Task 7: Stealth Browser Setup (playwright_browser.py)

This replaces `agent_task.py`. Provides an async context manager that yields a stealth
Playwright browser context using the persistent profile.

**Files:**
- Create: `soundcloud_dl/soundcloud_dl/playwright_browser.py`
- Delete: `soundcloud_dl/soundcloud_dl/agent_task.py`

- [ ] **Step 1: Create playwright_browser.py**

```python
"""Stealth Playwright browser context for SoundCloud gate automation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import stealth_async

from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    DOWNLOAD_DIR,
    HEADED,
    SCROLL_BEFORE_CLICK,
    TYPE_DELAY_MS,
    get_browser_profile_dir,
)

logger = logging.getLogger("soundcloud_dl.playwright_browser")


@contextlib.asynccontextmanager
async def stealth_browser() -> AsyncIterator[BrowserContext]:
    """
    Async context manager yielding a stealth Playwright BrowserContext.

    Uses a persistent profile (so SoundCloud login is preserved between runs).
    Applies playwright-stealth to suppress automation fingerprints.

    Usage::

        async with stealth_browser() as context:
            page = await context.new_page()
            await page.goto("https://soundcloud.com/...")
    """
    profile_dir = get_browser_profile_dir()
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
    ]

    async with async_playwright() as pw:
        if profile_dir is not None:
            profile_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Using persistent browser profile: %s", profile_dir)
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=not HEADED,
                args=launch_args,
                accept_downloads=True,
                downloads_path=str(DOWNLOAD_DIR) if DOWNLOAD_DIR else None,
            )
        else:
            logger.info("Using ephemeral browser (no persistent profile)")
            browser = await pw.chromium.launch(headless=not HEADED, args=launch_args)
            context = await browser.new_context(accept_downloads=True)

        # Apply stealth to all new pages automatically
        context.on("page", lambda page: asyncio.ensure_future(_apply_stealth(page)))

        try:
            yield context
        finally:
            await context.close()


async def _apply_stealth(page: Page) -> None:
    """Apply playwright-stealth patches to a page."""
    try:
        await stealth_async(page)
    except Exception:  # noqa: BLE001
        logger.debug("stealth_async failed on page (may be a background page)", exc_info=True)


async def new_stealth_page(context: BrowserContext) -> Page:
    """Open a new page in the context with stealth applied."""
    page = await context.new_page()
    await stealth_async(page)
    return page


async def random_delay(page: Page) -> None:
    """Wait a random human-like duration between actions."""
    ms = random.randint(ACTION_DELAY_MIN_MS, ACTION_DELAY_MAX_MS)  # noqa: S311
    await page.wait_for_timeout(ms)
```

- [ ] **Step 2: Delete agent_task.py**

```bash
cd soundcloud_dl
git rm soundcloud_dl/soundcloud_dl/agent_task.py
```

- [ ] **Step 3: Verify imports work**

```bash
cd soundcloud_dl
uv run python -c "from soundcloud_dl.playwright_browser import stealth_browser; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/playwright_browser.py
git commit -m "feat(soundcloud-dl): add stealth Playwright browser context manager"
```

---

## Task 8: SoundCloud Page Interaction (soundcloud_page.py)

Navigates to a SoundCloud track page and clicks the free download button, handling the new-tab
redirect to the gate service.

**Files:**
- Create: `soundcloud_dl/soundcloud_dl/soundcloud_page.py`

- [ ] **Step 1: Create soundcloud_page.py**

```python
"""Interact with a SoundCloud track page to trigger the free download gate."""

from __future__ import annotations

import logging

from playwright.async_api import BrowserContext, Page

from soundcloud_dl.config import PAGE_LOAD_WAIT_SECONDS
from soundcloud_dl.playwright_browser import new_stealth_page, random_delay

logger = logging.getLogger("soundcloud_dl.soundcloud_page")

# Selectors for the free download button on SoundCloud track pages
FREE_DOWNLOAD_SELECTORS = [
    "a.sc-buylink",                       # primary purchase/download link
    "a[href*='free'][href*='download']",  # href-based heuristic
    "a:has-text('Free Download')",
    "a:has-text('FREE DL')",
    "a:has-text('Free DL')",
]


class SoundCloudPageError(RuntimeError):
    """Raised when we can't find or trigger the free download on a SoundCloud page."""


async def get_gate_url(context: BrowserContext, track_url: str) -> str:
    """
    Navigate to a SoundCloud track, click the free download button, and return
    the URL of the gate page that opens in the new tab.

    Raises SoundCloudPageError if no free download button is found.
    """
    page = await new_stealth_page(context)
    try:
        logger.info("Navigating to track: %s", track_url)
        await page.goto(track_url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for SPA to render
        if PAGE_LOAD_WAIT_SECONDS > 0:
            await page.wait_for_timeout(PAGE_LOAD_WAIT_SECONDS * 1000)

        await random_delay(page)

        # Find the free download element
        el = None
        for selector in FREE_DOWNLOAD_SELECTORS:
            el = await page.query_selector(selector)
            if el:
                logger.info("Found free download element with selector: %s", selector)
                break

        if el is None:
            raise SoundCloudPageError(
                f"No free download button found on: {track_url}"
            )

        # Intercept the new tab that opens on click
        async with context.expect_page() as new_page_info:
            await el.click()

        gate_page = await new_page_info.value
        await gate_page.wait_for_load_state("domcontentloaded", timeout=15_000)
        gate_url = gate_page.url
        logger.info("Gate page opened: %s", gate_url)
        return gate_url

    finally:
        await page.close()
```

- [ ] **Step 2: Verify import**

```bash
cd soundcloud_dl
uv run python -c "from soundcloud_dl.soundcloud_page import get_gate_url; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/soundcloud_page.py
git commit -m "feat(soundcloud-dl): add SoundCloud page interaction to extract gate URL"
```

---

## Task 9: Record Mode (recorder.py)

`--record <gate-name> <url>` runs `playwright codegen`, captures selectors interactively, and
scaffolds a starter YAML for a new gate handler.

**Files:**
- Create: `soundcloud_dl/soundcloud_dl/recorder.py`

- [ ] **Step 1: Create recorder.py**

```python
"""Record mode: run playwright codegen and scaffold a gate handler YAML."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger("soundcloud_dl.recorder")

_HANDLERS_DIR = Path(__file__).parent / "gate_handlers"

# Patterns to extract from codegen output
_CLICK_PATTERN = re.compile(
    r'page\.(?:get_by_\w+\("([^"]+)"\)|locator\("([^"]+)"\)|click\("([^"]+)"\))'
)
_FILL_PATTERN = re.compile(
    r'page\.(?:get_by_\w+\("([^"]+)"\)|locator\("([^"]+)"\))\.fill\("([^"]*)"\)'
)


def _parse_codegen_output(code: str) -> list[dict]:
    """Best-effort parse of playwright codegen Python output into step dicts."""
    steps = []

    for line in code.splitlines():
        line = line.strip()

        fill_match = _FILL_PATTERN.search(line)
        if fill_match:
            selector = next(g for g in fill_match.groups()[:-1] if g)
            value = fill_match.group(3)
            steps.append({
                "id": f"fill_{len(steps)}",
                "trigger": selector,
                "action": "fill",
                "value": value or "{{replace_me}}",
                "optional": True,
            })
            continue

        click_match = _CLICK_PATTERN.search(line)
        if click_match:
            selector = next(g for g in click_match.groups() if g)
            steps.append({
                "id": f"click_{len(steps)}",
                "trigger": selector,
                "action": "click",
                "optional": True,
            })

    return steps


def _write_yaml_scaffold(gate_name: str, steps: list[dict]) -> Path:
    """Write a starter YAML file for the gate. Returns the path written."""
    import yaml  # local import so recorder is importable without pyyaml installed

    out_path = _HANDLERS_DIR / f"{gate_name}.yaml"
    config = {
        "gate": gate_name,
        "url_pattern": f"{gate_name}.com",
        "steps": steps,
    }
    out_path.write_text(yaml.dump(config, sort_keys=False, allow_unicode=True))
    return out_path


def record(gate_name: str, url: str) -> None:
    """
    Launch playwright codegen for url, parse the output, and write a starter YAML
    to gate_handlers/<gate_name>.yaml.

    The generated YAML is a scaffold — review and annotate required/optional/depends_on
    and replace placeholder values with {{template_vars}} before using.
    """
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
        output_path = Path(tmp.name)

    logger.info("Starting playwright codegen for: %s", url)
    logger.info("Walk through the gate flow in the browser, then close it.")
    logger.info("Output will be written to: %s", output_path)

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "playwright", "codegen", "--output", str(output_path), url],
        check=False,
    )

    if result.returncode != 0:
        logger.warning("playwright codegen exited with code %d", result.returncode)

    code = output_path.read_text() if output_path.exists() else ""
    output_path.unlink(missing_ok=True)

    steps = _parse_codegen_output(code)

    if not steps:
        logger.warning("No steps parsed from codegen output. Writing empty scaffold.")

    yaml_path = _write_yaml_scaffold(gate_name, steps)
    logger.info("Scaffold written to: %s", yaml_path)
    logger.info(
        "Next: annotate required/optional, add depends_on, replace values with {{template_vars}}."
    )
    logger.info(
        "Then register the handler in gate_handlers/__init__.py if it's a new service."
    )
```

- [ ] **Step 2: Verify import**

```bash
cd soundcloud_dl
uv run python -c "from soundcloud_dl.recorder import record; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/recorder.py
git commit -m "feat(soundcloud-dl): add record mode for bootstrapping new gate handler YAMLs"
```

---

## Task 10: Rewrite main.py

Wire everything together. Remove all LLM flags. Add `--record`. Implement the new Phase 2
orchestration: for each track, get the gate URL, look up the handler, run steps.

**Files:**
- Modify: `soundcloud_dl/soundcloud_dl/main.py`

- [ ] **Step 1: Rewrite main.py**

```python
"""Phase 1: API track list. Phase 2: stealth Playwright gate automation per track."""

from __future__ import annotations

import argparse
import asyncio
import logging

from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    DELAY_SECONDS,
    DOWNLOAD_COMMENT,
    DOWNLOAD_EMAIL,
    DOWNLOAD_NAME,
    PLAYLIST_CACHE_ENABLED,
    RESUME_ENABLED,
    SCROLL_BEFORE_CLICK,
    TUNEWRANGLER_SC_PLAYLIST_URL,
    TYPE_DELAY_MS,
    validate_phase1_config,
    validate_phase2_config,
)
from soundcloud_dl.gate_handlers import GateNotSupportedError, get_handler_for_url
from soundcloud_dl.gate_handlers.base import GateStepError
from soundcloud_dl.logger import setup_logging
from soundcloud_dl.playlist import TrackItem, extract_track_urls
from soundcloud_dl.playlist_cache import load_cached_tracks, save_cached_tracks
from soundcloud_dl.playwright_browser import new_stealth_page, stealth_browser
from soundcloud_dl.recorder import record
from soundcloud_dl.resume import load_processed_urls, record_processed
from soundcloud_dl.soundcloud_page import SoundCloudPageError, get_gate_url

logger = logging.getLogger("soundcloud_dl.main")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="SoundCloud free-download automation (Phase 1: API, Phase 2: Playwright)."
    )
    p.add_argument(
        "--record",
        nargs=2,
        metavar=("GATE_NAME", "URL"),
        help="Record a new gate handler: open codegen for URL, scaffold GATE_NAME.yaml",
    )
    return p.parse_args()


def _load_tracks(playlist_url: str) -> list[TrackItem]:
    tracks = None
    if PLAYLIST_CACHE_ENABLED:
        tracks = load_cached_tracks(playlist_url)
        if tracks is not None:
            logger.info("Phase 1: using cached track list (%d tracks)", len(tracks))
    if tracks is None:
        tracks = extract_track_urls(playlist_url)
        if PLAYLIST_CACHE_ENABLED:
            save_cached_tracks(playlist_url, tracks)
    return tracks


def _get_tracks_to_process(tracks: list[TrackItem], playlist_url: str) -> list[TrackItem]:
    if not RESUME_ENABLED:
        return tracks
    processed = load_processed_urls(playlist_url)
    to_process = [t for t in tracks if t.url not in processed]
    skipped = len(tracks) - len(to_process)
    if skipped:
        logger.info("Resume: skipping %d already-processed tracks.", skipped)
    return to_process


async def _run_phase2(playlist_url: str, to_process: list[TrackItem]) -> None:
    """Run stealth Playwright gate automation for each track."""
    validate_phase2_config()

    template_vars = {
        "email": DOWNLOAD_EMAIL,
        "name": DOWNLOAD_NAME,
        "comment": DOWNLOAD_COMMENT,
    }

    succeeded = 0
    failed = 0

    async with stealth_browser() as context:
        for idx, track in enumerate(to_process, 1):
            logger.info("Phase 2 track %d/%d: %s", idx, len(to_process), track.url)
            success = False
            reason = "UNKNOWN"

            try:
                gate_url = await get_gate_url(context, track.url)
                handler_class = get_handler_for_url(gate_url)
                handler = handler_class(
                    template_vars=template_vars,
                    action_delay_min_ms=ACTION_DELAY_MIN_MS,
                    action_delay_max_ms=ACTION_DELAY_MAX_MS,
                    type_delay_ms=TYPE_DELAY_MS,
                    scroll_before_click=SCROLL_BEFORE_CLICK,
                )
                # Open the gate page in a new stealth page
                gate_page = await new_stealth_page(context)
                await gate_page.goto(gate_url, wait_until="domcontentloaded", timeout=30_000)
                await handler.run(gate_page)
                await gate_page.close()
                success = True
                reason = "DOWNLOAD_SUCCESS"
                succeeded += 1
                logger.info("DOWNLOAD_SUCCESS | %s", track.title or track.url)

            except SoundCloudPageError as e:
                reason = f"NO_FREE_DOWNLOAD: {e}"
                logger.warning("No free download for %s: %s", track.title or track.url, e)
                failed += 1
            except GateNotSupportedError as e:
                reason = f"UNSUPPORTED_GATE: {e}"
                logger.warning("Unsupported gate for %s: %s", track.title or track.url, e)
                failed += 1
            except GateStepError as e:
                reason = f"GATE_STEP_FAILED: {e}"
                logger.error("Gate step failed for %s: %s", track.title or track.url, e)
                failed += 1
            except Exception as e:  # noqa: BLE001
                reason = f"ERROR: {e}"
                logger.exception("Unexpected error for %s", track.title or track.url)
                failed += 1

            if RESUME_ENABLED:
                record_processed(playlist_url, track.url)

            if idx < len(to_process) and DELAY_SECONDS > 0:
                await asyncio.sleep(DELAY_SECONDS)

    logger.info("Completed: %d succeeded, %d failed.", succeeded, failed)


async def main_async() -> None:
    setup_logging()
    validate_phase1_config()
    playlist_url = (TUNEWRANGLER_SC_PLAYLIST_URL or "").strip()

    logger.info("Phase 1: extracting track URLs from: %s", playlist_url)
    tracks = _load_tracks(playlist_url)
    logger.info("Found %d tracks.", len(tracks))

    to_process = _get_tracks_to_process(tracks, playlist_url)
    if not to_process:
        logger.info("No tracks to process.")
        return

    await _run_phase2(playlist_url, to_process)


def main() -> None:
    setup_logging()
    args = _parse_args()

    if args.record:
        gate_name, url = args.record
        record(gate_name, url)
        return

    asyncio.run(main_async())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify full import chain**

```bash
cd soundcloud_dl
uv run python -c "from soundcloud_dl.main import main; print('OK')"
```

Expected: `OK` (no import errors).

- [ ] **Step 3: Run full test suite**

```bash
cd soundcloud_dl
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Run linter**

```bash
cd soundcloud_dl
uv run ruff check soundcloud_dl && uv run ruff format --check soundcloud_dl
```

Fix any issues, then:

- [ ] **Step 5: Commit**

```bash
git add soundcloud_dl/soundcloud_dl/main.py
git commit -m "feat(soundcloud-dl): rewrite Phase 2 with stealth Playwright gate automation"
```

---

## Task 11: Update README

**Files:**
- Modify: `soundcloud_dl/README.md`

- [ ] **Step 1: Update setup and usage sections**

The README needs:

1. Remove all LLM/Ollama/LM Studio setup instructions
2. Add `uvx playwright install chromium` to setup
3. Update "Run" section to show `--record` flag usage
4. Update dev section to show new test command

- [ ] **Step 2: Verify markdownlint**

```bash
cd /Users/tseitz/code/projects/TuneWrangler
npx markdownlint soundcloud_dl/README.md --config .markdownlint.json
```

Fix any issues.

- [ ] **Step 3: Commit**

```bash
git add soundcloud_dl/README.md
git commit -m "docs(soundcloud-dl): update README for stealth Playwright approach"
```

---

## Task 12: End-to-End Smoke Test

Manual verification against a real Hypeddit link from your playlist.

- [ ] **Step 1: Set up .env**

Ensure these are set in the root `.env`:

```env
TUNEWRANGLER_SC_PLAYLIST_URL=https://soundcloud.com/your-username/sets/your-playlist
SOUNDCLOUD_CLIENT_ID=your_client_id
SOUNDCLOUD_CLIENT_SECRET=your_client_secret
TUNEWRANGLER_SC_EMAIL=your@email.com
TUNEWRANGLER_SC_NAME=Tom
TUNEWRANGLER_SC_COMMENT=🔥🔥🔥
TUNEWRANGLER_SC_HEADED=1
```

- [ ] **Step 2: Run against a single known Hypeddit track**

The resume system will skip any previously processed tracks. Clear it first if needed:

```bash
rm -f logs/soundcloud_dl_processed.json
cd soundcloud_dl
uv run python -m soundcloud_dl.main
```

Watch the headed browser — it should navigate to the track, click free download, handle the
Hypeddit form, and trigger the download.

- [ ] **Step 3: Refine selectors if needed**

If a step fails, run record mode to capture real selectors:

```bash
uv run python -m soundcloud_dl.main --record hypeddit https://hypeddit.com/ACTUAL_URL
```

Walk through the form manually. Copy improved selectors from the scaffolded YAML into
`gate_handlers/hypeddit.yaml`. Commit with:

```bash
git add soundcloud_dl/soundcloud_dl/gate_handlers/hypeddit.yaml
git commit -m "fix(soundcloud-dl): refine Hypeddit selectors from live recording"
```

- [ ] **Step 4: Final commit with any fixes**

```bash
git add -p  # stage only selector fixes, not noise
git commit -m "fix(soundcloud-dl): selector refinements after smoke test"
```
