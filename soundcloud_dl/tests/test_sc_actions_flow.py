"""Follow accounting: what a run hands back, and when it must not."""

from unittest.mock import AsyncMock

import pytest

from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, CaptchaKind
from soundcloud_dl.sc_actions_flow import (
    do_soundcloud_actions,
    follows_to_release,
    release_follows_taken,
    requirement_follower,
)
from soundcloud_dl.soundcloud_actions import MAX_GATE_FOLLOWS, ActionResult


def _follow(subject_id: int | None, *, changed: bool = True) -> ActionResult:
    return ActionResult("follow", ok=True, detail="", changed=changed, subject_id=subject_id)


def test_only_follows_this_run_took_are_released():
    """A follow the user already had is theirs. `changed` is the only thing that
    distinguishes it from one this run is responsible for.
    """
    actions = {
        "follow:a": _follow(1),
        "follow:b": _follow(2, changed=False),
        "follow:c": _follow(3),
    }
    assert follows_to_release(actions) == [1, 3]


def test_non_follow_actions_are_never_released():
    actions = {
        "like": ActionResult("like", ok=True, detail="", changed=True, subject_id=9),
        "repost": ActionResult("repost", ok=True, detail="", changed=True, subject_id=9),
    }
    assert follows_to_release(actions) == []


def test_a_follow_with_no_subject_id_is_skipped():
    """Without an id there is nothing to unfollow, and guessing would hand back
    somebody else's follow.
    """
    assert follows_to_release({"follow:x": _follow(None)}) == []


@pytest.mark.asyncio
async def test_releasing_nothing_does_not_call_the_api(monkeypatch):
    called = AsyncMock()
    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.release_follows", called)
    await release_follows_taken({})
    called.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failing_release_is_reported_not_raised(monkeypatch):
    """The download has already succeeded by this point; failing to tidy up must not
    undo it by turning the track into a failure.
    """

    async def _boom(_ids):
        msg = "network"
        raise RuntimeError(msg)

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.release_follows", _boom)
    await release_follows_taken({"follow:a": _follow(1)})


@pytest.mark.asyncio
async def test_mid_run_follows_join_the_release_set(monkeypatch):
    """A gate names profiles partway through. Those follows are the run's too, so they
    have to land in the same dict the release step reads.
    """
    actions: dict[str, ActionResult] = {}
    monkeypatch.setattr(
        "soundcloud_dl.gate_handlers.gate_requirements.soundcloud_handles",
        lambda _blocks: ["newartist"],
    )

    async def _follow_handles(handles):
        return {f"follow:{h}": _follow(77) for h in handles}

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.follow_handles", _follow_handles)

    await requirement_follower(actions)(["follow @newartist"])
    assert follows_to_release(actions) == [77]


@pytest.mark.asyncio
async def test_a_profile_already_followed_this_run_is_not_followed_twice(monkeypatch):
    actions: dict[str, ActionResult] = {"follow:known": _follow(5)}
    monkeypatch.setattr(
        "soundcloud_dl.gate_handlers.gate_requirements.soundcloud_handles",
        lambda _blocks: ["known"],
    )

    async def _never(_handles):
        msg = "already followed this run"
        raise AssertionError(msg)

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.follow_handles", _never)
    await requirement_follower(actions)(["follow @known"])
    assert follows_to_release(actions) == [5]


@pytest.mark.asyncio
async def test_a_follow_survives_a_later_action_blowing_up(monkeypatch):
    """perform() takes the follow first and like/repost/comment can each raise. A dict
    that only exists as a return value takes the follow's record with it when one does,
    leaving a real follow on the account that nothing can give back.
    """

    async def _perform(_ctx, _url, *, comment_text, into):
        into["follow"] = _follow(42)
        msg = "timeout reading the like back"
        raise RuntimeError(msg)

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.perform", _perform)
    results = await do_soundcloud_actions(None, "u", comment_text="c")
    assert follows_to_release(results) == [42]


@pytest.mark.asyncio
async def test_a_captcha_mid_actions_also_keeps_what_landed(monkeypatch):
    async def _perform(_ctx, _url, *, comment_text, into):
        into["follow"] = _follow(7)
        raise CaptchaEncountered(CaptchaKind.HCAPTCHA, "sc")

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.perform", _perform)
    results = await do_soundcloud_actions(None, "u", comment_text="c")
    assert follows_to_release(results) == [7]


@pytest.mark.asyncio
async def test_the_gate_follow_budget_is_for_the_run_not_the_call(monkeypatch):
    """MAX_GATE_FOLLOWS caps one call, and a gate is asked for its requirements once per
    batch of fresh blocks — so a per-call cap let one page spend it many times over.
    """
    actions: dict[str, ActionResult] = {}
    handed: list[list[str]] = []

    monkeypatch.setattr(
        "soundcloud_dl.gate_handlers.gate_requirements.soundcloud_handles",
        lambda blocks: list(blocks),
    )

    async def _follow_handles(handles):
        handed.append(list(handles))
        return {f"follow:{h}": _follow(hash(h) % 1000) for h in handles}

    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.follow_handles", _follow_handles)

    follower = requirement_follower(actions)
    await follower([f"a{i}" for i in range(4)])
    await follower([f"b{i}" for i in range(4)])
    await follower([f"c{i}" for i in range(4)])

    assert sum(len(batch) for batch in handed) == MAX_GATE_FOLLOWS
