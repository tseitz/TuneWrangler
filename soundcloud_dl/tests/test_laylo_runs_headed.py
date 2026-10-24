"""A Laylo RSVP from headless Chrome was taken and never delivered, so a batch with one
runs headed."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from soundcloud_dl import main
from soundcloud_dl.playlist import TrackItem


async def _headed_asked(monkeypatch, tracks):
    monkeypatch.setattr(main, "_process_track", AsyncMock(return_value=main.TrackOutcome("done")))
    monkeypatch.setattr(main, "record_state", lambda *_a, **_k: None)
    monkeypatch.setattr(main, "validate_phase2_config", lambda: None)
    monkeypatch.setattr(main, "_ensure_logged_in", AsyncMock())
    monkeypatch.setattr(main, "DELAY_SECONDS", 0)
    with patch.object(main, "attached_browser") as attach:
        attach.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        attach.return_value.__aexit__ = AsyncMock(return_value=False)
        await main._run_phase2("https://soundcloud.com/u/sets/p", tracks)
    return attach.call_args.kwargs["headed"]


@pytest.mark.asyncio
async def test_a_batch_with_a_laylo_gate_runs_headed(monkeypatch):
    tracks = [
        TrackItem(url="https://soundcloud.com/u/t0", purchase_url="https://hypeddit.com/a/b"),
        TrackItem(url="https://soundcloud.com/u/t1", purchase_url="https://laylo.com/x/aB1"),
    ]
    assert await _headed_asked(monkeypatch, tracks) is True


@pytest.mark.asyncio
async def test_a_batch_without_one_leaves_it_to_the_config(monkeypatch):
    tracks = [TrackItem(url="https://soundcloud.com/u/t0", purchase_url="https://hypeddit.com/a/b")]
    assert await _headed_asked(monkeypatch, tracks) is None


@pytest.mark.asyncio
async def test_a_laylo_link_only_in_the_description_runs_headed(monkeypatch):
    tracks = [
        TrackItem(
            url="https://soundcloud.com/u/t0",
            description="all my remixes (free download): laylo.com/x/aB1 \n socials: @x",
        ),
    ]
    assert await _headed_asked(monkeypatch, tracks) is True
