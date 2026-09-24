"""SoundCloud's v2 track page, whose body is a same-origin iframe, in a real browser."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from soundcloud_dl.inspect_gate import _snapshot
from soundcloud_dl.soundcloud_page import _poll_gate_sc_url, track_content_frame

pytestmark = pytest.mark.requires_browser

_TRACK = "https://soundcloud.com/artist/track"
_FRAME = "https://soundcloud.com/n/artist/track?v2_layout=true&embedded=crossfade"
_V2_TOP = f'<html><body><button>Play</button><iframe class="webiIframe webiIframeV2Layout" src="{_FRAME}"></iframe></body></html>'
_V2_BODY = """<html><body><h1>Track</h1><button aria-label="Share">s</button>
<a href="https://gate.sc/?url=https%3A%2F%2Fartist.bandcamp.com%2Ftrack%2Fx&token=a">bc</a>
<a id="card" href="https://gate.sc?url=https%3A%2F%2Fpl8list.com%2Fa%2Fb&token=b">FREE DOWNLOAD</a>
</body></html>"""
_LEGACY = '<html><body><div class="soundActions"><button>Like</button></div></body></html>'
_EMPTY = "<html><body><button>Play</button></body></html>"


async def _open(top: str, fn):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()

        async def serve(route):
            html = _V2_BODY if "/n/" in route.request.url else top
            await route.fulfill(status=200, content_type="text/html", body=html)

        await page.route("https://soundcloud.com/**", serve)
        await page.goto(_TRACK)
        await page.wait_for_timeout(300)
        try:
            return await fn(page)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_the_v2_frame_is_the_track_content() -> None:
    url = await _open(_V2_TOP, lambda p: _frame_url(p))
    assert url == _FRAME


async def _frame_url(page):
    frame = await track_content_frame(page)
    return frame.url if frame is not None else None


@pytest.mark.asyncio
async def test_the_legacy_layout_is_the_main_frame() -> None:
    assert await _open(_LEGACY, _frame_url) == _TRACK


@pytest.mark.asyncio
async def test_nothing_rendered_is_none() -> None:
    assert await _open(_EMPTY, _frame_url) is None


@pytest.mark.asyncio
async def test_the_gate_poll_finds_the_v2_card_over_an_earlier_bandcamp_link() -> None:
    gate = await _open(_V2_TOP, lambda p: _poll_gate_sc_url(p, timeout_ms=2_000))
    assert gate == "https://pl8list.com/a/b"


@pytest.mark.asyncio
async def test_inspect_sees_controls_inside_the_layout_frame() -> None:
    snapshot = await _open(_V2_TOP, _snapshot)
    in_frame = [el for key, el in snapshot.items() if key.startswith("soundcloud.com/n/")]
    assert any(el["id"] == "card" for el in in_frame)


@pytest.mark.asyncio
async def test_get_gate_url_reads_a_v2_track_page(monkeypatch) -> None:
    """End to end: the readiness wait accepts the frame, and the gate is found in it —
    SIMON SAYS's path, which reported "SoundCloud served no track content"."""
    from soundcloud_dl import soundcloud_actions  # noqa: PLC0415
    from soundcloud_dl.soundcloud_page import get_gate_url  # noqa: PLC0415

    monkeypatch.setattr(soundcloud_actions, "PAGE_LOAD_WAIT_SECONDS", 0)
    monkeypatch.setattr(soundcloud_actions, "_CONTENT_TIMEOUT_MS", 3_000)

    async def no_ad_block(_page):
        # Its page-level route outranks the fixture's and passes requests to the network.
        return None

    monkeypatch.setattr(soundcloud_actions, "block_ads", no_ad_block)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context()

        async def serve(route):
            html = _V2_BODY if "/n/" in route.request.url else _V2_TOP
            await route.fulfill(status=200, content_type="text/html", body=html)

        await context.route("https://soundcloud.com/**", serve)
        try:
            assert await get_gate_url(context, _TRACK) == "https://pl8list.com/a/b"
        finally:
            await browser.close()
