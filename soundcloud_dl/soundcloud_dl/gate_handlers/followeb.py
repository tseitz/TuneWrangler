"""Followeb gate handler."""

from __future__ import annotations

from pathlib import Path

from soundcloud_dl.gate_handlers.base import GateHandler


class FollowebHandler(GateHandler):
    config_path = Path(__file__).parent / "followeb.yaml"
