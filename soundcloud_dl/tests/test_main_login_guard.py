"""The signed-out guard in main._ensure_logged_in."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl.main import SoundCloudLoginRequiredError, _ensure_logged_in


def _context(*, signed_out: bool) -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.query_selector = AsyncMock(return_value=MagicMock() if signed_out else None)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    return context


def _never_asks(monkeypatch, why: str) -> None:
    def _never(*_args, **_kwargs):
        raise AssertionError(why)

    monkeypatch.setattr("builtins.input", _never)


@pytest.mark.asyncio
async def test_signed_out_and_unattended_raises_instead_of_waiting(monkeypatch):
    """An unattended headless batch has nobody at the terminal and no window to log in
    to. Waiting on stdin there blocks until the run is killed, and a blocked run looks
    exactly like a working one for as long as it is left alone.
    """
    monkeypatch.setattr("soundcloud_dl.main.sys.stdin.isatty", lambda: True)
    _never_asks(monkeypatch, "stdin must not be read when there is no window to log into")

    with pytest.raises(SoundCloudLoginRequiredError):
        await _ensure_logged_in(_context(signed_out=True), headed=False)


@pytest.mark.asyncio
async def test_a_window_is_not_enough_without_a_terminal(monkeypatch):
    """Nobody is there to press Enter, so the window cannot be acted on either."""
    monkeypatch.setattr("soundcloud_dl.main.sys.stdin.isatty", lambda: False)
    _never_asks(monkeypatch, "stdin must not be read when nothing is attached to it")

    with pytest.raises(SoundCloudLoginRequiredError):
        await _ensure_logged_in(_context(signed_out=True), headed=True)


@pytest.mark.asyncio
async def test_signed_out_with_a_window_and_a_terminal_still_asks(monkeypatch):
    """The interactive path is the reason the prompt exists — keep it.

    headed is passed in rather than read off config because --pause forces a window on
    regardless of TUNEWRANGLER_SC_HEADED; a guard reading the constant refuses to ask
    even though there is a window right there to log into.
    """
    monkeypatch.setattr("soundcloud_dl.main.sys.stdin.isatty", lambda: True)
    asked = []
    monkeypatch.setattr("builtins.input", lambda *_: asked.append(True) or "")

    await _ensure_logged_in(_context(signed_out=True), headed=True)
    assert asked == [True]


@pytest.mark.asyncio
async def test_signed_in_never_asks(monkeypatch):
    _never_asks(monkeypatch, "a signed-in profile has nothing to ask about")
    await _ensure_logged_in(_context(signed_out=False), headed=False)
