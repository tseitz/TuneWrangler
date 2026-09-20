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
# Spotify's consent screen uses data-testid="auth-accept" or text "Agree"/"Allow".
_SPOTIFY_ALLOW = (
    "button[data-testid='auth-accept'], "
    "button:has-text('Agree'), button:has-text('Allow'), "
    "button:has-text('Accept'), button:has-text('Authorize')"
)


async def _approve(popup: Page, gate_name: str, *, vendor: str) -> None:
    """Click the consent button on a loaded OAuth popup."""
    selector = _SC_ALLOW if vendor == "SoundCloud" else _SPOTIFY_ALLOW
    # Best-effort wait; on timeout fall through to query_selector below
    # which logs explicitly if the Allow button is still missing.
    with contextlib.suppress(Exception):
        await popup.wait_for_selector(selector, state="visible", timeout=15_000)

    allow = await popup.query_selector(selector)
    if allow is None:
        await _dump_buttons(popup, gate_name, vendor)
        return

    logger.info("[%s] %s OAuth popup: clicking Allow", gate_name, vendor)
    await popup.wait_for_timeout(500)
    await allow.click()
    logger.info("[%s] %s OAuth popup: clicked Allow", gate_name, vendor)
    # Wait for the popup to redirect back to the gate host or close itself.
    # ToneDen redirects to toneden.io/auth/spotify/callback then closes;
    # Hypeddit redirects back to hypeddit.com. Either way the popup is done.
    # Popup may close itself or redirect elsewhere — both are fine
    # since the OAuth click already registered.
    with contextlib.suppress(Exception):
        await popup.wait_for_url("*hypeddit.com*|*toneden.io*", timeout=8_000)
        await popup.wait_for_timeout(500)


async def _dump_buttons(popup: Page, gate_name: str, vendor: str) -> None:
    """Log what the popup did show, so a changed consent screen is diagnosable."""
    try:
        btns = await popup.evaluate(
            "Array.from(document.querySelectorAll('button,input[type=submit],a'))"
            ".filter(el => el.offsetParent !== null)"
            ".map(el => el.outerHTML.slice(0, 200))"
        )
    except Exception:  # noqa: BLE001
        logger.debug(
            "[%s] %s OAuth popup: Allow button not found (could not dump)", gate_name, vendor
        )
        return
    logger.debug(
        "[%s] %s OAuth popup: Allow button not found. Visible elements: %s",
        gate_name,
        vendor,
        btns,
    )


def _decline(
    popup: Page,
    gate_name: str,
    vendor: str,
    on_keep_open: Callable[[Page], None] | None,
) -> None:
    """Leave a consent popup for a person, and make sure run() leaves it alone too."""
    logger.warning(
        "[%s] %s is asking for a grant on your account. Not clicking Allow — decide on "
        "the open tab yourself, then re-run.",
        gate_name,
        vendor,
    )
    if on_keep_open is not None:
        on_keep_open(popup)


async def handle_oauth_popup(
    popup: Page,
    gate_name: str,
    *,
    approve: bool = True,
    on_keep_open: Callable[[Page], None] | None = None,
) -> None:
    """Auto-approve SoundCloud/Spotify OAuth popups; close ToneDen URL-visit popups.

    `gate_name` is only used for log message prefixes. `approve=False` leaves a consent
    popup open and untouched for a person to decide on — see GateHandler.auto_approve_oauth.

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
            # Popup may close itself between is_closed() check and close() call.
            with contextlib.suppress(Exception):
                await popup.wait_for_timeout(1_000)
                if not popup.is_closed():
                    await popup.close()
            return

        # ToneDen's Instagram (and other URL-visit) steps open a popup that just
        # records the visit — no OAuth flow needed, just close it after it loads.
        if is_toneden_visit:
            logger.debug("[%s] ToneDen URL-visit popup: %s", gate_name, url)
            await popup.wait_for_timeout(1_500)
            if not popup.is_closed():
                await popup.close()
            return

        vendor = "SoundCloud" if is_sc else "Spotify"
        logger.debug("[%s] %s OAuth popup: %s", gate_name, vendor, url)
        if not approve:
            keep_open = True
            _decline(popup, gate_name, vendor, on_keep_open)
            return
        await _approve(popup, gate_name, vendor=vendor)
    except Exception:  # noqa: BLE001
        logger.debug("[%s] OAuth popup handler error", gate_name, exc_info=True)
    finally:
        if not keep_open and not popup.is_closed():
            await popup.close()
