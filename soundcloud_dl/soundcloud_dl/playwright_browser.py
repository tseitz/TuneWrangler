"""Real-Chrome browser context for SoundCloud gate automation (CDP attach)."""

from __future__ import annotations

import contextlib
import logging
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from playwright.async_api import BrowserContext, Page, async_playwright

from soundcloud_dl.chrome_bringup import ensure_chrome_running
from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    CHROME_DEBUG_PORT,
    CHROME_PATH,
    CHROME_PROFILE_DIR,
)

logger = logging.getLogger("soundcloud_dl.playwright_browser")


@contextlib.asynccontextmanager
async def attached_browser() -> AsyncIterator[BrowserContext]:
    """
    Async context manager yielding a BrowserContext attached to a real running Chrome.

    Ensures Chrome is running with --remote-debugging-port + dedicated profile,
    then connects via CDP. The Chrome process is left running on exit.

    Usage::

        async with attached_browser() as context:
            page = await context.new_page()
            await page.goto("https://soundcloud.com/...")
    """
    ensure_chrome_running(
        chrome_path=CHROME_PATH,
        profile_dir=CHROME_PROFILE_DIR,
        port=CHROME_DEBUG_PORT,
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
        # connect_over_cdp returns a Browser whose first context is Chrome's
        # existing default context tied to the user-data-dir profile.
        if not browser.contexts:
            msg = "Connected to Chrome but no browser context found"
            raise RuntimeError(msg)
        context = browser.contexts[0]

        try:
            yield context
        finally:
            # Disconnect, but leave Chrome running for inspection of any
            # captcha tabs and faster re-attach on subsequent runs.
            await browser.close()


async def new_page(context: BrowserContext) -> Page:
    """Open a new page in the context."""
    return await context.new_page()


async def random_delay(page: Page) -> None:
    """Wait a random human-like duration between actions."""
    ms = random.randint(ACTION_DELAY_MIN_MS, ACTION_DELAY_MAX_MS)  # noqa: S311
    await page.wait_for_timeout(ms)
