"""Real-Chrome browser context for SoundCloud gate automation (CDP attach)."""

from __future__ import annotations

import contextlib
import logging
import random
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from playwright.async_api import BrowserContext, Page, async_playwright

from soundcloud_dl.chrome_bringup import (
    ensure_chrome_running,
    kill_chrome_on_port,
    shutdown_chrome_on_port,
)
from soundcloud_dl.config import (
    ACTION_DELAY_MAX_MS,
    ACTION_DELAY_MIN_MS,
    CHROME_DEBUG_PORT,
    CHROME_PATH,
    CHROME_PROFILE_DIR,
    HEADED,
)

logger = logging.getLogger("soundcloud_dl.playwright_browser")

_CDP_CONTEXT_ERROR = "Browser context management is not supported"

#: URLs a tab shows when it is holding nothing. Anything else on screen at the end of a run
#: is there because a captcha or a login wall asked for a person, and is not ours to close.
_EMPTY_TAB_URLS = frozenset(
    {
        "",
        "about:blank",
        "chrome://new-tab-page",
        "chrome://new-tab-page/",
        "chrome://newtab",
        "chrome://newtab/",
    }
)


@contextlib.asynccontextmanager
async def attached_browser(*, headed: bool | None = None) -> AsyncIterator[BrowserContext]:
    """
    Async context manager yielding a BrowserContext attached to a real running Chrome.

    Ensures Chrome is running with --remote-debugging-port + dedicated profile,
    then connects via CDP. Chrome must be launched with --enable-automation for full
    CDP access.

    A browser this call started is shut down on the way out; one that was already running
    is left alone. Leaving a headless Chrome behind made the next Dock click on Chrome
    activate that invisible process instead of opening the user's own browser — same app
    bundle, so macOS treats it as already running.

    If the existing Chrome session rejects CDP context management (e.g. launched
    without --enable-automation), kills it and relaunches before retrying once.
    """
    # None means "whatever the config says". A caller that needs a human to look at the
    # window — login, auth, record, inspect, pause — passes True and overrides it.
    want_headed = HEADED if headed is None else headed
    launched = ensure_chrome_running(
        chrome_path=CHROME_PATH,
        profile_dir=CHROME_PROFILE_DIR,
        port=CHROME_DEBUG_PORT,
        headed=want_headed,
    )
    # Nothing was ever opened, so nothing is being held. Distinct from None, which the
    # read below uses to say it could not tell.
    held: list[str] | None = []

    # Wraps the launch, not just the body: a connect that fails, or a Chrome that answers
    # with no context, used to leave the browser this call started running forever.
    try:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.connect_over_cdp(
                    f"http://localhost:{CHROME_DEBUG_PORT}"
                )
            except Exception as e:
                if _CDP_CONTEXT_ERROR not in str(e):
                    raise
                logger.warning(
                    "Existing Chrome on port %d rejected CDP context management — "
                    "killing and relaunching with required flags.",
                    CHROME_DEBUG_PORT,
                )
                kill_chrome_on_port(CHROME_DEBUG_PORT)
                launched = ensure_chrome_running(
                    chrome_path=CHROME_PATH,
                    profile_dir=CHROME_PROFILE_DIR,
                    port=CHROME_DEBUG_PORT,
                    headed=want_headed,
                )
                browser = await pw.chromium.connect_over_cdp(
                    f"http://localhost:{CHROME_DEBUG_PORT}"
                )

            if not browser.contexts:
                msg = "Connected to Chrome but no browser context found"
                raise RuntimeError(msg)
            context = browser.contexts[0]

            try:
                yield context
            finally:
                held = _tabs_left_for_a_person(context)
                await browser.close()
    finally:
        if launched:
            _settle_browser(held, headed=want_headed)


def _settle_browser(held: list[str] | None, *, headed: bool) -> None:
    """Shut the browser down, unless a tab is open that someone can actually go and use."""
    if held is None:
        logger.warning(
            "Could not read the open tabs — leaving Chrome up rather than closing one you "
            "may still need. Close it yourself, or the next run will reuse it."
        )
        return
    if held and headed:
        logger.info("Leaving Chrome up — %d tab(s) still open for you: %s", len(held), held)
        return
    if held:
        # A headless Chrome has no window, so "your tab is open" is not something the user
        # can act on — and leaving it up parks the live SoundCloud session on an open CDP
        # port with nothing on screen to show for it.
        logger.warning(
            "A headless run left %d tab(s) open that you cannot see (%s) — shutting Chrome "
            "down. Re-run that gate with TUNEWRANGLER_SC_HEADED=1 to finish it by hand.",
            len(held),
            held,
        )
    shutdown_chrome_on_port(CHROME_PROFILE_DIR, CHROME_DEBUG_PORT)


def _tabs_left_for_a_person(context: BrowserContext) -> list[str] | None:
    """Where the run is leaving tabs open, or None when that could not be established.

    Read before the CDP connection drops, because a disconnected context reports no pages —
    which would read as "nothing open" and close a captcha someone was just asked to finish.
    None keeps that same failure from arriving as an empty list.

    Scheme, host and path only. These go to a rotating log file, and a tab sitting on the
    OAuth redirect has the authorization code and the CSRF state in its query string.
    """
    try:
        pages = list(context.pages)
    except Exception:  # noqa: BLE001
        logger.warning("Could not list the open tabs", exc_info=True)
        return None
    urls: list[str] = []
    for page in pages:
        try:
            url = page.url
        except Exception:  # noqa: BLE001
            logger.warning("Could not read an open tab's URL", exc_info=True)
            return None
        if url not in _EMPTY_TAB_URLS:
            parts = urllib.parse.urlsplit(url)
            urls.append(urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")))
    return urls


async def new_page(context: BrowserContext) -> Page:
    """Open a new page in the context."""
    return await context.new_page()


async def random_delay(page: Page) -> None:
    """Wait a random human-like duration between actions."""
    ms = random.randint(ACTION_DELAY_MIN_MS, ACTION_DELAY_MAX_MS)  # noqa: S311
    await page.wait_for_timeout(ms)
