"""Table tests for the unlock predicates. Pure functions, no mocks, no browser."""

import pytest

from soundcloud_dl.gate_handlers.unlock import (
    find_download_target,
    is_action_done,
    is_download_element,
    is_download_enabled,
    is_unlocked_href,
    page_actions_complete,
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
        "icons": [],
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


def test_actions_done_is_not_unlocked_on_a_carousel_gate():
    """The download button is several 'Next' clicks past the last action."""
    snapshot = {"data-step=follow": FOLLOW_DONE, "gateDownloadButton": LOCKED_BUTTON}
    assert page_actions_complete(snapshot) is True
    assert unlock_reached(snapshot) is False


def test_unlock_reached_once_an_enabled_download_is_on_screen():
    snapshot = {"data-step=follow": FOLLOW_DONE, "gateDownloadButton": UNLOCKED_BUTTON}
    assert unlock_reached(snapshot) is True


def test_page_actions_complete_is_false_while_one_is_undone():
    assert page_actions_complete({"data-step=follow": FOLLOW_UNDONE}) is False


def test_page_actions_complete_is_false_with_no_actions_at_all():
    assert page_actions_complete({"gateDownloadButton": UNLOCKED_BUTTON}) is False


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


# Taken from a real run: once the four actions are done, hypeddit drops the disable classes
# from #gateDownloadButton while leaving it parked on an off-screen carousel slide.
OFFSCREEN_READY_BUTTON = el(
    id="gateDownloadButton",
    key="gateDownloadButton",
    cls="hype-btn hype-btn-green hype-btn-xlarge hype-w-100 login-to-soundcloud-common free_dwln",
    href="javascript:void(0);",
    text="Download",
    visible=False,
)


def test_an_enabled_download_still_counts_when_it_is_off_screen():
    """Visible-only detection read this as a locked gate and the run stalled on Next."""
    snapshot = {"data-step=follow": FOLLOW_DONE, "gateDownloadButton": OFFSCREEN_READY_BUTTON}
    assert unlock_reached(snapshot) is True
    assert find_download_target(snapshot)["id"] == "gateDownloadButton"


# #downloadProcess opens the gate; it carries no disable class even while fully locked.
GATE_OPENER = el(
    key="downloadProcess",
    id="downloadProcess",
    tag="a",
    cls="dp hype-btn",
    href="javascript:void(0);",
    text="Download",
)


def test_the_gate_opener_is_not_mistaken_for_the_download():
    """Judged by class alone it looked ready on a freshly loaded, fully locked gate."""
    assert is_download_element(GATE_OPENER) is True
    assert find_download_target({"downloadProcess": GATE_OPENER}) is None
    assert unlock_reached({"downloadProcess": GATE_OPENER}) is False


def test_the_gate_opener_counts_once_its_href_goes_live():
    live = GATE_OPENER | {"href": "https://cdn.hypeddit.com/x.mp3"}
    assert find_download_target({"downloadProcess": live})["key"] == "downloadProcess"


# ToneDen, both states off the live page. Identical but for the icon: no href either way,
# no disable class either way, and the same text — so the snapshot key is the same too.
TONEDEN_LOCKED = el(
    key="a@locked",
    tag="a",
    cls="btn primary large expand expand post-gate-btn",
    text="FREE DOWNLOAD",
    icons=["lock"],
)
TONEDEN_OPEN = el(
    key="a@locked",
    tag="a",
    cls="btn success large expand expand post-gate-btn",
    text="FREE DOWNLOAD",
    icons=["download"],
)


def test_toneden_button_is_recognised_as_the_download():
    assert is_download_element(TONEDEN_OPEN) is True
    assert find_download_target({"a@locked": TONEDEN_OPEN})["key"] == "a@locked"
    assert unlock_reached({"a@locked": TONEDEN_OPEN}) is True


def test_a_padlocked_toneden_button_is_not_a_download_yet():
    """The stall this closes: judged ready while locked, clicked once, then banned by key.

    judgment.py banks the key before attempting, and the key is the same in both states, so
    one premature click made the real button unreachable for the whole run.
    """
    assert is_download_enabled(TONEDEN_LOCKED) is False
    assert find_download_target({"a@locked": TONEDEN_LOCKED}) is None
    assert unlock_reached({"a@locked": TONEDEN_LOCKED}) is False


def test_a_padlocked_button_stays_locked_even_when_it_carries_an_href():
    """A live href was once proof on its own, which skipped the readiness check entirely."""
    linked = TONEDEN_LOCKED | {"href": "/gate/locked"}
    assert find_download_target({"a@locked": linked}) is None
    assert unlock_reached({"a@locked": linked}) is False


def test_an_unfamiliar_locked_icon_still_reads_as_locked():
    """Only the open state was observed, so readiness is a positive check on 'download'."""
    assert is_download_enabled(TONEDEN_LOCKED | {"icons": ["lock-alt"]}) is False
    assert is_download_enabled(TONEDEN_LOCKED | {"icons": []}) is False


def test_icon_gating_does_not_reach_buttons_that_carry_no_icons():
    """Every hypeddit download button reports icons=[]; none may start depending on one."""
    assert is_download_enabled(UNLOCKED_BUTTON) is True
    assert find_download_target({"gateDownloadButton": UNLOCKED_BUTTON})["id"] == (
        "gateDownloadButton"
    )


# Taken verbatim from logs/soundcloud_dl/debug/captures/influenceplanner-Na9k2IGP-20260920/,
# the same button on the same page captured either side of a manual unlock. It is a
# <button> with no id and no href, and the only tokens that move are at the tail.
_IPLN_SHARED = (
    "group/button shrink-0 border border-transparent bg-clip-padding text-xs font-medium "
    "whitespace-nowrap disabled:pointer-events-none disabled:opacity-50 "
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 w-full h-14 flex items-center "
    "justify-center gap-2 bg-primary hover:opacity-90 cursor-pointer rounded-md"
)
IPLN_LOCKED = el(
    tag="button",
    text="Download",
    cls=f"{_IPLN_SHARED} text-transparent opacity-50 pointer-events-none relative",
    icons=["lock"],
)
IPLN_OPEN = el(tag="button", text="Download", cls=f"{_IPLN_SHARED} text-white", icons=["download"])


def test_a_button_download_is_recognised_at_all():
    """unlock.py used to require tag == 'a', so InfluencePlanner's button was invisible:
    find_download_target returned None every turn and the model was offered no download."""
    assert is_download_element(IPLN_OPEN)
    assert is_download_element(IPLN_LOCKED)


def test_the_open_influenceplanner_button_is_clickable():
    assert is_download_enabled(IPLN_OPEN)
    assert find_download_target({"d": IPLN_OPEN}) is IPLN_OPEN
    assert unlock_reached({"d": IPLN_OPEN})


def test_the_locked_influenceplanner_button_is_not():
    assert not is_download_enabled(IPLN_LOCKED)
    assert find_download_target({"d": IPLN_LOCKED}) is None
    assert not unlock_reached({"d": IPLN_LOCKED})


def test_the_tailwind_variants_of_pointer_events_none_do_not_disable():
    """`disabled:pointer-events-none` and `[&_svg]:pointer-events-none` sit in the class
    list of a perfectly clickable control. Only the bare token means disabled."""
    assert is_download_enabled(IPLN_OPEN)
    assert "disabled:pointer-events-none" in IPLN_OPEN["cls"]
    assert "[&_svg]:pointer-events-none" in IPLN_OPEN["cls"]


def test_a_padlock_locks_any_control_without_a_per_host_opt_in():
    """The padlock is unambiguous wherever it shows up, unlike the open state's icon."""
    assert not is_download_enabled(el(tag="button", text="Download", icons=["lock"]))
    assert not is_download_enabled(el(tag="button", text="Download", icons=["lock-keyhole"]))


@pytest.mark.parametrize(
    "text",
    ["Download the app on iOS", "Download our mobile app", "Downloads", ""],
)
def test_a_button_that_merely_mentions_downloading_is_not_the_download(text):
    """Fails closed: an unlisted label costs a run, a wrong match costs a burned key."""
    assert not is_download_element(el(tag="button", text=text))


@pytest.mark.parametrize("text", ["Download", "FREE DOWNLOAD", "  download  ", "Download."])
def test_the_observed_download_labels_all_match(text):
    assert is_download_element(el(tag="button", text=text))
