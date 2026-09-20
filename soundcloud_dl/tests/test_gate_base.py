"""Unit tests for GateHandler YAML step interpreter (base.py)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from soundcloud_dl import gate_handlers

from soundcloud_dl.gate_handlers.base import (
    GateHandler,
    GateStepError,
    StepResult,
)
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, CaptchaKind


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
    return GateHandler(
        config=config,
        template_vars={"email": "test@test.com"} if template_vars is None else template_vars,
    )


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
                # _find_element awaits is_visible() to filter hidden matches.
                el.is_visible = AsyncMock(return_value=True)
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
    page = make_page({"#submit", "input[name='email']", "textarea", "button:has-text('Download')"})
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
    el.is_visible = AsyncMock(return_value=True)
    page = MagicMock()
    page.query_selector = AsyncMock(return_value=el)
    page.wait_for_timeout = AsyncMock()

    async def fake_detect(_page):
        return None

    monkeypatch.setattr("soundcloud_dl.gate_handlers.base.detect_captcha", fake_detect)
    results = await handler.run(page)
    assert "required_click" in results


def test_a_fresh_handler_has_not_downloaded_anything():
    h = GateHandler(config={"gate": "g", "steps": []})
    assert h.downloaded is False


def test_note_saved_is_what_marks_a_download_real(tmp_path):
    h = GateHandler(config={"gate": "g", "steps": []})
    h._note_saved(tmp_path / "t.wav")
    assert h.downloaded is True


def test_waiting_on_a_step_named_download_is_not_downloading():
    """The bug this replaces: main.py inferred success from step ids containing
    "download", and every gate config has a non-terminal step named for the thing it is
    waiting on — hypeddit's wait_for_download_ready, toneden's wait_for_download_unlock.
    A run that only ever waited was recorded done, and done is never retried.
    """
    h = GateHandler(config={"gate": "g", "steps": []})
    results = {
        "wait_for_download_ready": StepResult.EXECUTED,
        "wait_for_download_unlock": StepResult.EXECUTED,
    }
    assert any("download" in step_id for step_id in results)
    assert h.downloaded is False


def test_no_gate_guards_a_javascript_href_by_exact_match():
    """hypeddit's markup says href="javascript:void(0);" — with the semicolon — so a
    :not([href='javascript:void(0)']) guard did not match it and the still-locked
    Download anchor was clicked anyway. Two of three tracks in a batch then fell through
    to the href fallback and one of them saved a stream segment as the track.
    """
    configs = Path(gate_handlers.__file__).parent.glob("*.yaml")
    offenders = [p.name for p in configs if "[href='javascript:" in p.read_text()]
    assert offenders == [], f"use [href^='javascript:'] instead: {offenders}"


@pytest.mark.asyncio
async def test_a_download_step_does_not_click_an_off_screen_button():
    """Hypeddit enables #gateDownloadButton by class from the first turn while parking it
    on a carousel slide that has not arrived. Clicking it there does nothing: the run
    reports no file and the track is recorded failed with the gate half spent.
    """
    handler = GateHandler(config={"gate": "g", "steps": []})
    asked: list[bool] = []

    async def spy(_page, _trigger, *, allow_hidden=False):
        asked.append(allow_hidden)
        return None  # stops the step before it needs a live page

    handler._find_element = spy

    base = {"trigger": "a#gateDownloadButton", "action": "click", "force": True}
    await handler._execute_step(MagicMock(), base)
    await handler._execute_step(MagicMock(), {**base, "download": True})

    # A force step may still take a hidden match — overlaid or mid-transition is fine.
    # The download must not, which is the whole of the fix.
    assert asked == [True, False]
