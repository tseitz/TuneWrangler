"""Captcha detection: identify hCaptcha / reCAPTCHA / Turnstile / Cloudflare walls."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.gate_handlers.captcha")


class CaptchaKind(StrEnum):
    HCAPTCHA = "hcaptcha"
    RECAPTCHA = "recaptcha"
    TURNSTILE = "turnstile"
    CLOUDFLARE_INTERSTITIAL = "cloudflare_interstitial"
    DATADOME = "datadome"


class CaptchaEncountered(RuntimeError):  # noqa: N818
    """Raised when a captcha is detected mid-flow. Track is left in captcha_pending state."""

    def __init__(self, kind: CaptchaKind, gate_name: str) -> None:
        super().__init__(f"[{gate_name}] Captcha encountered: {kind}")
        self.kind = kind
        self.gate_name = gate_name


_CAPTCHA_SELECTORS: tuple[tuple[CaptchaKind, str], ...] = (
    (CaptchaKind.HCAPTCHA, 'iframe[src*="hcaptcha.com"]'),
    (CaptchaKind.RECAPTCHA, 'iframe[src*="recaptcha"]'),
    (CaptchaKind.TURNSTILE, '.cf-turnstile, iframe[src*="challenges.cloudflare.com"]'),
    # SoundCloud's bot protection. It challenges the api-v2 calls a page makes, so it can
    # appear as an overlay on a page that otherwise looks fine — and a challenged API call
    # leaves the page rendering nothing at all.
    (CaptchaKind.DATADOME, 'iframe[src*="captcha-delivery.com"], [id^="ddChallenge"]'),
)

_CLOUDFLARE_TEXT_PATTERNS = (
    "verify you are human",
    "checking your browser",
)

# reCAPTCHA v3 background iframes have near-zero size; only iframes at least this
# many pixels on each side are treated as a real, user-blocking challenge.
_RECAPTCHA_VISIBLE_MIN_PX = 50


async def detect_captcha(page: Page) -> CaptchaKind | None:
    """
    Return the first matching captcha kind on the page, or None.

    Checks each known captcha vendor's selector. As a fallback, scans visible body
    text for Cloudflare-style interstitial language.

    reCAPTCHA v3 (invisible) embeds a hidden iframe that is always present on many
    sites as background fraud detection — we skip it unless the iframe has a meaningful
    bounding box (>50px), which indicates a blocking challenge. hCaptcha and Turnstile
    widgets are always interactive so presence alone is enough for those.
    """
    for kind, selector in _CAPTCHA_SELECTORS:
        el = await page.query_selector(selector)
        if el is None:
            continue
        if kind == CaptchaKind.RECAPTCHA:
            try:
                bbox = await el.bounding_box()
            except Exception:  # noqa: BLE001
                logger.debug("reCAPTCHA bounding_box() failed; treating as invisible")
                continue
            if (
                bbox is None
                or bbox["width"] < _RECAPTCHA_VISIBLE_MIN_PX
                or bbox["height"] < _RECAPTCHA_VISIBLE_MIN_PX
            ):
                continue
        return kind
    try:
        body_text = (await page.inner_text("body", timeout=500)).lower()
    except Exception:  # noqa: BLE001
        return None
    if any(p in body_text for p in _CLOUDFLARE_TEXT_PATTERNS):
        return CaptchaKind.CLOUDFLARE_INTERSTITIAL
    return None
