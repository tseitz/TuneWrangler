"""SoundCloud's own download button, and why a decline has to say so."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl import soundcloud_page


@pytest.fixture(autouse=True)
def _no_real_page(monkeypatch):
    """Stub the page-render wait and ad blocking; both need a live browser."""
    monkeypatch.setattr(
        "soundcloud_dl.soundcloud_actions._wait_for_actions", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("soundcloud_dl.soundcloud_actions.block_ads", AsyncMock(return_value=None))
    monkeypatch.setattr(soundcloud_page, "random_delay", AsyncMock(return_value=None))


def _page(*, inline_download=False, more=False, menu_download=False) -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.route = AsyncMock()

    dl = MagicMock()
    dl.click = AsyncMock()

    async def query_selector(sel):
        if sel == "button.sc-button-download":
            return dl if inline_download else None
        if sel == "button.sc-button-more":
            if not more:
                return None
            btn = MagicMock()
            btn.click = AsyncMock()
            return btn
        return None

    async def wait_for_selector(sel, **_kw):
        if sel == "button.sc-button-download" and menu_download:
            return dl
        msg = "timeout"
        raise TimeoutError(msg)

    page.query_selector = query_selector
    page.wait_for_selector = wait_for_selector
    page._dl_btn = dl
    return page


def _context(page) -> MagicMock:
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)
    return ctx


@pytest.fixture
def _saving(monkeypatch):
    """Make expect_download succeed, so the test is about finding the button."""

    def _install(page):
        download = MagicMock()
        download.suggested_filename = "track.wav"
        download.save_as = AsyncMock()

        class _Ctx:
            async def __aenter__(self):
                return MagicMock(value=_await(download))

            async def __aexit__(self, *_a):
                return False

        def _await(v):
            async def _get():
                return v

            return _get()

        page.expect_download = lambda **_kw: _Ctx()
        return download

    return _install


@pytest.mark.asyncio
async def test_an_inline_download_button_is_taken_without_the_menu(_saving, tmp_path, monkeypatch):
    """The button sits in the action bar when the artist allows the download. Requiring
    the '...' menu first meant a track with the button right there was declined whenever
    the menu was absent — and the caller turns that into NO_GATE.
    """
    page = _page(inline_download=True, more=False)
    _saving(page)
    ok = await soundcloud_page.try_native_sc_download(_context(page), "u", tmp_path, "A - B")
    assert ok is True


@pytest.mark.asyncio
async def test_the_menu_is_still_used_when_there_is_no_inline_button(_saving, tmp_path):
    page = _page(inline_download=False, more=True, menu_download=True)
    _saving(page)
    ok = await soundcloud_page.try_native_sc_download(_context(page), "u", tmp_path, "A - B")
    assert ok is True


@pytest.mark.asyncio
async def test_a_page_with_no_action_bar_says_why(tmp_path, caplog):
    """The decline that used to be silent. 'Not rendered yet' and 'no download exists'
    reached the caller identically, and it writes the track off as NO_GATE.
    """
    page = _page(inline_download=False, more=False)
    with caplog.at_level(logging.INFO):
        ok = await soundcloud_page.try_native_sc_download(_context(page), "u", tmp_path)
    assert ok is False
    assert any("No native download" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_a_menu_without_a_download_entry_says_why(tmp_path, caplog):
    page = _page(inline_download=False, more=True, menu_download=False)
    with caplog.at_level(logging.INFO):
        ok = await soundcloud_page.try_native_sc_download(_context(page), "u", tmp_path)
    assert ok is False
    assert any("No native download" in r.getMessage() for r in caplog.records)
