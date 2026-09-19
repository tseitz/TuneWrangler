"""Table tests for the unlock predicates. Pure functions, no mocks, no browser."""

import pytest

from soundcloud_dl.gate_handlers.unlock import (
    find_download_target,
    is_action_done,
    is_download_element,
    is_download_enabled,
    is_unlocked_href,
    unlock_reached,
)


def el(**overrides):
    base = {
        "key": "k",
        "id": "",
        "step": "",
        "tag": "a",
        "cls": "",
        "href": "",
        "disabled": False,
        "visible": True,
        "text": "",
        "placeholder": "",
        "name": "",
    }
    return base | overrides


# Both taken verbatim from logs/soundcloud_dl/soundcloud_dl.log — the same button, same page,
# observed in both states, href unchanged.
LOCKED_BUTTON = el(
    id="gateDownloadButton",
    cls=(
        "hype-btn hype-btn-green hype-btn-xlarge hype-w-100 login-to-soundcloud-common "
        "free_dwln  disable hy-btn-lightgray disabled"
    ),
    href="javascript:void(0);",
    text="Get Free Download",
)
UNLOCKED_BUTTON = el(
    id="gateDownloadButton",
    cls="hype-btn hype-btn-green hype-btn-xlarge hype-w-100 login-to-soundcloud-common free_dwln",
    href="javascript:void(0);",
    text="Get Free Download",
)
FOLLOW_UNDONE = el(step="follow", key="data-step=follow", cls="sc-action undone", text="Follow")
FOLLOW_DONE = el(step="follow", key="data-step=follow", cls="sc-action done", text="Follow")


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("javascript:void(0);", False),
        ("javascript:void(0)", False),
        ("JavaScript:Void(0);", False),
        ("", False),
        ("#", False),
        ("  javascript:void(0); ", False),
        ("https://cdn.hypeddit.com/x.mp3", True),
        ("http://example.com/dl", True),
        ("/download/6353", True),
        ("mailto:a@b.com", False),
    ],
)
def test_is_unlocked_href(href, expected):
    assert is_unlocked_href(href) is expected


def test_gate_action_anchor_is_not_a_download_element():
    """The misroute that cost 65s a turn: a follow anchor must never read as the download."""
    assert is_download_element(FOLLOW_UNDONE) is False


@pytest.mark.parametrize("element", [LOCKED_BUTTON, UNLOCKED_BUTTON])
def test_gate_download_button_is_a_download_element(element):
    assert is_download_element(element) is True


def test_disable_class_distinguishes_the_two_button_states():
    assert is_download_enabled(LOCKED_BUTTON) is False
    assert is_download_enabled(UNLOCKED_BUTTON) is True


def test_done_is_not_matched_inside_undone():
    assert is_action_done(FOLLOW_UNDONE) is False
    assert is_action_done(FOLLOW_DONE) is True


def test_unlock_not_reached_while_an_action_is_undone():
    snapshot = {"data-step=follow": FOLLOW_UNDONE, "gateDownloadButton": UNLOCKED_BUTTON}
    assert unlock_reached(snapshot) is False


def test_unlock_reached_when_every_action_is_done():
    snapshot = {"data-step=follow": FOLLOW_DONE, "gateDownloadButton": LOCKED_BUTTON}
    assert unlock_reached(snapshot) is True


def test_unlock_reached_on_a_live_download_href():
    live = el(id="downloadProcess", href="https://cdn.hypeddit.com/x.mp3", text="Download")
    snapshot = {"data-step=follow": FOLLOW_UNDONE, "downloadProcess": live}
    assert unlock_reached(snapshot) is True


def test_find_download_target_prefers_a_live_href():
    live = el(key="dp", id="downloadProcess", href="https://cdn.x/y.mp3")
    snapshot = {"gateDownloadButton": UNLOCKED_BUTTON, "dp": live}
    assert find_download_target(snapshot)["key"] == "dp"


def test_find_download_target_falls_back_to_the_enabled_button():
    snapshot = {"gateDownloadButton": UNLOCKED_BUTTON}
    assert find_download_target(snapshot)["id"] == "gateDownloadButton"


def test_find_download_target_ignores_a_locked_button():
    assert find_download_target({"gateDownloadButton": LOCKED_BUTTON}) is None


def test_hypeddit_site_nav_is_not_the_download_button():
    """A nav link with a real href once outranked the real button and navigated away."""
    nav = el(tag="a", href="https://hypeddit.com/music/genre/dubstep", text="Free Downloads")
    assert is_download_element(nav) is False
    assert find_download_target({"nav": nav, "gateDownloadButton": UNLOCKED_BUTTON}) == (
        UNLOCKED_BUTTON
    )
