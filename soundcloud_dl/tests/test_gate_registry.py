"""Unit tests for the gate handler registry."""

import pytest

from soundcloud_dl.gate_handlers import GateNotSupportedError, get_handler_for_url


def test_hypeddit_url_returns_handler():
    handler_class = get_handler_for_url("https://hypeddit.com/l8nite/sometrack")
    assert handler_class is not None
    assert handler_class.__name__ == "HypedditHandler"


def test_toneden_url_returns_handler():
    handler_class = get_handler_for_url("https://toneden.io/artist/sometrack")
    assert handler_class is not None
    assert handler_class.__name__ == "TonedenHandler"


def test_unknown_url_raises():
    with pytest.raises(GateNotSupportedError, match="unknown-gate.com"):
        get_handler_for_url("https://unknown-gate.com/track")


def test_url_matching_is_case_insensitive():
    handler_class = get_handler_for_url("https://HYPEDDIT.COM/artist/track")
    assert handler_class.__name__ == "HypedditHandler"
