"""Interact with a SoundCloud track page to trigger the free download gate."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

from soundcloud_dl.config import PAGE_LOAD_WAIT_SECONDS
from soundcloud_dl.playwright_browser import new_stealth_page, random_delay

logger = logging.getLogger("soundcloud_dl.soundcloud_page")

# Selectors for the free download button on SoundCloud track pages
FREE_DOWNLOAD_SELECTORS = [
    "a.sc-buylink",
    "a[href*='free'][href*='download']",
    "a:has-text('Free Download')",
    "a:has-text('FREE DL')",
    "a:has-text('Free DL')",
]


class SoundCloudPageError(RuntimeError):
    """Raised when we can't find or trigger the free download on a SoundCloud page."""


async def get_gate_url(context: BrowserContext, track_url: str) -> str:
    """
    Navigate to a SoundCloud track, click the free download button, and return
    the URL of the gate page that opens in the new tab.

    Raises SoundCloudPageError if no free download button is found.
    """
    page = await new_stealth_page(context)
    try:
        logger.info("Navigating to track: %s", track_url)
        await page.goto(track_url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for SPA to render
        if PAGE_LOAD_WAIT_SECONDS > 0:
            await page.wait_for_timeout(PAGE_LOAD_WAIT_SECONDS * 1000)

        await random_delay(page)

        # Find the free download element
        el = None
        for selector in FREE_DOWNLOAD_SELECTORS:
            el = await page.query_selector(selector)
            if el:
                logger.info("Found free download element with selector: %s", selector)
                break

        if el is None:
            msg = f"No free download button found on: {track_url}"
            raise SoundCloudPageError(msg)

        # Intercept the new tab that opens on click
        async with context.expect_page() as new_page_info:
            await el.click()

        gate_page = await new_page_info.value
        await gate_page.wait_for_load_state("domcontentloaded", timeout=15_000)
        gate_url = gate_page.url
        logger.info("Gate page opened: %s", gate_url)
        return gate_url

    finally:
        await page.close()
