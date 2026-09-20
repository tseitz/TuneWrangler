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

from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler


class JevHandler(JudgmentGateHandler):
    """JudgmentGateHandler under its own name, so a run is not filed as another gate's."""

    gate_slug: str = "jev"

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        kwargs.setdefault("config", {"gate": self.gate_slug, "steps": []})
        super().__init__(**kwargs)


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


class InfluencePlannerHandler(JevHandler):
    gate_slug = "influenceplanner_jev"

    # This gate opens by asking SoundCloud for authType SUPERFAN_CONNECT: a broad,
    # non-expiring grant on the account, not the per-download connect the other gates use.
    # That is the operator's to give, once, by hand. Clicking it automatically re-granted
    # it on thirteen consecutive turns and never unlocked the gate.
    auto_approve_oauth = False
