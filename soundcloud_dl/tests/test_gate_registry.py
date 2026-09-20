"""Unit tests for the gate handler registry."""

import pytest

from soundcloud_dl.gate_handlers import GateNotSupportedError, get_handler_for_url


def test_hypeddit_url_returns_handler():
    """Judgment, not hypeddit.yaml. The gate enables its download button by class while
    parking it on a carousel slide that has not arrived, so a step list clicks a control
    that is not on screen and the run ends with no file."""
    handler_class = get_handler_for_url("https://hypeddit.com/l8nite/sometrack")
    assert handler_class is not None
    assert handler_class.__name__ == "HypedditJevHandler"


def test_toneden_url_returns_handler():
    handler_class = get_handler_for_url("https://toneden.io/artist/sometrack")
    assert handler_class is not None
    assert handler_class.__name__ == "TonedenHandler"


def test_unknown_url_raises():
    with pytest.raises(GateNotSupportedError, match=r"unknown-gate\.com"):
        get_handler_for_url("https://unknown-gate.com/track")


def test_url_matching_is_case_insensitive():
    handler_class = get_handler_for_url("https://HYPEDDIT.COM/artist/track")
    assert handler_class.__name__ == "HypedditJevHandler"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://droploud.com/track/f196e1fa", "DroploudHandler"),
        ("https://www.droploud.com/gate/abc", "DroploudHandler"),
        ("https://gate.influenceplanner.com/x", "InfluencePlannerHandler"),
        # The short link printed in track descriptions; it redirects to
        # gate.influenceplanner.com, but this is asked before the redirect.
        ("https://ipln.io/abc123", "InfluencePlannerHandler"),
    ],
)
def test_judgment_driven_gates_are_registered(url, expected):
    """Both hosts were extracted from the page and then had nowhere to go.

    soundcloud_page.py has recognised their links all along, so a playlist run found the
    gate URL and raised GateNotSupportedError on it.
    """
    assert get_handler_for_url(url).__name__ == expected


def test_a_judgment_gate_runs_under_its_own_name():
    """Otherwise every line of a droploud run is logged as the gate it was first written
    against, which is what the --jev pilot had to work around."""
    from soundcloud_dl.gate_handlers.jev import DroploudHandler

    handler = DroploudHandler(template_vars={})
    assert handler.gate_name == "droploud_jev"


def test_the_main_pipelines_keyword_arguments_construct_one():
    """main.py builds every handler with the same kwargs and no config — a registry entry
    that cannot take them raises at the first track instead of at import."""
    from soundcloud_dl.gate_handlers.jev import InfluencePlannerHandler

    handler = InfluencePlannerHandler(
        template_vars={"email": "a@b.com", "name": "T", "comment": "hi"},
        action_delay_min_ms=1,
        action_delay_max_ms=2,
        type_delay_ms=3,
        scroll_before_click=True,
        pause=False,
        download_dir=None,
        track_title="Artist - Title",
    )
    assert handler.gate_name == "influenceplanner_jev"
    assert handler.track_title == "Artist - Title"


def test_every_judgment_gate_is_recognisable_as_one():
    """main.py validates the TypeSafe key up front for any JevHandler, before the run
    spends follows it cannot take back. A judgment gate registered as something else
    gets that check skipped and fails partway through instead."""
    from soundcloud_dl.gate_handlers.jev import JevHandler

    for url in (
        "https://hypeddit.com/artist/track",
        "https://droploud.com/track/f196e1fa",
        "https://gate.influenceplanner.com/x",
    ):
        assert issubclass(get_handler_for_url(url), JevHandler), url
