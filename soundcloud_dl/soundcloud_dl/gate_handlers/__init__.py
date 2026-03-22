"""Gate handler registry: maps gate service URLs to handler classes."""

from __future__ import annotations

from urllib.parse import urlparse


class GateNotSupportedError(ValueError):
    """Raised when no handler is registered for a given URL."""


def get_handler_for_url(url: str) -> type:
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

    domain = urlparse(url).netloc or url
    msg = f"No gate handler registered for: {domain}"
    raise GateNotSupportedError(msg)
