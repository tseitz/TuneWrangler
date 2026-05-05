"""Tests for recorder: codegen output parsing + YAML scaffolding."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from soundcloud_dl import recorder
from soundcloud_dl.recorder import _parse_codegen_output, _write_yaml_scaffold

if TYPE_CHECKING:
    from pathlib import Path


# ── _parse_codegen_output ────────────────────────────────────────────────────


def test_parse_codegen_output_empty_input_returns_no_steps() -> None:
    assert _parse_codegen_output("") == []
    assert _parse_codegen_output("\n\n") == []


def test_parse_codegen_output_ignores_garbage_lines() -> None:
    code = "import time\nfrom playwright import sync_playwright\n# a comment"
    assert _parse_codegen_output(code) == []


def test_parse_codegen_output_extracts_get_by_role_single_arg_click() -> None:
    code = 'page.get_by_role("button").click()'
    steps = _parse_codegen_output(code)
    assert steps == [{"id": "click_0", "trigger": "button", "action": "click", "optional": True}]


def test_parse_codegen_output_does_not_capture_get_by_role_with_kwargs() -> None:
    """Regex doesn't match get_by_role with name= kwarg — known recorder limitation."""
    code = 'page.get_by_role("button", name="Submit").click()'
    assert _parse_codegen_output(code) == []


def test_parse_codegen_output_extracts_locator_click() -> None:
    code = 'page.locator("#download").click()'
    steps = _parse_codegen_output(code)
    assert steps == [{"id": "click_0", "trigger": "#download", "action": "click", "optional": True}]


def test_parse_codegen_output_extracts_direct_click_call() -> None:
    code = 'page.click("text=Download")'
    steps = _parse_codegen_output(code)
    assert steps == [
        {"id": "click_0", "trigger": "text=Download", "action": "click", "optional": True}
    ]


def test_parse_codegen_output_extracts_locator_fill_with_value() -> None:
    code = 'page.locator("#email").fill("test@example.com")'
    steps = _parse_codegen_output(code)
    assert steps == [
        {
            "id": "fill_0",
            "trigger": "#email",
            "action": "fill",
            "value": "test@example.com",
            "optional": True,
        }
    ]


def test_parse_codegen_output_replaces_empty_value_with_template_placeholder() -> None:
    code = 'page.locator("#email").fill("")'
    steps = _parse_codegen_output(code)
    assert steps[0]["value"] == "{{replace_me}}"


def test_parse_codegen_output_assigns_sequential_ids_per_action_type() -> None:
    code = (
        'page.locator("#email").fill("a@b.com")\n'
        'page.locator("#name").fill("Tom")\n'
        'page.locator("#submit").click()\n'
        'page.locator("#confirm").click()'
    )
    steps = _parse_codegen_output(code)
    ids = [s["id"] for s in steps]
    # IDs use len(steps) at insertion time, not action-type-specific counters
    assert ids == ["fill_0", "fill_1", "click_2", "click_3"]


def test_parse_codegen_output_preserves_step_order() -> None:
    code = (
        'page.locator("#submit").click()\n'
        'page.locator("#email").fill("x@y")\n'
        'page.locator("#agree").click()'
    )
    actions = [s["action"] for s in _parse_codegen_output(code)]
    assert actions == ["click", "fill", "click"]


# ── _write_yaml_scaffold ─────────────────────────────────────────────────────


@pytest.fixture
def scaffold_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(recorder, "_HANDLERS_DIR", tmp_path)
    return tmp_path


def test_write_yaml_scaffold_writes_file_with_expected_structure(scaffold_dir: Path) -> None:
    steps = [
        {"id": "click_0", "trigger": "#go", "action": "click", "optional": True},
        {"id": "fill_1", "trigger": "#email", "action": "fill", "value": "{{email}}"},
    ]
    out = _write_yaml_scaffold("examplegate", steps)
    assert out == scaffold_dir / "examplegate.yaml"
    assert out.exists()
    parsed = yaml.safe_load(out.read_text())
    assert parsed["gate"] == "examplegate"
    assert parsed["url_pattern"] == "examplegate.com"
    assert parsed["steps"] == steps


def test_write_yaml_scaffold_writes_empty_steps_list(scaffold_dir: Path) -> None:
    out = _write_yaml_scaffold("emptygate", [])
    parsed = yaml.safe_load(out.read_text())
    assert parsed["steps"] == []
