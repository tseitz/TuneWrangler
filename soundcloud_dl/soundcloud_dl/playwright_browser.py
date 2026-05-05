"""Real-Chrome browser context for SoundCloud gate automation (CDP attach)."""

from __future__ import annotations

import contextlib
import logging
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from playwright.async_api import BrowserContext, Page, async_playwright

from soundcloud_dl.chrome_bringup import ensure_chrome_running, kill_chrome_on_port
from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    CHROME_DEBUG_PORT,
    CHROME_PATH,
    CHROME_PROFILE_DIR,
)

logger = logging.getLogger("soundcloud_dl.playwright_browser")

_CDP_CONTEXT_ERROR = "Browser context management is not supported"


@contextlib.asynccontextmanager
async def attached_browser() -> AsyncIterator[BrowserContext]:
    """
    Async context manager yielding a BrowserContext attached to a real running Chrome.

    Ensures Chrome is running with --remote-debugging-port + dedicated profile,
    then connects via CDP. The Chrome process is left running on exit.
    Chrome must be launched with --enable-automation for full CDP access.

    If the existing Chrome session rejects CDP context management (e.g. launched
    without --enable-automation), kills it and relaunches before retrying once.
    """
    ensure_chrome_running(
        chrome_path=CHROME_PATH,
        profile_dir=CHROME_PROFILE_DIR,
        port=CHROME_DEBUG_PORT,
    )

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
        except Exception as e:
            if _CDP_CONTEXT_ERROR not in str(e):
                raise
            logger.warning(
                "Existing Chrome on port %d rejected CDP context management — "
                "killing and relaunching with required flags.",
                CHROME_DEBUG_PORT,
            )
            kill_chrome_on_port(CHROME_DEBUG_PORT)
            ensure_chrome_running(
                chrome_path=CHROME_PATH,
                profile_dir=CHROME_PROFILE_DIR,
                port=CHROME_DEBUG_PORT,
            )
            browser = await pw.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")

        if not browser.contexts:
            msg = "Connected to Chrome but no browser context found"
            raise RuntimeError(msg)
        context = browser.contexts[0]

        try:
            yield context
        finally:
            await browser.close()


async def new_page(context: BrowserContext) -> Page:
    """Open a new page in the context."""
    return await context.new_page()


async def random_delay(page: Page) -> None:
    """Wait a random human-like duration between actions."""
    ms = random.randint(ACTION_DELAY_MIN_MS, ACTION_DELAY_MAX_MS)  # noqa: S311
    await page.wait_for_timeout(ms)
