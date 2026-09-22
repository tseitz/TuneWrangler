"""Every registered gate handler can actually be built.

FanLinkHandler pointed config_path at a fanlink.yaml that has never existed. The base
class opens that file in __init__, so every fanlink track died on FileNotFoundError
before its gate was even fetched — and nothing caught it, because no test had ever
constructed the handler. Routing to a handler that cannot be instantiated is the failure
this file exists to stop.
"""

from __future__ import annotations

import pytest

from soundcloud_dl.gate_handlers import get_handler_for_url

#: One URL per branch of get_handler_for_url. Kept as URLs rather than classes so a new
#: handler is only covered once it is routable, which is the state that matters.
GATE_URLS = [
    "https://hypeddit.com/artist/track",
    "https://toneden.io/artist/post/track",
    "https://fanlink.tv/abc123",
    "https://fanlink.to/abc123",
    "https://pumpyoursound.com/f/abc",
    "https://followeb.de/abc",
    "https://droploud.com/d/abc",
    "https://gaterush.com/abc",
    "https://gate.influenceplanner.com/abc",
    "https://ipln.io/abc",
]


@pytest.mark.parametrize("url", GATE_URLS)
def test_the_handler_for_a_gate_can_be_constructed(url):
    handler_cls = get_handler_for_url(url)
    # No config= passed, exactly as main.py builds these: a handler that needs a file on
    # disk has to have one, and a handler that does not must not ask for it.
    handler = handler_cls(template_vars={"email": "someone@example.com"})
    assert handler.gate_name


def test_a_handler_that_owns_its_flow_needs_no_yaml_on_disk():
    from soundcloud_dl.gate_handlers.fanlink import FanLinkHandler

    handler = FanLinkHandler()
    assert handler.gate_name == "fanlink"
    assert handler.steps == []
