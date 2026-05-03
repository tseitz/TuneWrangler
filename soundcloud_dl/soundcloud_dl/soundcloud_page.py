"""Interact with a SoundCloud track page to trigger the free download gate."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

from soundcloud_dl.config import PAGE_LOAD_WAIT_SECONDS
from soundcloud_dl.playwright_browser import new_page, random_delay

logger = logging.getLogger("soundcloud_dl.soundcloud_page")

# Known gate domains used to validate gate.sc proxy links.
_GATE_DOMAINS = frozenset({"hypeddit.com", "toneden.io", "fanlink.tv", "fanlink.to"})

# Selectors checked in order. Gate-domain links are tried first since they're
# unambiguous. Text-based selectors are broader and can match description links
# that point back to other SoundCloud tracks.
_SELECTORS = [
    # Direct links to known gate domains (in description or buy-link)
    "a[href*='hypeddit.com']",
    "a[href*='toneden.io']",
    "a[href*='fanlink.tv']",
    "a[href*='fanlink.to']",
    "a[href*='distrokid.com']",
    "a[href*='smarturl.it']",
    # gate.sc is SoundCloud's buy-link URL proxy (wraps the real gate URL in a
    # tracking redirect). Multiple gate.sc links can appear on a page (e.g. one
    # for the download button, others for social follow links). We query all of
    # them and pick the first one whose inner URL targets a known gate domain.
    "a[href*='gate.sc']",
    # SoundCloud's own buy/download link element (native free download)
    "a.sc-buylink",
    ".sc-buylink-wrapper a",
    # Text-based fallbacks scoped to exclude same-origin SC links — the text
    # "FREE DL" / "Free Download" appears in related-track titles and comments,
    # which are SC-internal links (absolute https://soundcloud.com/... OR relative /path)
    # and would navigate the current tab, not open a gate.
    # :not([href^='/']) excludes relative paths; :not([href*='soundcloud.com']) excludes
    # absolute SC links. Both filters are needed.
    "a:has-text('Free Download'):not([href*='soundcloud.com']):not([href^='/'])",
    "a:has-text('FREE DL'):not([href*='soundcloud.com']):not([href^='/'])",
    "a:has-text('Free DL'):not([href*='soundcloud.com']):not([href^='/'])",
    # MUI / React-rendered download buttons (button or anchor styled as button).
    # These appear "above the description" and render after the initial DOM paint —
    # the gate.sc poller above already handles the most common case; these catch
    # direct-href MUI buttons that don't proxy through gate.sc.
    "button:has-text('Free Download')",
    "button:has-text('FREE DL')",
    "[role='button']:has-text('Free Download')",
]


def _decode_gate_sc(href: str) -> str | None:
    """Return the inner URL if this gate.sc href wraps a known gate domain, else None."""
    try:
        inner = parse_qs(urlparse(href).query).get("url", [""])[0]
        if inner and any(d in inner.lower() for d in _GATE_DOMAINS):
            return inner
    except Exception:
        pass
    return None


async def _poll_gate_sc_url(page: Page, timeout_ms: int = 8_000) -> str | None:
    """
    Poll for a gate.sc link that wraps a known gate domain.

    SoundCloud renders some download buttons (e.g. MUI React components) after
    the initial DOM is ready, so the gate.sc link may not exist on the first pass.
    Polls every 500 ms up to timeout_ms before giving up.
    """
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    last_seen: set[str] = set()
    while asyncio.get_event_loop().time() < deadline:
        candidates = await page.query_selector_all("a[href*='gate.sc']")
        for c in candidates:
            href = await c.get_attribute("href") or ""
            inner = _decode_gate_sc(href)
            if inner:
                return inner
            if href not in last_seen:
                logger.debug("gate.sc link (non-gate): %s", href[:120])
                last_seen.add(href)
        await asyncio.sleep(0.5)
    return None


class SoundCloudPageError(RuntimeError):
    """Raised when we can't find or trigger the free download on a SoundCloud page."""


async def get_gate_url(context: BrowserContext, track_url: str) -> str:  # noqa: C901
    """
    Navigate to a SoundCloud track, click the free download button, and return
    the URL of the gate page that opens in the new tab.

    Raises SoundCloudPageError if no free download button is found.
    """
    page = await new_page(context)
    try:
        logger.info("Navigating to track: %s", track_url)
        await page.goto(track_url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for SPA to render
        if PAGE_LOAD_WAIT_SECONDS > 0:
            await page.wait_for_timeout(PAGE_LOAD_WAIT_SECONDS * 1000)

        await random_delay(page)

        # Find the free download element
        el = None
        matched_selector = None
        for selector in _SELECTORS:
            if "gate.sc" in selector:
                # Multiple gate.sc links can appear (download button + social follow links).
                # Poll up to 8s for one whose inner URL targets a known gate domain,
                # skipping social/Instagram proxy links. The MUI download button can
                # render a second after the rest of the page.
                inner = await _poll_gate_sc_url(page)
                if inner:
                    logger.info("Gate URL decoded from gate.sc proxy: %s", inner)
                    return inner
                continue
            el = await page.query_selector(selector)
            if el:
                matched_selector = selector
                logger.info("Found free download element with selector: %s", selector)
                break

        if el is None:
            msg = f"No free download button found on: {track_url}"
            raise SoundCloudPageError(msg)

        # Detect login modal — means we're not authenticated in this profile
        auth_modal = await page.query_selector(".auth-modal")
        if auth_modal:
            msg = (
                "SoundCloud is showing a login prompt. "
                "Run once with TUNEWRANGLER_SC_HEADED=1 to log in and save your session, "
                "then re-run without it."
            )
            raise SoundCloudPageError(msg)

        # If the anchor has a direct href to an external gate, use it without clicking.
        # dispatch_event("click") is a synthetic (non-trusted) event so browsers block
        # window.open() popups triggered by it. Reading href avoids the race entirely.
        href = await el.get_attribute("href") or ""
        is_external = href.startswith("http") and "soundcloud.com" not in href
        if is_external:
            logger.info("Gate URL from href: %s", href)
            return href

        # Text-based selectors (has-text) are broad and can match related-track links
        # or description text that points back to SoundCloud (including relative hrefs).
        # If we matched via text and the href isn't an external gate URL, bail immediately
        # rather than burning 30 seconds waiting for a new tab that will never open.
        is_text_selector = matched_selector is not None and "has-text" in matched_selector
        if is_text_selector:
            msg = (
                f"Text-matched element has no external gate href on: {track_url} "
                f"(href={href!r}) — likely description text or related-track link"
            )
            raise SoundCloudPageError(msg)

        # href is empty or same-origin — fall back to click and wait for new tab.
        # Use el.click() (trusted event) so target=_blank links actually open a tab.
        try:
            async with context.expect_page(timeout=30_000) as new_page_info:
                await el.click()
            gate_page = await new_page_info.value
        except Exception as e:
            raise SoundCloudPageError(
                f"Clicked free download on {track_url} but no new tab opened "
                f"(likely no gate link, just description text)"
            ) from e

        await gate_page.wait_for_load_state("domcontentloaded", timeout=15_000)
        gate_url = gate_page.url
        logger.info("Gate page opened: %s", gate_url)
        return gate_url

    finally:
        await page.close()


async def try_native_sc_download(
    context: BrowserContext,
    track_url: str,
    download_dir: Path | str,
    track_title: str | None = None,
) -> bool:
    """
    Attempt SoundCloud's native "Download file" button (behind the more-actions menu).
    Returns True if the file was saved, False if no native download is available.
    """
    page = await new_page(context)
    try:
        await page.goto(track_url, wait_until="domcontentloaded", timeout=30_000)
        if PAGE_LOAD_WAIT_SECONDS > 0:
            await page.wait_for_timeout(PAGE_LOAD_WAIT_SECONDS * 1000)
        await random_delay(page)

        # Open the "..." more-actions dropdown to reveal the download button.
        more_btn = await page.query_selector("button.sc-button-more")
        if more_btn is None:
            return False
        await more_btn.click()

        try:
            dl_btn = await page.wait_for_selector(
                "button.sc-button-download", state="visible", timeout=3_000
            )
        except Exception:
            return False
        if dl_btn is None:
            return False

        dest = Path(download_dir)
        dest.mkdir(parents=True, exist_ok=True)

        async with page.expect_download(timeout=60_000) as dl_info:
            await dl_btn.click()
        dl = await dl_info.value

        suggested = dl.suggested_filename
        if track_title:
            ext = Path(suggested).suffix
            save_name = f"{track_title}{ext}" if ext else track_title
        else:
            save_name = suggested

        save_path = dest / save_name
        await dl.save_as(str(save_path))
        logger.info("Native SC download saved: %s", save_path)
        return True

    except Exception:
        logger.debug("Native SC download not available for %s", track_url, exc_info=True)
        return False
    finally:
        await page.close()
