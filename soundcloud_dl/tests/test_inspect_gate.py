"""Unit tests for the manual-unlock inspector (inspect_gate.py)."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl import inspect_gate as ig


def el(key: str, **over: object) -> dict:
    base = {
        "key": key,
        "tag": "button",
        "text": "Download",
        "cls": "",
        "href": "",
        "disabled": False,
        "visible": True,
        "checked": False,
    }
    return base | over


def page_yielding(frames: list[list[dict]], monkeypatch) -> MagicMock:
    """A Page whose successive snapshots come from `frames`, the last frame repeating."""
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)
    remaining = list(frames)

    async def next_frame(_page):
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    monkeypatch.setattr(ig, "snapshot_elements", next_frame)
    return page


# Both spellings of the InfluencePlanner skeleton, which is what made this measurable.
_SKELETON = "text-transparent [&>svg]:opacity-0 opacity-50 pointer-events-none relative"
_HYDRATED = "text-white bg-primary cursor-pointer"


@pytest.mark.asyncio
async def test_the_snapshot_waits_for_the_dom_to_stop_changing(monkeypatch):
    """The live miss: a client-rendered gate serves a skeleton whose controls carry the
    same not-ready classes a locked control does. Snapshotting at domcontentloaded
    measured hydration and reported it as the unlock."""
    page = page_yielding([[el("b", cls=_SKELETON)], [el("b", cls=_HYDRATED)]], monkeypatch)
    settled = await ig._settled_snapshot(page, "before")
    assert settled["b"]["cls"] == _HYDRATED


@pytest.mark.asyncio
async def test_an_empty_page_is_not_a_settled_page(monkeypatch):
    """Two agreeing empty polls mean nothing has rendered yet, not that the page is ready.

    Settling there is the same bug one edge earlier: every control then shows up as NEW.
    """
    page = page_yielding([[], [], [el("b", cls=_HYDRATED)]], monkeypatch)
    settled = await ig._settled_snapshot(page, "before")
    assert list(settled) == ["b"]


@pytest.mark.asyncio
async def test_a_snapshot_that_throws_is_retried_not_fatal(monkeypatch):
    """Completing a gate navigates, which destroys the execution context mid-poll."""
    calls = {"n": 0}

    async def flaky(_page):
        calls["n"] += 1
        if calls["n"] == 1:
            msg = "Execution context was destroyed"
            raise RuntimeError(msg)
        return [el("b", cls=_HYDRATED)]

    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    monkeypatch.setattr(ig, "snapshot_elements", flaky)
    settled = await ig._settled_snapshot(page, "after")
    assert settled["b"]["cls"] == _HYDRATED


@pytest.mark.asyncio
async def test_a_page_that_never_settles_still_returns_and_warns(monkeypatch, caplog):
    """Never hang on an animated page — a noisy snapshot beats no snapshot at all."""
    flip = [[el("b", cls=_SKELETON)], [el("b", cls=_HYDRATED)]]
    calls = {"n": 0}

    async def never_same(_page):
        calls["n"] += 1
        return flip[calls["n"] % 2]

    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    monkeypatch.setattr(ig, "snapshot_elements", never_same)
    with caplog.at_level("WARNING"):
        settled = await ig._settled_snapshot(page, "before")
    assert settled
    assert "still changing" in caplog.text


@pytest.mark.asyncio
async def test_the_button_is_added_under_the_id_the_remove_script_targets():
    """Our own injected button is an element; left in place it is a NEW row in every diff.

    The add and remove scripts have to name the same id, and nothing else checks that —
    a mismatch just leaves the button in place, and the noise reads as a gate change.
    """
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=False)
    await ig._poll_done_button(page)

    add_args = page.evaluate.await_args_list[1].args
    assert add_args[0] is ig._ADD_DONE_BUTTON_JS
    assert add_args[1][0] == ig._DONE_BUTTON_ID
    assert ig._DONE_BUTTON_ID in ig._REMOVE_DONE_BUTTON_JS


@pytest.mark.asyncio
async def test_the_button_is_re_added_on_every_poll_until_it_is_clicked():
    """A navigation wipes it, so placement is repeated rather than done once."""
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=False)
    assert await ig._poll_done_button(page) is False
    assert page.evaluate.await_count == 2


@pytest.mark.asyncio
async def test_the_click_is_what_ends_the_wait_without_a_tty(monkeypatch):
    """The crash this replaces: no stdin meant a bare EOFError, after the before-snapshot
    had already been spent."""
    monkeypatch.setattr(ig, "_stdin_is_a_terminal", lambda: False)
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    clicks = iter([False, False, True])
    page.evaluate = AsyncMock(side_effect=lambda *_a, **_k: next(clicks, True))

    await ig._wait_for_done(page)  # returns rather than raising


@pytest.mark.asyncio
async def test_a_button_that_can_never_be_placed_is_reported(monkeypatch, caplog):
    """Without this the loop stalls in silence, and with no terminal there is no way out."""
    monkeypatch.setattr(ig, "_stdin_is_a_terminal", lambda: False)
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    tries = {"n": 0}

    async def always_broken(*_a, **_k):
        tries["n"] += 1
        if tries["n"] > ig._DONE_STALL_WARN_AFTER:
            return True  # let the test exit once the warning has had to fire
        msg = "no document.body"
        raise RuntimeError(msg)

    page.evaluate = always_broken
    with caplog.at_level("WARNING"):
        await ig._wait_for_done(page)
    assert "Cannot place the Done button" in caplog.text


def test_enter_is_never_read_when_stdin_is_not_a_terminal(monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    assert ig._stdin_is_a_terminal() is False
    assert ig._enter_pressed() is False


class FakeEmitter:
    """Just enough of Page/BrowserContext's .on() to fire events by hand."""

    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}

    def on(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, arg: object) -> None:
        for handler in self.handlers.get(event, []):
            handler(arg)


def fake_download(name: str = "track.wav", *, hang: bool = False) -> MagicMock:
    download = MagicMock()
    download.suggested_filename = name

    async def save_as(path: str) -> None:
        if hang:
            await asyncio.Event().wait()
        await asyncio.to_thread(Path(path).write_bytes, b"RIFF")

    download.save_as = save_as
    return download


@pytest.mark.asyncio
async def test_a_download_the_operator_starts_is_saved(tmp_path):
    """Playwright routes an attached browser's downloads into a temp dir it deletes on
    disconnect, so the file a person unlocked by hand vanished the moment they clicked Done.
    A gate is one-shot, and that download cannot be had again."""
    context, page = FakeEmitter(), FakeEmitter()
    saves = ig._keep_downloads(context, page, tmp_path)

    page.emit("download", fake_download("gate.wav"))
    popup = FakeEmitter()
    context.emit("page", popup)
    popup.emit("download", fake_download("popup.wav"))
    await ig._finish_saves(saves)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["gate.wav", "popup.wav"]


@pytest.mark.asyncio
async def test_a_download_still_transferring_is_reported_not_dropped(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(ig, "_SAVE_TIMEOUT_S", 0.01)
    context, page = FakeEmitter(), FakeEmitter()
    saves = ig._keep_downloads(context, page, tmp_path)

    page.emit("download", fake_download(hang=True))
    await ig._finish_saves(saves)

    assert "still transferring" in caplog.text


@pytest.mark.asyncio
async def test_a_download_never_overwrites_an_earlier_one(tmp_path):
    """Inspect keeps the gate's own filename, and artists reuse names like master.wav, so a
    second gate's file would silently replace the first track."""
    (tmp_path / "master.wav").write_bytes(b"first")
    context, page = FakeEmitter(), FakeEmitter()
    saves = ig._keep_downloads(context, page, tmp_path)

    page.emit("download", fake_download("master.wav"))
    await ig._finish_saves(saves)

    assert (tmp_path / "master.wav").read_bytes() == b"first"
    assert (tmp_path / "master (1).wav").exists()
