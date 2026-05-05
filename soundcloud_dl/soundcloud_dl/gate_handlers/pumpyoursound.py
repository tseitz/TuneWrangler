"""PumpYourSound gate handler."""

from __future__ import annotations

from pathlib import Path

from soundcloud_dl.gate_handlers.base import GateHandler


class PumpYourSoundHandler(GateHandler):
    config_path = Path(__file__).parent / "pumpyoursound.yaml"
