"""Tests for soundcloud_page._decode_gate_sc — pure URL-decoding logic."""

from __future__ import annotations

import pytest

from soundcloud_dl.soundcloud_page import _decode_gate_sc


@pytest.mark.parametrize(
    ("inner", "domain"),
    [
        ("https://hypeddit.com/abc/123", "hypeddit"),
        ("https://toneden.io/x/y", "toneden"),
        ("https://fanlink.tv/foo", "fanlink.tv"),
        ("https://fanlink.to/bar", "fanlink.to"),
        ("https://pumpyoursound.com/track", "pumpyoursound"),
        ("https://followeb.de/abc", "followeb"),
        ("https://laylo.com/baz", "laylo"),
    ],
)
def test_decode_gate_sc_returns_inner_for_known_gate_domains(inner: str, domain: str) -> None:
    href = f"https://gate.sc/?url={inner}&token=abc"
    assert _decode_gate_sc(href) == inner, f"expected gate domain '{domain}' to decode"


def test_decode_gate_sc_returns_none_for_non_gate_domain() -> None:
    href = "https://gate.sc/?url=https://instagram.com/some_artist&token=abc"
    assert _decode_gate_sc(href) is None


def test_decode_gate_sc_returns_none_when_url_param_missing() -> None:
    href = "https://gate.sc/?token=abc"
    assert _decode_gate_sc(href) is None


def test_decode_gate_sc_returns_none_for_malformed_input() -> None:
    assert _decode_gate_sc("not a url") is None
    assert _decode_gate_sc("") is None


def test_decode_gate_sc_handles_url_encoded_inner() -> None:
    """gate.sc proxy URL-encodes the inner URL — parse_qs should decode it."""
    inner = "https://hypeddit.com/track/abc?campaign=test"
    encoded = "https%3A%2F%2Fhypeddit.com%2Ftrack%2Fabc%3Fcampaign%3Dtest"
    href = f"https://gate.sc/?url={encoded}&token=xyz"
    assert _decode_gate_sc(href) == inner


def test_decode_gate_sc_case_insensitive_domain_match() -> None:
    """Domain match is case-insensitive (per implementation: inner.lower())."""
    href = "https://gate.sc/?url=https://HYPEDDIT.COM/track&token=abc"
    assert _decode_gate_sc(href) == "https://HYPEDDIT.COM/track"
