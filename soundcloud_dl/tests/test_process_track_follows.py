"""When the playlist path hands follows back, and when it must not."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl import main as main_mod
from soundcloud_dl.gate_handlers.base import GateHandler, StuckGate
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
    cleaned: list[str] = []

    async def _release(actions):
        seen.append(actions)

    async def _clean_up(_context, track_url, *, apply):
        assert apply is True
        cleaned.append(track_url)

    monkeypatch.setattr(main_mod, "release_follows_taken", _release)
    monkeypatch.setattr(main_mod.pending_follows, "hold", held.append)
    monkeypatch.setattr(main_mod, "keep_one_comment", _clean_up)

    async def _act(_context, _url, *, comment_text, into):
        # Writes into the caller's dict rather than returning one — the contract that
        # keeps a follow recoverable when a later action raises.
        into.update(ACTIONS)
        return into

    monkeypatch.setattr(main_mod, "do_soundcloud_actions", _act)
    monkeypatch.setattr(main_mod, "judge_track_filename", AsyncMock(return_value="A - B"))
    monkeypatch.setattr(main_mod, "try_native_sc_download", AsyncMock(return_value=False))
    monkeypatch.setattr(main_mod, "get_gate_url", AsyncMock(return_value="https://gate.io/x"))
    monkeypatch.setattr(main_mod, "skip_reason", lambda _u: None)
    monkeypatch.setattr(main_mod, "_save_debug_artifacts", AsyncMock())
    monkeypatch.setattr(main_mod, "DOWNLOAD_DIR", None)
    return seen, held, cleaned


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
    seen, held, cleaned = released

    async def _run(_self, _page):
        return {}

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "manual_review"
    assert seen == [ACTIONS]
    assert held == []
    assert cleaned == [TRACK.url]


@pytest.mark.asyncio
async def test_a_captcha_keeps_the_follows(released, monkeypatch):
    """The tab is left open for a person to finish and the gate is still checking for
    them. Taking them back mid-gate is what makes the manual followup fail.
    """
    seen, held, cleaned = released

    async def _run(_self, _page):
        raise CaptchaEncountered(CaptchaKind.HCAPTCHA, "g")

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "captcha_pending"
    assert seen == []
    # Held, not forgotten: a re-run cannot re-derive these, so they go on the ledger.
    assert held == [ACTIONS]
    # The tab is left for a person and the gate's own comment lands only once they
    # finish — the --dedupe-comments sweep is what catches this track, not here.
    assert cleaned == []


@pytest.mark.asyncio
async def test_a_login_wall_keeps_the_follows(released, monkeypatch):
    seen, held, cleaned = released

    async def _run(_self, _page):
        raise LoginWallEncountered("https://soundcloud.com/signin", "signed out", "g")

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "login_required"
    assert seen == []
    assert held == [ACTIONS]
    assert cleaned == []


@pytest.mark.asyncio
async def test_a_crashing_gate_still_hands_the_follows_back(released, monkeypatch):
    """The gate spent them and produced nothing; nobody is coming back to that tab."""
    seen, held, cleaned = released

    async def _run(_self, _page):
        msg = "boom"
        raise RuntimeError(msg)

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "failed"
    assert seen == [ACTIONS]
    assert held == []
    assert cleaned == [TRACK.url]


@pytest.mark.asyncio
async def test_a_stuck_gate_still_runs_the_comment_cleanup(released, monkeypatch):
    """StuckGate is not caught by `except Exception` above it — the clean-up must not
    depend on which exception type ended the gate.
    """
    _seen, _held, cleaned = released

    async def _run(_self, _page):
        raise StuckGate("g", "step_3")

    _handler_that(_run, monkeypatch)
    outcome = await main_mod._process_track(_context(), TRACK, sc_actions=True)
    assert outcome.state == "manual_review"
    assert cleaned == [TRACK.url]


@pytest.mark.asyncio
async def test_without_sc_actions_there_is_nothing_to_hand_back(released, monkeypatch):
    seen, _held, cleaned = released

    async def _run(_self, _page):
        return {}

    _handler_that(_run, monkeypatch)
    await main_mod._process_track(_context(), TRACK, sc_actions=False)
    assert seen == [{}]
    # No sc_actions and the gate has no comment box in this fake, but the gate still ran
    # — the clean-up is gated on that, not on sc_actions.
    assert cleaned == [TRACK.url]


@pytest.mark.asyncio
async def test_the_judged_filename_is_recorded_with_what_soundcloud_credits(
    released, monkeypatch
):
    import json

    from soundcloud_dl import track_index

    async def _run(_self, _page):
        return {}

    _handler_that(_run, monkeypatch)
    track = TrackItem(
        url="https://soundcloud.com/a/b", title="A - B", artist="A", metadata_artist="A, C"
    )
    await main_mod._process_track(_context(), track)
    index = json.loads(track_index.get_track_index_file().read_text(encoding="utf-8"))
    assert index["A - B"]["metadata_artist"] == "A, C"
    assert index["A - B"]["url"] == track.url
