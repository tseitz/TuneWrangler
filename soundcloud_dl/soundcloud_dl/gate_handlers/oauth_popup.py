"""OAuth popup handling for SoundCloud / Spotify auth + ToneDen / Instagram visit popups."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.gate_handlers.oauth_popup")


async def handle_oauth_popup(popup: Page, gate_name: str) -> None:  # noqa: C901, PLR0912, PLR0915
    """Auto-approve SoundCloud/Spotify OAuth popups; close ToneDen URL-visit popups.

    `gate_name` is only used for log message prefixes.
    """
    try:
        # Use "load" — SoundCloud's auth page is a React SPA; Spotify's is similar.
        await popup.wait_for_load_state("load", timeout=15_000)
        url = popup.url
        is_sc = "soundcloud.com" in url
        is_sp = "accounts.spotify.com" in url
        is_toneden_visit = "toneden.io/auth/custom-url-visit" in url
        is_instagram = "instagram.com" in url
        if not is_sc and not is_sp and not is_toneden_visit and not is_instagram:
            return

        # Instagram follow and ToneDen URL-visit popups just need to be closed
        # after they load — no OAuth interaction required.
        if is_instagram:
            logger.debug("[%s] Instagram follow popup: %s", gate_name, url)
            try:
                await popup.wait_for_timeout(1_000)
                if not popup.is_closed():
                    await popup.close()
            except Exception:  # noqa: BLE001
                pass  # popup already closed itself
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

        if is_sc:
            _allow_selector = (
                "button:has-text('Allow'), button:has-text('Authorize'), "
                "button:has-text('Connect'), input[type='submit'], button[type='submit']"
            )
        else:
            # Spotify's consent screen uses data-testid="auth-accept" or text "Agree"/"Allow".
            _allow_selector = (
                "button[data-testid='auth-accept'], "
                "button:has-text('Agree'), button:has-text('Allow'), "
                "button:has-text('Accept'), button:has-text('Authorize')"
            )

        try:
            await popup.wait_for_selector(_allow_selector, state="visible", timeout=15_000)
        except Exception:  # noqa: BLE001
            pass  # fall through to query_selector; will log if still missing

        allow = await popup.query_selector(_allow_selector)
        if allow is not None:
            logger.info("[%s] %s OAuth popup: clicking Allow", gate_name, vendor)
            await popup.wait_for_timeout(500)
            await allow.click()
            logger.info("[%s] %s OAuth popup: clicked Allow", gate_name, vendor)
            # Wait for the popup to redirect back to the gate host or close itself.
            # ToneDen redirects to toneden.io/auth/spotify/callback then closes;
            # Hypeddit redirects back to hypeddit.com. Either way the popup is done.
            try:
                await popup.wait_for_url("*hypeddit.com*|*toneden.io*", timeout=8_000)
                await popup.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                pass  # popup closed itself or redirected elsewhere — both OK
        else:
            try:
                btns = await popup.evaluate(
                    "Array.from(document.querySelectorAll('button,input[type=submit],a'))"
                    ".filter(el => el.offsetParent !== null)"
                    ".map(el => el.outerHTML.slice(0, 200))"
                )
                logger.debug(
                    "[%s] %s OAuth popup: Allow button not found. Visible elements: %s",
                    gate_name,
                    vendor,
                    btns,
                )
            except Exception:  # noqa: BLE001
                logger.debug(
                    "[%s] %s OAuth popup: Allow button not found (could not dump)",
                    gate_name,
                    vendor,
                )
    except Exception:  # noqa: BLE001
        logger.debug("[%s] OAuth popup handler error", gate_name, exc_info=True)
    finally:
        if not popup.is_closed():
            await popup.close()
