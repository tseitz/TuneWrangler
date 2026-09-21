"""Who owns the Chrome a run attached to, and whether it may be shut down."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from soundcloud_dl import playwright_browser


def _page(url: str) -> MagicMock:
    page = MagicMock()
    page.url = url
    return page


@contextlib.contextmanager
def _attached(*, launched: bool, pages: list[str], with_context: bool = True):
    """Stand in for a real CDP attach, yielding the shutdown mock to assert against."""
    context = MagicMock()
    context.pages = [_page(u) for u in pages]
    browser = MagicMock()
    browser.contexts = [context] if with_context else []
    browser.close = AsyncMock()

    pw = MagicMock()
    pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    pw_cm = MagicMock()
    pw_cm.__aenter__ = AsyncMock(return_value=pw)
    pw_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(playwright_browser, "async_playwright", return_value=pw_cm),
        patch.object(playwright_browser, "ensure_chrome_running", return_value=launched),
        patch.object(playwright_browser, "shutdown_chrome_on_port") as mock_shutdown,
    ):
        yield mock_shutdown


@pytest.mark.asyncio
async def test_a_browser_this_run_launched_is_shut_down():
    # Otherwise it outlives the run headless, and macOS then activates that invisible
    # process instead of opening the user's own Chrome — the app bundle is the same one.
    with _attached(launched=True, pages=["about:blank"]) as mock_shutdown:
        async with playwright_browser.attached_browser():
            pass
    mock_shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_a_browser_someone_else_started_is_left_alone():
    with _attached(launched=False, pages=["about:blank"]) as mock_shutdown:
        async with playwright_browser.attached_browser():
            pass
    mock_shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_tabs_left_open_in_a_headed_run_keep_the_browser_up():
    # A captcha or a login wall ends the run by leaving its tab open and telling the user
    # to finish it. Shutting down here throws that away before they have looked.
    with _attached(
        launched=True,
        pages=["about:blank", "https://hypeddit.com/artist/track"],
    ) as mock_shutdown:
        async with playwright_browser.attached_browser(headed=True):
            pass
    mock_shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_a_headless_run_does_not_park_a_session_on_a_tab_nobody_can_see():
    # Headless has no window, so "your tab is open" is not something the user can act on.
    # Keeping it alive leaves the live SoundCloud login on an open CDP port with nothing
    # on screen to show for it, and the next run reuses it rather than cleaning it up.
    with _attached(
        launched=True,
        pages=["about:blank", "https://hypeddit.com/artist/track"],
    ) as mock_shutdown:
        async with playwright_browser.attached_browser(headed=False):
            pass
    mock_shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_tabs_that_cannot_be_read_keep_the_browser_up():
    # A context that has already dropped reports no pages, which is indistinguishable from
    # "nothing was open" — and closing on that guess is the exact thing the read guards.
    with _attached(launched=True, pages=[]) as mock_shutdown:
        with patch.object(playwright_browser, "_tabs_left_for_a_person", return_value=None):
            async with playwright_browser.attached_browser(headed=True):
                pass
    mock_shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_a_tab_url_is_logged_without_its_query(caplog):
    # These go to a rotating log file, and a tab sitting on the OAuth redirect carries the
    # authorization code and the CSRF state in its query string.
    context = MagicMock()
    context.pages = [_page("http://localhost:8080/callback?code=SECRET&state=ALSOSECRET")]

    urls = playwright_browser._tabs_left_for_a_person(context)

    assert urls == ["http://localhost:8080/callback"]
    assert "SECRET" not in repr(urls)


@pytest.mark.asyncio
async def test_a_browser_is_not_left_behind_when_the_attach_itself_fails():
    # The launch happens before the connect. A Chrome that comes up and then answers with
    # no usable context used to be left running with nobody holding a handle to it.
    with _attached(launched=True, pages=[], with_context=False) as mock_shutdown:
        with pytest.raises(RuntimeError, match="no browser context"):
            async with playwright_browser.attached_browser(headed=False) as ctx:
                _ = ctx
    mock_shutdown.assert_called_once()


@pytest.mark.asyncio
async def test_the_browser_is_shut_down_even_when_the_run_raises():
    with _attached(launched=True, pages=["about:blank"]) as mock_shutdown:
        with pytest.raises(RuntimeError, match="gate blew up"):
            async with playwright_browser.attached_browser():
                msg = "gate blew up"
                raise RuntimeError(msg)
    mock_shutdown.assert_called_once()
