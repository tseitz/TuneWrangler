"""Every recorded gate run ends with a result.json, however it ended.

Twenty-one of one day's thirty-seven run directories held screenshots and nothing saying
what happened, because finish() was only reached on the success path — so the runs worth
going back to were exactly the ones with no record.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl import main as main_mod
from soundcloud_dl import run_artifacts
from soundcloud_dl.gate_handlers.base import StuckGate
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, CaptchaKind
from soundcloud_dl.gate_handlers.jev import JevHandler
from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered
from soundcloud_dl.playlist import TrackItem

TRACK = TrackItem(url="https://soundcloud.com/a/b", title="A - B", artist="A")


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    d = tmp_path / "runs"
    d.mkdir()
    monkeypatch.setattr(run_artifacts, "get_runs_dir", lambda: d)
    monkeypatch.setattr(main_mod, "judge_track_filename", AsyncMock(return_value="A - B"))
    monkeypatch.setattr(main_mod, "try_native_sc_download", AsyncMock(return_value=False))
    monkeypatch.setattr(main_mod, "get_gate_url", AsyncMock(return_value="https://gate.io/x"))
    monkeypatch.setattr(main_mod, "is_url_blacklisted", lambda _u: False)
    monkeypatch.setattr(main_mod, "_save_debug_artifacts", AsyncMock())
    monkeypatch.setattr(main_mod, "validate_jev_config", lambda: None)
    monkeypatch.setattr(main_mod, "gate_name_for", lambda _u: "testgate")
    monkeypatch.setattr(main_mod, "DOWNLOAD_DIR", None)
    return d


def _context() -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.url = "https://gate.io/x"
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    return context


def _jev_handler_that(run, monkeypatch) -> None:
    class _Fake(JevHandler):
        gate_slug = "testgate"

        def __init__(self, **_kwargs):
            self.downloaded = False

    _Fake.run = run
    monkeypatch.setattr(main_mod, "get_handler_for_url", lambda _u: _Fake)


def _results(runs_dir):
    return [json.loads(p.read_text()) for p in runs_dir.glob("*/result.json")]


@pytest.mark.parametrize(
    ("raised", "expected_terminal", "expected_state"),
    [
        (StuckGate("gate stuck", last_step_id="s1"), "StuckGate", "manual_review"),
        (CaptchaEncountered(CaptchaKind.HCAPTCHA, "g"), "captcha", "captcha_pending"),
        (LoginWallEncountered("https://gate.io/x", "needs login", "g"), "login_required",
         "login_required"),
        (RuntimeError("something else entirely"), "RuntimeError", "failed"),
    ],
)
@pytest.mark.asyncio
async def test_a_failed_run_still_records_how_it_ended(
    runs_dir, monkeypatch, raised, expected_terminal, expected_state
):
    async def _run(_self, _page):
        raise raised

    _jev_handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK)

    assert outcome == expected_state
    results = _results(runs_dir)
    assert len(results) == 1, "the run directory has screenshots but no result.json"
    assert results[0]["terminal"] == expected_terminal
    assert results[0]["url"] == TRACK.url
    assert results[0]["downloaded"] is False


@pytest.mark.asyncio
async def test_a_successful_run_keeps_its_detailed_record(runs_dir, monkeypatch):
    """The backstop must not overwrite the richer record written on the way through."""

    async def _run(_self, _page):
        _self.downloaded = True
        return {"el_1_download": "EXECUTED"}

    _jev_handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK)

    assert outcome == "done"
    results = _results(runs_dir)
    assert len(results) == 1
    assert results[0]["terminal"] == "downloaded"
    assert results[0]["downloaded"] is True
    assert results[0]["steps"] == {"el_1_download": "EXECUTED"}


def test_finish_keeps_the_first_call(tmp_path, monkeypatch):
    monkeypatch.setattr(run_artifacts, "get_runs_dir", lambda: tmp_path)
    rec = run_artifacts.RunRecorder("g")
    rec.finish(terminal="StuckGate", downloaded=False)
    rec.finish(terminal="backstop", downloaded=False)
    assert json.loads((rec.dir / "result.json").read_text())["terminal"] == "StuckGate"
