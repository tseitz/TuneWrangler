"""last_run.json is deleted when a batch starts and written however the batch ends."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from soundcloud_dl import main, resume, run_record
from soundcloud_dl.playlist import TrackItem

PLAYLIST = "https://soundcloud.com/u/sets/p"
TRACKS = [TrackItem(url=f"https://soundcloud.com/u/t{i}", title=f"T{i}") for i in range(4)]


@pytest.fixture(autouse=True)
def batch(tmp_path, monkeypatch):
    monkeypatch.setattr(resume, "get_processed_file", lambda: tmp_path / "processed.json")
    monkeypatch.setattr(main, "validate_phase1_config", lambda: None)
    monkeypatch.setattr(main, "validate_phase2_config", lambda: None)
    monkeypatch.setattr(main, "TUNEWRANGLER_SC_PLAYLIST_URL", PLAYLIST)
    monkeypatch.setattr(main, "RESUME_ENABLED", True)
    monkeypatch.setattr(main, "DELAY_SECONDS", 0)
    monkeypatch.setattr(main, "_load_tracks", lambda _url: list(TRACKS))
    monkeypatch.setattr(main, "_ensure_logged_in", AsyncMock())


def _last_run() -> dict:
    return json.loads(run_record.get_last_run_file().read_text(encoding="utf-8"))


def _browser(*, enter_error: Exception | None = None):
    patcher = patch.object(main, "attached_browser")
    attach = patcher.start()
    attach.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(), side_effect=enter_error)
    attach.return_value.__aexit__ = AsyncMock(return_value=False)
    return patcher


def _outcomes(monkeypatch, outcomes: dict[str, object]) -> list[str]:
    tried: list[str] = []

    async def fake_process(_ctx, track, **_kw):
        tried.append(track.url)
        result = outcomes.get(track.url, main.TrackOutcome("done"))
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(main, "_process_track", fake_process)
    return tried


@pytest.mark.asyncio
async def test_a_normal_run_records_its_counts_and_what_needs_attention(monkeypatch):
    _outcomes(
        monkeypatch,
        {
            TRACKS[1].url: main.TrackOutcome("captcha_pending", "cloudflare"),
            TRACKS[2].url: main.TrackOutcome("unsupported", "no gate"),
            TRACKS[3].url: main.TrackOutcome("failed", "boom"),
        },
    )
    patcher = _browser()
    try:
        await main.main_async()
    finally:
        patcher.stop()

    rec = _last_run()
    assert rec["version"] == 1
    assert rec["finished"] is True
    assert rec["stopped_early"] is False
    assert rec["error"] is None
    assert rec["untried"] == 0
    assert rec["counts"] == {
        "done": 1,
        "unsupported": 1,
        "captcha_pending": 1,
        "login_required": 0,
        "manual_review": 0,
        "failed": 1,
    }
    assert rec["needs_attention"] == [
        {"title": "T1", "url": TRACKS[1].url, "state": "captcha_pending", "reason": "cloudflare"},
        {"title": "T3", "url": TRACKS[3].url, "state": "failed", "reason": "boom"},
    ]
    assert rec["run_started_at"][-6] in "+-"


@pytest.mark.asyncio
async def test_a_stale_record_is_gone_when_the_batch_cannot_start(monkeypatch):
    run_record.get_last_run_file().write_text('{"finished": true}', encoding="utf-8")

    def boom(_url):
        msg = "playlist 404"
        raise RuntimeError(msg)

    monkeypatch.setattr(main, "_load_tracks", boom)
    with pytest.raises(RuntimeError):
        await main.main_async()

    rec = _last_run()
    assert rec["finished"] is False
    assert "playlist 404" in rec["error"]


@pytest.mark.asyncio
async def test_no_tracks_left_is_a_finished_run(monkeypatch):
    for t in TRACKS:
        resume.record_state(PLAYLIST, t.url, "done")
    run_record.get_last_run_file().write_text('{"stale": true}', encoding="utf-8")

    await main.main_async()

    rec = _last_run()
    assert "stale" not in rec
    assert rec["finished"] is True
    assert rec["stopped_early"] is False
    assert rec["untried"] == 0


@pytest.mark.asyncio
async def test_an_empty_playlist_is_a_finished_run(monkeypatch):
    monkeypatch.setattr(main, "_load_tracks", lambda _url: [])
    await main.main_async()
    assert _last_run()["finished"] is True


@pytest.mark.asyncio
async def test_signed_out_records_the_error_and_every_track_untried(monkeypatch):
    tried = _outcomes(monkeypatch, {})
    msg = "Not logged into SoundCloud"
    monkeypatch.setattr(
        main, "_ensure_logged_in", AsyncMock(side_effect=main.SoundCloudLoginRequiredError(msg))
    )
    patcher = _browser()
    try:
        with pytest.raises(main.SoundCloudLoginRequiredError):
            await main.main_async()
    finally:
        patcher.stop()

    rec = _last_run()
    assert tried == []
    assert rec["finished"] is False
    assert rec["stopped_early"] is True
    assert rec["untried"] == 4
    assert "SoundCloudLoginRequiredError" in rec["error"]


@pytest.mark.asyncio
async def test_a_chrome_that_will_not_start_records_the_error():
    patcher = _browser(enter_error=RuntimeError("Chrome did not open port 9222"))
    try:
        with pytest.raises(RuntimeError):
            await main.main_async()
    finally:
        patcher.stop()

    rec = _last_run()
    assert rec["finished"] is False
    assert rec["untried"] == 4
    assert "9222" in rec["error"]


@pytest.mark.asyncio
async def test_a_dead_browser_stops_early_and_counts_the_tracks_left(monkeypatch):
    gone = main.BrowserGoneError("Chrome closed")
    _outcomes(monkeypatch, {TRACKS[1].url: gone})
    patcher = _browser()
    try:
        await main.main_async()
    finally:
        patcher.stop()

    rec = _last_run()
    assert rec["finished"] is True
    assert rec["stopped_early"] is True
    assert rec["untried"] == 3
    assert rec["counts"]["done"] == 1


@pytest.mark.asyncio
async def test_two_hangs_in_a_row_stop_early(monkeypatch):
    monkeypatch.setattr(main, "TRACK_TIMEOUT_SECONDS", 1)
    _outcomes(monkeypatch, {TRACKS[0].url: TimeoutError(), TRACKS[1].url: TimeoutError()})
    patcher = _browser()
    try:
        await main.main_async()
    finally:
        patcher.stop()

    rec = _last_run()
    assert rec["stopped_early"] is True
    assert rec["untried"] == 2
    assert rec["counts"]["manual_review"] == 2
    assert [i["state"] for i in rec["needs_attention"]] == ["manual_review", "manual_review"]


@pytest.mark.asyncio
async def test_a_track_the_resume_logic_gave_up_on_is_listed(monkeypatch):
    for _ in range(3):
        resume.record_state(PLAYLIST, TRACKS[0].url, "manual_review", reason="slide never came")
    tried = _outcomes(monkeypatch, {})
    patcher = _browser()
    try:
        await main.main_async()
    finally:
        patcher.stop()

    rec = _last_run()
    assert TRACKS[0].url not in tried
    assert rec["gave_up"] == [
        {
            "title": "T0",
            "url": TRACKS[0].url,
            "state": "manual_review",
            "reason": "slide never came",
        }
    ]
    assert rec["counts"]["done"] == 3


def test_a_failed_write_leaves_the_old_file_untouched(monkeypatch):
    path = run_record.get_last_run_file()
    path.write_text("old", encoding="utf-8")
    monkeypatch.setattr(run_record, "asdict", lambda _r: {"x": object()})
    run_record.write(run_record.RunRecord())
    assert path.read_text(encoding="utf-8") == "old"
    assert not path.with_name("last_run.json.tmp").exists()


@pytest.mark.asyncio
async def test_a_run_killed_before_it_can_write_leaves_no_old_record(monkeypatch):
    run_record.get_last_run_file().write_text('{"finished": true}', encoding="utf-8")
    monkeypatch.setattr(run_record, "write", lambda _rec: None)
    await main.main_async(limit=0)
    assert not run_record.get_last_run_file().exists()
