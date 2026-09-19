"""Capture a gate page's DOM before and after a manual unlock, then report what changed.

Gate sites redesign without warning, and when they do, the handler's selectors go stale
in ways that are hard to guess at. The reliable way to find the new unlock condition is
to watch a person do it: snapshot the page, let them complete the gate by hand, snapshot
again, and report which elements changed. The element that flips from disabled to enabled
is the one the handler has to wait for.

Run it with: deno task py --inspect <gate-url>
"""

import asyncio
import logging
from typing import Any

from playwright.async_api import Page

from soundcloud_dl.config import get_debug_dir
from soundcloud_dl.gate_handlers.dom_snapshot import snapshot_elements
from soundcloud_dl.playwright_browser import attached_browser

logger = logging.getLogger("soundcloud_dl.inspect_gate")

# Fields worth diffing. A gate unlock nearly always shows up as a class change
# (e.g. losing "disabled"), an href changing off the javascript:void(0) placeholder,
# or a previously hidden element becoming visible.
_TRACKED_FIELDS = ("cls", "href", "disabled", "visible", "text", "checked")


async def _snapshot(page: Page) -> dict[str, dict[str, Any]]:
    """Record the state of every interactive element, keyed so it survives a re-render."""
    snapshot: dict[str, dict[str, Any]] = {}
    for el in await snapshot_elements(page):
        snapshot.setdefault(el["key"], el)
    return snapshot


def _report(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> None:
    """Log every element that changed, appeared, or disappeared between the snapshots."""
    changed = 0
    for key, now in after.items():
        was = before.get(key)
        if was is None:
            logger.info("NEW      %-34s <%s> %r", key, now["tag"], now["text"])
            logger.info("           class=%s href=%s", now["cls"], now["href"])
            changed += 1
            continue
        deltas = [(f, was[f], now[f]) for f in _TRACKED_FIELDS if was[f] != now[f]]
        if deltas:
            logger.info("CHANGED  %-34s <%s> %r", key, now["tag"], now["text"])
            for field, old, new in deltas:
                logger.info("           %-9s %r → %r", field, old, new)
            changed += 1
    for key, was in before.items():
        if key not in after:
            logger.info("GONE     %-34s <%s> %r", key, was["tag"], was["text"])
            changed += 1
    if changed == 0:
        logger.warning("Nothing changed between the two snapshots.")
    else:
        logger.info("%d element(s) differed.", changed)


async def inspect_gate(url: str) -> None:
    """Open a gate page, wait for a manual unlock, and report what the unlock changed."""
    debug_dir = get_debug_dir()
    async with attached_browser() as context:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        logger.info("Gate page open: %s", page.url)

        before = await _snapshot(page)
        await asyncio.to_thread(
            (debug_dir / "inspect-before.html").write_text,
            await page.content(),
            encoding="utf-8",
        )
        logger.info(
            "Captured %d elements. Snapshot → %s", len(before), debug_dir / "inspect-before.html"
        )
        logger.info("")
        logger.info("Now complete the gate BY HAND in the Chrome window.")
        logger.info("Go all the way until the download button is genuinely clickable.")
        logger.info("Do not click download. Come back here and press Enter.")
        await asyncio.to_thread(input, "")

        after = await _snapshot(page)
        await asyncio.to_thread(
            (debug_dir / "inspect-after.html").write_text,
            await page.content(),
            encoding="utf-8",
        )
        logger.info("Snapshot → %s", debug_dir / "inspect-after.html")
        logger.info("─" * 60)
        _report(before, after)
        logger.info("─" * 60)
        await page.close()
