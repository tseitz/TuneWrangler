"""Unit tests for GateHandler YAML step interpreter (base.py)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from soundcloud_dl.gate_handlers.base import (
    CaptchaEncountered,
    CaptchaKind,
    GateHandler,
    GateStepError,
    StepResult,
)


@pytest.fixture(autouse=True)
def _stub_detect_captcha(monkeypatch):
    """Stub detect_captcha to return None by default for gate-handler tests."""

    async def _none(_page):
        return None

    monkeypatch.setattr("soundcloud_dl.gate_handlers.base.detect_captcha", _none)

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
    return GateHandler(config=config, template_vars={"email": "test@test.com"} if template_vars is None else template_vars)


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
                el.type = AsyncMock()
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
    with pytest.raises(KeyError):
        handler.resolve_value("{{email}}")


@pytest.mark.asyncio
async def test_run_raises_captcha_encountered_when_detected(monkeypatch):
    """When detect_captcha returns a kind during run(), CaptchaEncountered is raised."""
    handler = make_handler(SIMPLE_CONFIG)

    page = MagicMock()
    page.query_selector = AsyncMock(return_value=MagicMock())
    page.wait_for_timeout = AsyncMock()

    async def fake_detect(_page):
        return CaptchaKind.HCAPTCHA

    monkeypatch.setattr("soundcloud_dl.gate_handlers.base.detect_captcha", fake_detect)

    with pytest.raises(CaptchaEncountered) as exc:
        await handler.run(page)
    assert exc.value.kind == CaptchaKind.HCAPTCHA
    assert exc.value.gate_name == "test"


@pytest.mark.asyncio
async def test_run_continues_when_no_captcha(monkeypatch):
    """When detect_captcha returns None, run completes normally."""
    handler = make_handler(SIMPLE_CONFIG)

    el = MagicMock()
    el.click = AsyncMock()
    el.fill = AsyncMock()
    el.type = AsyncMock()
    el.scroll_into_view_if_needed = AsyncMock()
    page = MagicMock()
    page.query_selector = AsyncMock(return_value=el)
    page.wait_for_timeout = AsyncMock()

    async def fake_detect(_page):
        return None

    monkeypatch.setattr("soundcloud_dl.gate_handlers.base.detect_captcha", fake_detect)
    results = await handler.run(page)
    assert "required_click" in results
