"""Unit tests for the sign-in stop (login_wall.py)."""

import pytest

from soundcloud_dl.gate_handlers.login_wall import detect_login_wall, normalize_host, same_site


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.droploud.com/track/abc", "droploud.com"),
        ("https://DropLoud.com:8443/x", "droploud.com"),
        ("https://accounts.google.com/v3/signin", "accounts.google.com"),
        ("not a url", ""),
    ],
)
def test_normalize_host(url, expected):
    assert normalize_host(url) == expected


@pytest.mark.parametrize(
    ("url", "gate_host", "expected"),
    [
        ("https://droploud.com/track/abc", "droploud.com", True),
        ("https://www.droploud.com/track/abc", "droploud.com", True),
        ("https://cdn.droploud.com/f.mp3", "droploud.com", True),
        # The gate itself can sit on a subdomain; the track page on the bare domain is
        # still the same gate, not a redirect away from it.
        ("https://hypeddit.com/x", "gate.hypeddit.com", True),
        ("https://accounts.google.com/v3/signin", "droploud.com", False),
        ("https://droploudmalicious.com/x", "droploud.com", False),
    ],
)
def test_same_site(url, gate_host, expected):
    assert same_site(url, gate_host) is expected


def test_off_host_navigation_is_the_stop():
    """The real miss: a droploud run reached Google's sign-in form and typed into it."""
    reason = detect_login_wall("https://accounts.google.com/v3/signin/identifier", "droploud.com")
    assert reason == "left the gate for accounts.google.com"


@pytest.mark.parametrize(
    "path",
    ["/login", "/sign-up", "/signin?next=%2Ftrack", "/account/login", "/auth/callback"],
)
def test_a_login_path_on_the_gate_host_also_stops(path):
    assert detect_login_wall(f"https://droploud.com{path}", "droploud.com") is not None


@pytest.mark.parametrize(
    "url",
    [
        "https://droploud.com/track/3c5122b8",
        "https://droploud.com/gate/3c5122b8",
        # "login" inside a longer segment is not a login page.
        "https://droploud.com/blog/logins-explained",
        "about:blank",
        "",
    ],
)
def test_the_gate_itself_is_never_a_stop(url):
    assert detect_login_wall(url, "droploud.com") is None


def test_no_anchor_host_never_stops():
    """Before the first turn anchors the host, the guard must not fire on anything."""
    assert detect_login_wall("https://accounts.google.com/signin", "") is None
