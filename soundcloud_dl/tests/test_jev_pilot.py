"""Which URL a --jev run names its download from."""

from __future__ import annotations

import pytest

from soundcloud_dl import jev_pilot

GATE = "https://hypeddit.com/fossils/pullup"
TRACK = "https://soundcloud.com/nohypemusicofficial/fossils-pull-up"


@pytest.fixture
def named(monkeypatch) -> list[str]:
    calls: list[str] = []

    async def fake(track_url: str) -> str:
        calls.append(track_url)
        return "FOSSILS - PULL UP"

    monkeypatch.setattr(jev_pilot, "name_and_record", fake)
    return calls


@pytest.mark.asyncio
async def test_a_bare_gate_url_is_named_from_the_track_it_was_given(named):
    assert await jev_pilot._name_download(GATE, TRACK) == "FOSSILS - PULL UP"
    assert named == [TRACK]


@pytest.mark.asyncio
async def test_a_track_url_names_itself(named):
    await jev_pilot._name_download(TRACK, None)
    assert named == [TRACK]


@pytest.mark.asyncio
async def test_a_bare_gate_url_alone_warns_that_the_download_is_unlinked(named, caplog):
    assert await jev_pilot._name_download(GATE, None) is None
    assert named == []
    assert "--track" in caplog.text
