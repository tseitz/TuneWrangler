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


@pytest.mark.parametrize(
    ("url", "expected_slug"),
    [
        ("https://gaterush.me/GiMVei", "gaterush_jev"),
        ("https://www.some-new-gate.io/abc", "some-new-gate_jev"),
        ("https://gate.example.com/x", "gate_jev"),
    ],
)
def test_an_unregistered_host_gets_a_judgment_handler_named_after_it(url, expected_slug):
    """A step list has to be written per host before that host works at all. Judgment reads
    the page, so an unknown gate is worth attempting rather than retiring — and retiring is
    what the alternative means, since 'unsupported' is a resume skip state.
    """
    from soundcloud_dl.gate_handlers.jev import JevHandler, judgment_handler_for

    handler_cls = judgment_handler_for(url)
    assert issubclass(handler_cls, JevHandler)
    assert handler_cls.gate_slug == expected_slug
    # type() takes the name as given, and a host may carry characters a class name cannot.
    assert handler_cls.__name__.isidentifier()


def test_the_fallback_names_the_run_after_the_gate_not_a_generic_slug():
    """Otherwise every unregistered gate's log lines and run artifacts land under one name
    and a failure cannot be traced back to the host it came from."""
    from soundcloud_dl.gate_handlers.jev import JevHandler, judgment_handler_for

    assert judgment_handler_for("https://gaterush.me/x").gate_slug != JevHandler.gate_slug


def test_get_handler_for_url_still_raises_for_an_unknown_host():
    """The fallback belongs at the call site that has a live page, not in the registry:
    main.py's meta-gate redirect asks this about whatever URL a gate ended on, and a
    registry that always answers would start a second gate run on a CDN or success page.
    """
    with pytest.raises(GateNotSupportedError):
        get_handler_for_url("https://some-gate-nobody-has-written-yet.example/abc")


def test_gaterush_routes_to_a_handler_that_does_not_reapprove_oauth():
    """Approving gaterush's SoundCloud popup does not unlock its gate — a run approved it
    on seven consecutive turns and the download stayed locked. Without this, every turn
    re-grants an account-wide authorization for nothing.
    """
    from soundcloud_dl.gate_handlers import get_handler_for_url

    handler = get_handler_for_url("https://gaterush.me/GiMVei")
    assert handler.gate_slug == "gaterush_jev"
    assert handler.auto_approve_oauth is False
