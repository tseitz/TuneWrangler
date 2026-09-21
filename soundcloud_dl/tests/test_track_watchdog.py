"""What a run does when one track stops making progress.

A real run sat for 50 minutes on a gate that had already saved its file: the event loop
was idle with nothing left to fire, and every per-step timeout inside the track had
already passed without catching it. These pin the budget that ends that.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from soundcloud_dl import main
from soundcloud_dl.playlist import TrackItem


def _harness(monkeypatch, fake_process, *, timeout: float = 0.05):
    """Wire _run_phase2 up to a fake browser and return the recorder's log."""
    recorded: list[tuple[str, str, str]] = []
    monkeypatch.setattr(main, "_process_track", fake_process)
    monkeypatch.setattr(
        main,
        "record_state",
        lambda _p, u, s, reason="": recorded.append((u, s, reason)),
    )
    monkeypatch.setattr(main, "validate_phase2_config", lambda: None)
    monkeypatch.setattr(main, "_ensure_logged_in", AsyncMock())
    monkeypatch.setattr(main, "DELAY_SECONDS", 0)
    monkeypatch.setattr(main, "TRACK_TIMEOUT_SECONDS", timeout)
    return recorded


async def _run(tracks):
    ctx = AsyncMock()
    with patch.object(main, "attached_browser") as attach:
        attach.return_value.__aenter__ = AsyncMock(return_value=ctx)
        attach.return_value.__aexit__ = AsyncMock(return_value=False)
        await main._run_phase2("https://soundcloud.com/u/sets/p", tracks)


@pytest.mark.asyncio
async def test_a_hung_track_does_not_stall_the_rest_of_the_batch(monkeypatch):
    tracks = [TrackItem(url=f"https://soundcloud.com/u/t{i}") for i in range(3)]
    tried: list[str] = []

    async def fake_process(_ctx, track, **_kw):
        tried.append(track.url)
        if track.url.endswith("t0"):
            await asyncio.sleep(3600)
        return main.TrackOutcome("done")

    recorded = _harness(monkeypatch, fake_process)
    await _run(tracks)

    assert tried == [t.url for t in tracks], "the batch stopped at the track that hung"
    assert [s for _, s, _ in recorded] == ["manual_review", "done", "done"]


@pytest.mark.asyncio
async def test_the_hang_is_recorded_with_a_reason_that_names_it(monkeypatch):
    """The state alone reads like any other stuck gate, and this one is not."""
    tracks = [TrackItem(url="https://soundcloud.com/u/t0")]

    async def fake_process(_ctx, _track, **_kw):
        await asyncio.sleep(3600)
        return main.TrackOutcome("done")

    recorded = _harness(monkeypatch, fake_process)
    await _run(tracks)

    (_url, state, reason) = recorded[0]
    assert state == "manual_review"
    assert "hung" in reason, reason


@pytest.mark.asyncio
async def test_a_budgeted_state_is_used_so_a_permanent_hang_retires(monkeypatch):
    """"failed" retries forever, and a track that always hangs would then cost the full
    timeout on every batch from here on. Only the budgeted states are retired."""
    from soundcloud_dl import resume

    tracks = [TrackItem(url="https://soundcloud.com/u/t0")]

    async def fake_process(_ctx, _track, **_kw):
        await asyncio.sleep(3600)
        return main.TrackOutcome("done")

    recorded = _harness(monkeypatch, fake_process)
    await _run(tracks)

    assert recorded[0][1] in resume._BUDGETED_STATES


@pytest.mark.asyncio
async def test_a_wedged_browser_stops_the_run_instead_of_timing_out_every_track(monkeypatch):
    """Tracks after the browser wedges were never really tried, so nothing is written
    about them — the same rule the dead-browser guard follows."""
    tracks = [TrackItem(url=f"https://soundcloud.com/u/t{i}") for i in range(5)]
    tried: list[str] = []

    async def fake_process(_ctx, track, **_kw):
        tried.append(track.url)
        await asyncio.sleep(3600)
        return main.TrackOutcome("done")

    recorded = _harness(monkeypatch, fake_process)
    await _run(tracks)

    assert len(tried) == main._MAX_CONSECUTIVE_TIMEOUTS, (
        f"kept going after {main._MAX_CONSECUTIVE_TIMEOUTS} hangs in a row: {tried}"
    )
    assert len(recorded) == main._MAX_CONSECUTIVE_TIMEOUTS


@pytest.mark.asyncio
async def test_a_track_that_finishes_clears_the_run_of_hangs(monkeypatch):
    """Two hangs spread across a batch are two bad gates, not a wedged browser."""
    tracks = [TrackItem(url=f"https://soundcloud.com/u/t{i}") for i in range(4)]
    tried: list[str] = []

    async def fake_process(_ctx, track, **_kw):
        tried.append(track.url)
        if track.url.endswith(("t0", "t2")):
            await asyncio.sleep(3600)
        return main.TrackOutcome("done")

    _harness(monkeypatch, fake_process)
    await _run(tracks)

    assert tried == [t.url for t in tracks], "a passing track did not reset the hang count"


@pytest.mark.asyncio
async def test_an_ordinary_slow_track_is_left_alone(monkeypatch):
    """The budget exists to end a hang, never to cut short a gate that is still working."""
    tracks = [TrackItem(url="https://soundcloud.com/u/t0")]

    async def fake_process(_ctx, _track, **_kw):
        await asyncio.sleep(0.01)
        return main.TrackOutcome("done")

    recorded = _harness(monkeypatch, fake_process, timeout=5.0)
    await _run(tracks)

    assert [s for _, s, _ in recorded] == ["done"]
