"""`covered` in the DOM snapshot, measured in a real browser.

A dialog opened over pl8list's page left the page's own comment box offered to the model,
which filled it instead of the dialog's field and stalled on a disabled continue button.
"""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from soundcloud_dl.gate_handlers.dom_snapshot import snapshot_elements

pytestmark = pytest.mark.requires_browser

_PAGE = """
<!doctype html><html><body style="margin:0">
  <button id="under" style="position:absolute;top:20px;left:20px">page button</button>
  <label id="wrap" style="position:absolute;top:120px;left:20px">
    <input type="checkbox" style="opacity:0;position:absolute"><span>styled box</span>
  </label>
  <button id="through" style="position:absolute;top:220px;left:20px">under a pass-through</button>
  <div style="position:absolute;top:210px;left:0;width:400px;height:60px;pointer-events:none"></div>
  <div id="dialog" style="position:fixed;top:0;left:0;width:400px;height:80px;background:#000">
    <input id="field" placeholder="share your thoughts">
  </div>
</body></html>
"""


async def _covered_by_id() -> dict[str, bool]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(_PAGE)
        els = await snapshot_elements(page)
        await browser.close()
    return {el["id"]: el["covered"] for el in els if el["id"]}


@pytest.mark.asyncio
async def test_a_control_under_a_dialog_is_covered_and_the_dialogs_own_is_not() -> None:
    covered = await _covered_by_id()
    assert covered["under"] is True
    assert covered["field"] is False


@pytest.mark.asyncio
async def test_a_label_over_its_own_input_is_not_covered() -> None:
    assert (await _covered_by_id())["wrap"] is False


@pytest.mark.asyncio
async def test_an_overlay_that_clicks_pass_through_does_not_cover() -> None:
    assert (await _covered_by_id())["through"] is False


_LANDMARKS = """
<!doctype html><html><body>
  <header><a id="site_nav" href="/">home</a></header>
  <article><footer><button id="card_download">download</button></footer></article>
  <dialog open><form><footer><button id="dialog_continue">continue</button></footer></form></dialog>
  <footer><a id="site_terms" href="/terms">terms</a></footer>
</body></html>
"""


@pytest.mark.asyncio
async def test_only_a_page_level_header_or_footer_is_site_chrome() -> None:
    """pl8list puts its dialog's continue button in the dialog's own <footer>. Treating
    that as site furniture withheld the one control that finishes the gate."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(_LANDMARKS)
        chrome = {el["id"]: el["chrome"] for el in await snapshot_elements(page) if el["id"]}
        await browser.close()
    assert chrome == {
        "site_nav": True,
        "card_download": False,
        "dialog_continue": False,
        "site_terms": True,
    }
