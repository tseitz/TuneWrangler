"""Registry entries for gates that are driven by judgment rather than by a step list.

A YAML handler encodes one gate's flow as an ordered set of selectors. That works where the
flow is fixed, and does not where it is not: droploud states its terms on step 2, redirects
/gate/<id> to /track/<id> on load, and serves the file from its own success page with
nothing clicked. These hosts get JudgmentGateHandler instead, which decides each turn from
what is on the page.

Only the gate name differs per host, and only so a run is legible in the log — the handler
reads everything else off the page.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler


class JevHandler(JudgmentGateHandler):
    """JudgmentGateHandler under its own name, so a run is not filed as another gate's."""

    gate_slug: str = "jev"

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        kwargs.setdefault("config", {"gate": self.gate_slug, "steps": []})
        super().__init__(**kwargs)


def gate_name_for(url: str) -> str:
    """Name a judgment run after the gate's host, so a droploud run is not filed as hypeddit."""
    host = urlparse(url).netloc.removeprefix("www.")
    return f"{host.split('.')[0] or 'gate'}_jev"


def judgment_handler_for(url: str) -> type[JevHandler]:
    """A JevHandler for a host nothing is registered for.

    A step list has to be written per host before that host works at all; judgment reads
    the page, so an unrecognised gate is worth attempting rather than retiring. Retiring
    it is what the alternative means — `unsupported` is a resume skip state, so the track
    is never offered again without --retry-unsupported.

    Built per host rather than returning JevHandler itself so the log and the run
    artifacts name the gate, the same as every registered judgment handler.
    """
    slug = gate_name_for(url)
    # A host is allowed characters a class name is not, and type() takes the string as
    # given — so "some-new-gate.io" would name a class nothing can be written down as.
    name = "".join(c for c in slug.title() if c.isalnum()) + "Handler"
    return type(name, (JevHandler,), {"gate_slug": slug})


class HypedditJevHandler(JevHandler):
    """Hypeddit, driven by judgment rather than by hypeddit.yaml's step list.

    The step list cannot see where a control is. Hypeddit enables #gateDownloadButton by
    class from the first turn while parking it on a carousel slide that has not arrived —
    box 0x0, offsetParent null — and a selector that only tests classes clicks it there,
    which does nothing and leaves the run with no file. Judgment reads the geometry, skips
    the button until its slide arrives, and advances the carousel in between.
    """

    gate_slug = "hypeddit_jev"


class DroploudHandler(JevHandler):
    gate_slug = "droploud_jev"


class GaterushHandler(JevHandler):
    """Gaterush, whose Connect SoundCloud is not satisfied by approving the popup.

    Its gate is one card: a comment box, a Connect SoundCloud button, and a padlocked
    Download. Clicking Connect opens the SoundCloud consent popup and approving it changes
    nothing on the gate — a run approved it on seven consecutive turns and the download
    stayed LOCKED, the same shape InfluencePlanner showed on thirteen. Re-granting an
    account-wide authorization once per turn is worth stopping whether or not the grant is
    the reason the gate will not open.
    """

    gate_slug = "gaterush_jev"
    auto_approve_oauth = False


class InfluencePlannerHandler(JevHandler):
    gate_slug = "influenceplanner_jev"

    # This gate opens by asking SoundCloud for authType SUPERFAN_CONNECT: a broad,
    # non-expiring grant on the account, not the per-download connect the other gates use.
    # That is the operator's to give, once, by hand. Clicking it automatically re-granted
    # it on thirteen consecutive turns and never unlocked the gate.
    auto_approve_oauth = False
