"""What a run does when Chrome disappears underneath it."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from playwright.async_api import Error as PlaywrightError

from soundcloud_dl import main
from soundcloud_dl.playlist import TrackItem


@pytest.mark.parametrize(
    "message",
    [
        "BrowserContext.new_page: Target page, context or browser has been closed",
        "Page.goto: Target closed",
        "Connection closed while reading from the driver",
    ],
)
def test_a_dead_browser_is_recognised(message):
    assert main._is_browser_gone(PlaywrightError(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "Page.goto: Timeout 30000ms exceeded.",
        "Element is not visible",
        "strict mode violation: locator resolved to 2 elements",
    ],
)
def test_an_ordinary_playwright_failure_is_not_mistaken_for_one(message):
    # These must stay per-track failures. Treating one as a dead browser would abandon
    # every remaining track over a single slow page.
    assert main._is_browser_gone(PlaywrightError(message)) is False


@pytest.mark.asyncio
async def test_the_run_stops_and_leaves_the_remaining_tracks_untouched(monkeypatch):
    """The tracks after a crash were never tried, so nothing may be written about them.

    Recording "failed" spends their retry budget on a browser crash rather than on
    anything the gates did.
    """
    tracks = [TrackItem(url=f"https://soundcloud.com/u/t{i}") for i in range(4)]
    tried: list[str] = []
    recorded: list[tuple[str, str]] = []

    async def fake_process(_ctx, track, **_kw):
        tried.append(track.url)
        if track.url.endswith("t1"):
            msg = "Chrome closed"
            raise main.BrowserGoneError(msg)
        return main.TrackOutcome("done")

    monkeypatch.setattr(main, "_process_track", fake_process)
    monkeypatch.setattr(
        main, "record_state", lambda _p, u, s, reason="": recorded.append((u, s))
    )
    monkeypatch.setattr(main, "validate_phase2_config", lambda: None)
    monkeypatch.setattr(main, "_ensure_logged_in", AsyncMock())
    monkeypatch.setattr(main, "DELAY_SECONDS", 0)

    ctx = AsyncMock()
    with patch.object(main, "attached_browser") as attach:
        attach.return_value.__aenter__ = AsyncMock(return_value=ctx)
        attach.return_value.__aexit__ = AsyncMock(return_value=False)
        await main._run_phase2("https://soundcloud.com/u/sets/p", tracks)

    assert tried == [t.url for t in tracks[:2]], "the run kept going after the browser died"
    assert recorded == [(tracks[0].url, "done")], "a track that was never tried got a state"
