"""OAuth popup handling for SoundCloud / Spotify auth + ToneDen / Instagram visit popups."""

from __future__ import annotations

import contextlib
import logging
import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.gate_handlers.oauth_popup")


def host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def host_is(host: str, domain: str) -> bool:
    """Host equality or a subdomain of it.

    Never a substring test on the URL: "soundcloud.com" appears in
    https://evil.example/?x=soundcloud.com, which would hand an attacker-controlled page to
    _approve — whose SoundCloud selector ends in a bare input[type=submit].
    """
    return host == domain or host.endswith(f".{domain}")


_SC_ALLOW = (
    "button:has-text('Allow'), button:has-text('Authorize'), "
    "button:has-text('Connect'), input[type='submit'], button[type='submit']"
)


async def _approve(popup: Page, gate_name: str) -> None:
    """Click the consent button on a loaded SoundCloud OAuth popup."""
    # Best-effort wait; on timeout fall through to query_selector below
    # which logs explicitly if the Allow button is still missing.
    with contextlib.suppress(Exception):
        await popup.wait_for_selector(_SC_ALLOW, state="visible", timeout=15_000)

    allow = await popup.query_selector(_SC_ALLOW)
    if allow is None:
        await _dump_buttons(popup, gate_name)
        return

    logger.info("[%s] SoundCloud OAuth popup: clicking Allow", gate_name)
    await popup.wait_for_timeout(500)
    await allow.click()
    logger.info("[%s] SoundCloud OAuth popup: clicked Allow", gate_name)
    # Wait for the popup to redirect back to the gate host or close itself.
    # ToneDen redirects to toneden.io/auth/spotify/callback then closes;
    # Hypeddit redirects back to hypeddit.com. Either way the popup is done.
    # Popup may close itself or redirect elsewhere — both are fine
    # since the OAuth click already registered.
    with contextlib.suppress(Exception):
        await popup.wait_for_url("*hypeddit.com*|*toneden.io*", timeout=8_000)
        await popup.wait_for_timeout(500)


async def _dump_buttons(popup: Page, gate_name: str) -> None:
    """Log what the popup did show, so a changed consent screen is diagnosable."""
    try:
        btns = await popup.evaluate(
            "Array.from(document.querySelectorAll('button,input[type=submit],a'))"
            ".filter(el => el.offsetParent !== null)"
            ".map(el => el.outerHTML.slice(0, 200))"
        )
    except Exception:  # noqa: BLE001
        logger.debug(
            "[%s] SoundCloud OAuth popup: Allow button not found (could not dump)", gate_name
        )
        return
    logger.debug(
        "[%s] SoundCloud OAuth popup: Allow button not found. Visible elements: %s",
        gate_name,
        btns,
    )


async def _close_after_load(popup: Page, timeout_ms: int) -> None:
    """Give a popup that needs no interaction a moment to settle, then close it.

    Suppressed rather than let bubble: the popup may close itself between the wait and
    the close call, and either way run() would close it anyway once the turn ends.
    """
    with contextlib.suppress(Exception):
        await popup.wait_for_timeout(timeout_ms)
        if not popup.is_closed():
            await popup.close()


def _decline(
    popup: Page,
    gate_name: str,
    on_keep_open: Callable[[Page], None] | None,
) -> None:
    """Leave a consent popup for a person, and make sure run() leaves it alone too."""
    logger.warning(
        "[%s] SoundCloud is asking for a grant on your account. Not clicking Allow — decide "
        "on the open tab yourself, then re-run.",
        gate_name,
    )
    if on_keep_open is not None:
        on_keep_open(popup)


async def handle_oauth_popup(
    popup: Page,
    gate_name: str,
    *,
    approve: bool | Callable[[], bool] = True,
    on_keep_open: Callable[[Page], None] | None = None,
) -> None:
    """Auto-approve SoundCloud/Spotify OAuth popups; close ToneDen URL-visit popups.

    `gate_name` is only used for log message prefixes. `approve=False` leaves a consent
    popup open and untouched for a person to decide on — see GateHandler.auto_approve_oauth.
    A callable is asked only once a SoundCloud consent popup has loaded, so the other popups
    this handles never spend a one-shot allowance.

    `on_keep_open` is how that decision reaches the caller. Suppressing this function's own
    close is not enough on its own: run() closes every popup it saw when the run ends, so
    without telling it, the tab the operator was just sent to press Allow on is shut behind
    them and the next run repeats the whole cycle.
    """
    # Two unrelated reasons a popup must outlive this handler, tracked as one flag because
    # the finally below asks the same question either way: is this window still wanted.
    #
    # A popup serving the file — ToneDen's download window never reaches a "load" state and
    # has no URL to recognise, so it falls through to the close below, and closing it
    # mid-transfer cancels a download that is still being written.
    #
    # A consent popup we deliberately did not approve, which is left for a person.
    keep_open = False

    def note_download(_download: object) -> None:
        nonlocal keep_open
        keep_open = True

    popup.on("download", note_download)
    try:
        # Use "load" — SoundCloud's auth page is a React SPA; Spotify's is similar.
        await popup.wait_for_load_state("load", timeout=15_000)
        # Gaterush opens the window blank, saves the comment, then points it at SoundCloud.
        # Judged at the blank page, it was closed as unrecognised before the consent loaded.
        if popup.url in ("", "about:blank"):
            with contextlib.suppress(Exception):
                await popup.wait_for_url(lambda u: u not in ("", "about:blank"), timeout=15_000)
                await popup.wait_for_load_state("load", timeout=15_000)
        url = popup.url
        host = host_of(url)
        is_sc = host_is(host, "soundcloud.com")
        is_sp = host_is(host, "accounts.spotify.com")
        is_toneden_visit = host_is(host, "toneden.io") and "/auth/custom-url-visit" in url
        is_instagram = host_is(host, "instagram.com")
        if not is_sc and not is_sp and not is_toneden_visit and not is_instagram:
            return

        # Instagram follow and ToneDen URL-visit popups just need to be closed
        # after they load — no OAuth interaction required.
        if is_instagram:
            logger.debug("[%s] Instagram follow popup: %s", gate_name, url)
            await _close_after_load(popup, 1_000)
            return

        # ToneDen's Instagram (and other URL-visit) steps open a popup that just
        # records the visit — no OAuth flow needed, just close it after it loads.
        if is_toneden_visit:
            logger.debug("[%s] ToneDen URL-visit popup: %s", gate_name, url)
            await _close_after_load(popup, 1_500)
            return

        # Hypeddit's gate never checks whether Spotify granted anything back — the
        # client-side step is recorded by opening the popup, not by what happens inside
        # it. Trying to click Allow here waited 15s for a button a plain login screen
        # (no active Spotify session) never shows, for no benefit over just closing it.
        if is_sp:
            logger.debug("[%s] Spotify popup: %s", gate_name, url)
            await _close_after_load(popup, 1_000)
            return

        logger.debug("[%s] SoundCloud OAuth popup: %s", gate_name, url)
        if not (approve() if callable(approve) else approve):
            keep_open = True
            _decline(popup, gate_name, on_keep_open)
            return
        await _approve(popup, gate_name)
    except Exception:  # noqa: BLE001
        logger.debug("[%s] OAuth popup handler error", gate_name, exc_info=True)
    finally:
        if not keep_open and not popup.is_closed():
            await popup.close()
