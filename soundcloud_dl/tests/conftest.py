"""Shared pytest fixtures and hooks for soundcloud_dl tests."""

from __future__ import annotations

import asyncio
import logging

import pytest

logger = logging.getLogger(__name__)

_BROWSER_AVAILABLE: bool | None = None


def _probe_browser() -> bool:
    """One-shot probe: can we actually launch a headless Chromium right now?

    Tests marked `requires_browser` need a real browser. Under sandboxed
    environments (e.g. macOS Mach-port-restricted CI / Claude Code sandbox)
    the launch fails immediately with a Mach-port permission error. Probe
    once per session and cache the result so we don't re-probe per test.
    """
    global _BROWSER_AVAILABLE  # noqa: PLW0603
    if _BROWSER_AVAILABLE is not None:
        return _BROWSER_AVAILABLE

    async def _try() -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            await browser.close()

    try:
        asyncio.run(_try())
        _BROWSER_AVAILABLE = True
    except Exception as exc:  # noqa: BLE001
        logger.info("Browser probe failed (tests requiring browser will skip): %s", exc)
        _BROWSER_AVAILABLE = False
    return _BROWSER_AVAILABLE


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-skip `requires_browser` tests when no browser launch is possible."""
    skip_marker = pytest.mark.skip(reason="requires real browser launch (sandbox-blocked)")
    has_browser_test = any("requires_browser" in item.keywords for item in items)
    if not has_browser_test:
        return
    available = _probe_browser()
    if available:
        return
    for item in items:
        if "requires_browser" in item.keywords:
            item.add_marker(skip_marker)
