"""Keeping a headless run silent.

Chrome's --mute-audio is set at launch and was still not enough: a run carrying the flag
played a gate page's embedded track out loud. These cover the layer added underneath it.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import async_playwright

from soundcloud_dl import playwright_browser


@contextlib.contextmanager
def _attached():
    """Stand in for a real CDP attach, yielding the context the run is handed."""
    context = MagicMock()
    context.pages = []
    context.add_init_script = AsyncMock()
    browser = MagicMock()
    browser.contexts = [context]
    browser.close = AsyncMock()

    pw = MagicMock()
    pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    pw_cm = MagicMock()
    pw_cm.__aenter__ = AsyncMock(return_value=pw)
    pw_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(playwright_browser, "async_playwright", return_value=pw_cm),
        patch.object(playwright_browser, "ensure_chrome_running", return_value=False),
        patch.object(playwright_browser, "shutdown_chrome_on_port"),
    ):
        yield context


@pytest.mark.asyncio
async def test_every_run_installs_the_muter():
    """The script has to reach the context the run actually uses, not just exist."""
    with _attached() as context:
        async with playwright_browser.attached_browser():
            pass
    context.add_init_script.assert_awaited_once()
    assert "addEventListener('play'" in context.add_init_script.await_args.args[0]


@pytest.mark.asyncio
async def test_a_browser_that_refuses_the_muter_still_runs():
    """A silent run is worth less than a working one."""
    with _attached() as context:
        context.add_init_script.side_effect = RuntimeError("nope")
        async with playwright_browser.attached_browser() as ctx:
            assert ctx is context


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_the_script_mutes_a_player_that_starts():
    """The flag cannot be observed from JavaScript; this layer can, so it is checked here.

    A dispatched "play" is the same event a real player fires, and it reaches the document
    capture listener by the same path — without needing a codec the test machine may lack.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            context = await browser.new_context()
            await playwright_browser._silence(context)
            page = await context.new_page()
            await page.goto("about:blank")
            muted = await page.evaluate("""() => {
                const a = document.createElement('audio');
                document.body.appendChild(a);
                a.muted = false;
                a.volume = 1;
                a.dispatchEvent(new Event('play'));
                return a.muted && a.volume === 0;
            }""")
            assert muted, "a player that started was left audible"
        finally:
            await browser.close()


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_the_script_reaches_an_iframe():
    """Gate pages put the track in an embedded player, which is its own frame."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            context = await browser.new_context()
            await playwright_browser._silence(context)
            page = await context.new_page()
            await page.set_content("<iframe srcdoc='<audio id=a></audio>'></iframe>")
            frame = page.frames[1]
            muted = await frame.evaluate("""() => {
                const a = document.getElementById('a');
                a.dispatchEvent(new Event('play'));
                return a.muted;
            }""")
            assert muted, "the player inside the gate's iframe was left audible"
        finally:
            await browser.close()
