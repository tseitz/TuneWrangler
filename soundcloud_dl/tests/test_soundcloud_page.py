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


def test_decode_gate_sc_accepts_the_newer_gate_hosts() -> None:
    """SIMON SAYS's v2 FREE DOWNLOAD card wraps a pl8list gate; it was dropped as unknown."""
    inner = "https://pl8list.com/crysomemore/mythm-simon-says-crysomemore-remix-v4"
    assert _decode_gate_sc(f"https://gate.sc?url={inner}&token=a") == inner


def test_decode_gate_sc_matches_the_host_not_a_substring() -> None:
    href = "https://gate.sc/?url=https%3A%2F%2Finstagram.com%2Fx%3Fref%3Dhypeddit.com&token=a"
    assert _decode_gate_sc(href) is None


def test_a_real_gate_wins_over_an_earlier_bandcamp_link() -> None:
    """Every description link is gate.sc-wrapped. An artist's Bandcamp link first in the
    page would otherwise get the track skipped as a store page."""
    from soundcloud_dl.soundcloud_page import _pick_gate  # noqa: PLC0415

    bandcamp = "https://gate.sc/?url=https%3A%2F%2Fartist.bandcamp.com%2Ftrack%2Fx&token=a"
    gate = "https://gate.sc/?url=https%3A%2F%2Fpl8list.com%2Fa%2Fb&token=b"
    assert _pick_gate([bandcamp, gate], set()) == (
        "https://pl8list.com/a/b",
        "https://artist.bandcamp.com/track/x",
    )
    assert _pick_gate([bandcamp], set()) == (None, "https://artist.bandcamp.com/track/x")


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("https://gate.sc?url=https%3A%2F%2Flaylo.com%2Fx&token=a", "https://laylo.com/x"),
        ("https://hypeddit.com/a/b", "https://hypeddit.com/a/b"),
    ],
)
def test_unwrap_gate_sc(href: str, expected: str) -> None:
    """A text-matched card link is unwrapped, so the skip list sees laylo, not gate.sc."""
    from soundcloud_dl.soundcloud_page import _unwrap_gate_sc  # noqa: PLC0415

    assert _unwrap_gate_sc(href) == expected
