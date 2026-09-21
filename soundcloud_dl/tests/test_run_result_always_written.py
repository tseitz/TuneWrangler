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

    assert outcome.state == expected_state
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

    assert outcome.state == "done"
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


@pytest.mark.asyncio
async def test_the_outcome_carries_a_reason_a_person_can_act_on(runs_dir, monkeypatch):
    async def _run(_self, _page):
        raise StuckGate("gate stuck", last_step_id="jev_cap_25")

    _jev_handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK)

    assert outcome.state == "manual_review"
    assert outcome.reason == "stuck at jev_cap_25"


@pytest.mark.asyncio
async def test_a_reason_is_kept_short_enough_to_read(runs_dir, monkeypatch):
    """It goes in processed.json, which is read by eye; a stack-sized string ruins that."""

    async def _run(_self, _page):
        raise RuntimeError("x" * 5000)

    _jev_handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK)

    assert outcome.state == "failed"
    assert len(outcome.reason) <= main_mod._MAX_REASON_CHARS
    assert outcome.reason.startswith("RuntimeError: ")


@pytest.mark.asyncio
async def test_the_run_writes_the_reason_to_the_resume_file(monkeypatch):
    """Through _run_phase2: a reason the run never passes on is a reason nobody reads."""
    from soundcloud_dl.playlist import TrackItem as _TrackItem

    recorded: list[tuple[str, str, str]] = []

    async def fake_process(_ctx, _track, **_kw):
        return main_mod.TrackOutcome("manual_review", "stuck at jev_cap_25")

    monkeypatch.setattr(main_mod, "_process_track", fake_process)
    monkeypatch.setattr(
        main_mod,
        "record_state",
        lambda _p, u, s, reason="": recorded.append((u, s, reason)),
    )
    monkeypatch.setattr(main_mod, "validate_phase2_config", lambda: None)
    monkeypatch.setattr(main_mod, "_ensure_logged_in", AsyncMock())
    monkeypatch.setattr(main_mod, "DELAY_SECONDS", 0)

    track = _TrackItem(url="https://soundcloud.com/a/b", title="A - B")
    with pytest.MonkeyPatch.context() as mp:
        attach = MagicMock()
        attach.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        attach.return_value.__aexit__ = AsyncMock(return_value=False)
        mp.setattr(main_mod, "attached_browser", attach)
        await main_mod._run_phase2("https://soundcloud.com/u/sets/p", [track])

    assert recorded == [(track.url, "manual_review", "stuck at jev_cap_25")]
