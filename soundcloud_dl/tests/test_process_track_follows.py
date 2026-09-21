"""When the playlist path hands follows back, and when it must not."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl import main as main_mod
from soundcloud_dl.gate_handlers.base import GateHandler
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, CaptchaKind
from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered
from soundcloud_dl.playlist import TrackItem
from soundcloud_dl.soundcloud_actions import ActionResult

TRACK = TrackItem(url="https://soundcloud.com/a/b", title="A - B", artist="A")
ACTIONS = {
    "follow:a": ActionResult("follow", ok=True, detail="", changed=True, subject_id=1),
}


@pytest.fixture
def released(monkeypatch):
    """Patch _process_track's collaborators; collect what gets handed back and what gets
    written to the ledger instead.
    """
    seen: list[dict] = []
    held: list[dict] = []

    async def _release(actions):
        seen.append(actions)

    monkeypatch.setattr(main_mod, "release_follows_taken", _release)
    monkeypatch.setattr(main_mod.pending_follows, "hold", held.append)

    async def _act(_context, _url, *, comment_text, into):
        # Writes into the caller's dict rather than returning one — the contract that
        # keeps a follow recoverable when a later action raises.
        into.update(ACTIONS)
        return into

    monkeypatch.setattr(main_mod, "do_soundcloud_actions", _act)
    monkeypatch.setattr(main_mod, "judge_track_filename", AsyncMock(return_value="A - B"))
    monkeypatch.setattr(main_mod, "try_native_sc_download", AsyncMock(return_value=False))
    monkeypatch.setattr(main_mod, "get_gate_url", AsyncMock(return_value="https://gate.io/x"))
    monkeypatch.setattr(main_mod, "is_url_blacklisted", lambda _u: False)
    monkeypatch.setattr(main_mod, "_save_debug_artifacts", AsyncMock())
    monkeypatch.setattr(main_mod, "DOWNLOAD_DIR", None)
    return seen, held


def _context() -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.url = "https://gate.io/x"
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    return context


def _handler_that(run, monkeypatch) -> None:
    """Register a non-judgment handler whose run() does whatever the test needs."""

    class _Fake(GateHandler):
        def __init__(self, **_kwargs):
            self.downloaded = False

    _Fake.run = run
    monkeypatch.setattr(main_mod, "get_handler_for_url", lambda _u: _Fake)


@pytest.mark.asyncio
async def test_a_finished_run_hands_its_follows_back(released, monkeypatch):
    seen, held = released
    async def _run(_self, _page):
        return {}

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "manual_review"
    assert seen == [ACTIONS]
    assert held == []


@pytest.mark.asyncio
async def test_a_captcha_keeps_the_follows(released, monkeypatch):
    """The tab is left open for a person to finish and the gate is still checking for
    them. Taking them back mid-gate is what makes the manual followup fail.
    """
    seen, held = released

    async def _run(_self, _page):
        raise CaptchaEncountered(CaptchaKind.HCAPTCHA, "g")

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "captcha_pending"
    assert seen == []
    # Held, not forgotten: a re-run cannot re-derive these, so they go on the ledger.
    assert held == [ACTIONS]


@pytest.mark.asyncio
async def test_a_login_wall_keeps_the_follows(released, monkeypatch):
    seen, held = released
    async def _run(_self, _page):
        raise LoginWallEncountered("https://soundcloud.com/signin", "signed out", "g")

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "login_required"
    assert seen == []
    assert held == [ACTIONS]


@pytest.mark.asyncio
async def test_a_crashing_gate_still_hands_the_follows_back(released, monkeypatch):
    """The gate spent them and produced nothing; nobody is coming back to that tab."""
    seen, held = released

    async def _run(_self, _page):
        msg = "boom"
        raise RuntimeError(msg)

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "failed"
    assert seen == [ACTIONS]
    assert held == []


@pytest.mark.asyncio
async def test_without_sc_actions_there_is_nothing_to_hand_back(released, monkeypatch):
    seen, _held = released
    async def _run(_self, _page):
        return {}

    _handler_that(_run, monkeypatch)
    await main_mod._process_track(_context(), TRACK, sc_actions=False)
    assert seen == [{}]
