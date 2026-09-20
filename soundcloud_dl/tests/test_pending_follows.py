"""The ledger of follows a run held instead of releasing."""

import json

import pytest

from soundcloud_dl import pending_follows
from soundcloud_dl.soundcloud_actions import ActionResult


@pytest.fixture(autouse=True)
def _ledger(tmp_path, monkeypatch):
    path = tmp_path / "pending_follows.json"
    monkeypatch.setattr(pending_follows, "get_pending_follows_file", lambda: path)
    return path


def _follow(subject_id: int, *, changed: bool = True) -> ActionResult:
    return ActionResult("follow", ok=True, detail="", changed=changed, subject_id=subject_id)


def test_holding_writes_the_ids_down(_ledger):
    """Without this the follow is unrecoverable: a re-run's set_following reports
    changed=False for a follow already in place, which is the signal the release step
    uses to tell a run's own follows from the user's.
    """
    pending_follows.hold({"follow:a": _follow(1), "follow:b": _follow(2)})
    assert json.loads(_ledger.read_text()) == [1, 2]


def test_holding_nothing_writes_nothing(_ledger):
    pending_follows.hold({"follow:a": _follow(9, changed=False)})
    assert not _ledger.exists()


def test_holds_accumulate_across_tracks(_ledger):
    pending_follows.hold({"follow:a": _follow(1)})
    pending_follows.hold({"follow:b": _follow(2)})
    assert json.loads(_ledger.read_text()) == [1, 2]


def test_the_same_id_is_not_recorded_twice(_ledger):
    pending_follows.hold({"follow:a": _follow(1)})
    pending_follows.hold({"follow:a": _follow(1)})
    assert json.loads(_ledger.read_text()) == [1]


@pytest.mark.asyncio
async def test_sweeping_releases_and_clears(_ledger, monkeypatch):
    _ledger.write_text("[1, 2]")
    asked = []

    async def _release(ids):
        asked.append(ids)
        return [ActionResult("unfollow", ok=True, detail="", subject_id=i) for i in ids]

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.release_follows", _release)
    await pending_follows.sweep()
    assert asked == [[1, 2]]
    assert json.loads(_ledger.read_text()) == []


@pytest.mark.asyncio
async def test_an_id_that_did_not_come_back_stays_on_the_ledger(_ledger, monkeypatch):
    """Clearing on a failed release would be the same silent leak the ledger closes."""
    _ledger.write_text("[1, 2]")

    async def _release(ids):
        return [
            ActionResult("unfollow", ok=i == 1, detail="", subject_id=i) for i in ids  # noqa: PLR2004
        ]

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.release_follows", _release)
    await pending_follows.sweep()
    assert json.loads(_ledger.read_text()) == [2]


@pytest.mark.asyncio
async def test_a_failing_sweep_keeps_the_whole_ledger(_ledger, monkeypatch):
    _ledger.write_text("[1, 2]")

    async def _boom(_ids):
        msg = "network"
        raise RuntimeError(msg)

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.release_follows", _boom)
    await pending_follows.sweep()
    assert json.loads(_ledger.read_text()) == [1, 2]


@pytest.mark.asyncio
async def test_an_empty_ledger_calls_nothing(_ledger, monkeypatch):
    async def _never(_ids):
        msg = "nothing to release"
        raise AssertionError(msg)

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.release_follows", _never)
    await pending_follows.sweep()


@pytest.mark.asyncio
async def test_a_corrupt_ledger_does_not_end_the_run(_ledger, monkeypatch):
    _ledger.write_text("{not json")

    async def _never(_ids):
        msg = "nothing readable to release"
        raise AssertionError(msg)

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.release_follows", _never)
    await pending_follows.sweep()
