"""Gate handler registry: maps gate service URLs to handler classes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from playwright.async_api import Page

    from soundcloud_dl.gate_handlers.base import GateHandler


class GateNotSupportedError(ValueError):
    """Raised when no handler is registered for a given URL."""


# Domains we explicitly refuse to support. Tracks with these gate URLs are
# marked 'unsupported' immediately without loading the page.
_BLACKLISTED_DOMAINS: frozenset[str] = frozenset(
    [
        "laylo.com",
    ]
)


def is_url_blacklisted(url: str) -> bool:
    """Return True if the URL's domain is in the blacklist."""
    lower = url.lower()
    return any(domain in lower for domain in _BLACKLISTED_DOMAINS)


async def detect_handler_from_page(page: Page) -> type[GateHandler] | None:
    """
    Inspect page content to identify the gate type when URL matching fails.

    Used for custom-domain gates (e.g. Hypeddit white-label) where the URL
    doesn't contain the vendor's domain but the HTML structure is recognisable.
    Returns the handler class, or None if unrecognised.
    """
    # Hypeddit: has a#downloadProcess or the smartlink carousel structure.
    el = await page.query_selector("a#downloadProcess, a.dp, #downloadProcess")
    if el is not None:
        from soundcloud_dl.gate_handlers.hypeddit import HypedditHandler  # noqa: PLC0415

        return HypedditHandler

    # ToneDen: has the toneden-player or fan-gate wrapper.
    el = await page.query_selector(".toneden-player, [data-toneden], #fan-gate")
    if el is not None:
        from soundcloud_dl.gate_handlers.toneden import TonedenHandler  # noqa: PLC0415

        return TonedenHandler

    # PumpYourSound: has the socBtn__soundcloud or fangatex comment input.
    el = await page.query_selector(
        "div.socBtn__soundcloud, input.fangatex__icomment, [data-fangate-url]"
    )
    if el is not None:
        from soundcloud_dl.gate_handlers.pumpyoursound import PumpYourSoundHandler  # noqa: PLC0415

        return PumpYourSoundHandler

    return None


def get_handler_for_url(url: str) -> type[GateHandler]:  # noqa: PLR0911
    """
    Return the GateHandler subclass for the given gate URL.

    Imports are deferred so that adding a new handler only requires registering
    its URL pattern here — no changes to any other file.

    Raises GateNotSupportedError if no handler matches.
    """
    lower = url.lower()

    if "hypeddit.com" in lower:
        from soundcloud_dl.gate_handlers.hypeddit import HypedditHandler  # noqa: PLC0415

        return HypedditHandler

    if "toneden.io" in lower:
        from soundcloud_dl.gate_handlers.toneden import TonedenHandler  # noqa: PLC0415

        return TonedenHandler

    if "fanlink.tv" in lower or "fanlink.to" in lower:
        from soundcloud_dl.gate_handlers.fanlink import FanLinkHandler  # noqa: PLC0415

        return FanLinkHandler

    if "pumpyoursound.com" in lower:
        from soundcloud_dl.gate_handlers.pumpyoursound import PumpYourSoundHandler  # noqa: PLC0415

        return PumpYourSoundHandler

    if "followeb.de" in lower:
        from soundcloud_dl.gate_handlers.followeb import FollowebHandler  # noqa: PLC0415

        return FollowebHandler

    if "droploud.com" in lower:
        from soundcloud_dl.gate_handlers.jev import DroploudHandler  # noqa: PLC0415

        return DroploudHandler

    # ipln.io is the short link printed in track descriptions and redirects to
    # gate.influenceplanner.com. soundcloud_page.py already extracts both spellings, so both
    # arrive here — the redirect has not necessarily happened yet when this is asked.
    if "influenceplanner.com" in lower or "ipln.io" in lower:
        from soundcloud_dl.gate_handlers.jev import InfluencePlannerHandler  # noqa: PLC0415

        return InfluencePlannerHandler

    domain = urlparse(url).netloc or url
    msg = f"No gate handler registered for: {domain}"
    raise GateNotSupportedError(msg)
