"""Stealth Playwright browser context for SoundCloud gate automation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import Stealth

from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    DOWNLOAD_DIR,
    HEADED,
    get_browser_profile_dir,
)

logger = logging.getLogger("soundcloud_dl.playwright_browser")


@contextlib.asynccontextmanager
async def stealth_browser() -> AsyncIterator[BrowserContext]:
    """
    Async context manager yielding a stealth Playwright BrowserContext.

    Uses a persistent profile (so SoundCloud login is preserved between runs).
    Applies playwright-stealth to suppress automation fingerprints.

    Usage::

        async with stealth_browser() as context:
            page = await context.new_page()
            await page.goto("https://soundcloud.com/...")
    """
    profile_dir = get_browser_profile_dir()
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
    ]

    async with async_playwright() as pw:
        if profile_dir is not None:
            profile_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Using persistent browser profile: %s", profile_dir)
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=not HEADED,
                args=launch_args,
                accept_downloads=True,
                downloads_path=str(DOWNLOAD_DIR) if DOWNLOAD_DIR else None,
            )
        else:
            logger.info("Using ephemeral browser (no persistent profile)")
            browser = await pw.chromium.launch(headless=not HEADED, args=launch_args)
            context = await browser.new_context(accept_downloads=True)

        # Apply stealth to all new pages automatically.
        # The done-callback suppresses "Future exception was never retrieved" warnings
        # that occur when pages close before stealth finishes applying.
        _stealth = Stealth()

        def _on_page(page: Page) -> None:
            task = asyncio.ensure_future(_apply_stealth(page, _stealth))
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

        context.on("page", _on_page)

        try:
            yield context
        finally:
            await context.close()


async def _apply_stealth(page: Page, stealth: Stealth | None = None) -> None:
    """Apply playwright-stealth patches to a page."""
    try:
        s = stealth or Stealth()
        await s.apply_stealth_async(page)
    except Exception:  # noqa: BLE001
        logger.debug("apply_stealth_async failed on page (may be a background page)", exc_info=True)


async def new_stealth_page(context: BrowserContext) -> Page:
    """Open a new page in the context with stealth applied."""
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)
    return page


async def random_delay(page: Page) -> None:
    """Wait a random human-like duration between actions."""
    ms = random.randint(ACTION_DELAY_MIN_MS, ACTION_DELAY_MAX_MS)  # noqa: S311
    await page.wait_for_timeout(ms)
