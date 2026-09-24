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


@pytest.fixture(autouse=True)
def _isolate_pending_follows(tmp_path, monkeypatch):
    """Keep the follow ledger out of logs/ during tests.

    A test that reaches pending_follows.hold() for real writes ids into the file the next
    live run sweeps, and that run then tries to unfollow them on the actual account.
    """
    from soundcloud_dl import pending_follows

    monkeypatch.setattr(
        pending_follows, "get_pending_follows_file", lambda: tmp_path / "pending_follows.json"
    )


@pytest.fixture(autouse=True)
def _isolate_track_index(tmp_path, monkeypatch):
    """Keep test tracks out of the index the rename flow reads for real downloads."""
    from soundcloud_dl import track_index

    monkeypatch.setattr(
        track_index, "get_track_index_file", lambda: tmp_path / "track_index.json"
    )
