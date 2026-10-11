"""Gate fixes from the 2026-10-09 nightly run: key collisions, covered controls, sign-in links,
loops, Drive folders, and backstaged's OAuth policy."""

from __future__ import annotations

import logging
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import async_playwright

from soundcloud_dl.gate_handlers import GateNotSupportedError, get_handler_for_url
from soundcloud_dl.gate_handlers import judgment as judgment_module
from soundcloud_dl.gate_handlers.base import StuckGate
from soundcloud_dl.gate_handlers.dom_snapshot import snapshot_elements
from soundcloud_dl.gate_handlers.jev import JevHandler, judgment_handler_for
from soundcloud_dl.gate_handlers.judgment import (
    JudgmentGateHandler,
    _is_sign_in,
    _repeating_cycle,
)
from soundcloud_dl.gate_handlers.oauth_popup import drive_folder_url

_DEBUG_HTML = Path(__file__).parents[2] / "logs/soundcloud_dl/debug"


def _handler() -> JudgmentGateHandler:
    return JudgmentGateHandler(config={"gate": "t", "steps": []}, template_vars={})


def _el(key: str, **over) -> dict:
    base = {
        "key": key,
        "id": "",
        "step": "",
        "tag": "button",
        "cls": "",
        "href": "",
        "type": "",
        "checked": False,
        "disabled": False,
        "visible": True,
        "chrome": False,
        "onscreen": True,
        "covered": False,
        "text": key,
        "placeholder": "",
        "name": "",
        "icons": [],
    }
    return base | over


# --- #3: an accordion header and its action share text ---------------------------------

_ACCORDION = """
<!doctype html><html><body>
  <form>
    <button type="button" aria-expanded="true" id="">Follow on Instagram</button>
    <div><button type="button">Follow on Instagram</button></div>
  </form>
</body></html>
"""


async def _snapshot_of(html: str, *, offline: bool = False) -> list[dict]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        if offline:
            await page.route("**/*", lambda route: route.abort())
        await page.set_content(html)
        els = await snapshot_elements(page)
        await browser.close()
    return els


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_a_disclosure_header_and_the_button_under_it_get_different_keys() -> None:
    els = [e for e in await _snapshot_of(_ACCORDION) if e["text"] == "Follow on Instagram"]
    assert len(els) == 2
    assert els[0]["key"] != els[1]["key"]


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_a_header_keeps_its_key_when_it_opens_or_closes() -> None:
    opened = await _snapshot_of(_ACCORDION)
    closed = await _snapshot_of(_ACCORDION.replace('aria-expanded="true"', 'aria-expanded="false"'))
    assert [e["key"] for e in opened] == [e["key"] for e in closed]


@pytest.mark.requires_browser
@pytest.mark.asyncio
@pytest.mark.skipif(
    not (_DEBUG_HTML / "BAAUER_-_HARLEM_SHAKE__TRINIST_BOOTLEG___FREE_DL_.html").exists(),
    reason="saved backstaged page is in the gitignored logs/ dir",
)
async def test_the_saved_backstaged_page_offers_its_real_follow_button() -> None:
    html = (_DEBUG_HTML / "BAAUER_-_HARLEM_SHAKE__TRINIST_BOOTLEG___FREE_DL_.html").read_text()
    els = await _snapshot_of(html, offline=True)
    follows = [e for e in els if e["text"] == "Follow on Instagram"]
    assert len(follows) == 2
    assert len({e["key"] for e in follows}) == 2


@pytest.mark.asyncio
async def test_a_collision_with_a_visible_control_is_logged_at_info(caplog) -> None:
    handler = _handler()
    page = MagicMock()
    page.evaluate = AsyncMock(
        return_value=[
            _el("dupe", text="Follow on Instagram"),
            _el("dupe", text="Follow on Instagram"),
        ]
    )
    with caplog.at_level(logging.INFO):
        await handler._snapshot(page)
    assert "share the key" in caplog.text
    assert "Follow on Instagram" in caplog.text


@pytest.mark.parametrize(
    "url", ["https://backstaged.io/d/harlemshake", "https://www.backstaged.io/d/x"]
)
def test_backstaged_approves_the_soundcloud_grant_once(url) -> None:
    cls = get_handler_for_url(url)
    assert issubclass(cls, JevHandler)
    assert cls.gate_slug == "backstaged_jev"
    assert cls.auto_approve_oauth is False
    assert cls.oauth_approve_once is True
    handler = cls(template_vars={})
    assert handler.take_oauth_approval() is True
    assert handler.take_oauth_approval() is False


@pytest.mark.parametrize(
    "url",
    [
        "https://backstaged.io/x?utm_source=hypeddit.com",
        "https://backstaged.io/x?ref=droploud.com&u=toneden.io",
        "https://backstaged.io./d/x",
        "https://BACKSTAGED.IO/d/x?from=pumpyoursound.com",
    ],
)
def test_a_substring_of_another_gate_in_a_backstaged_url_does_not_reroute_it(url) -> None:
    """The other hosts are matched by substring, so a query string naming one of them took
    the backstaged URL to a handler that approves every consent screen."""
    cls = get_handler_for_url(url)
    assert cls.gate_slug == "backstaged_jev"
    assert cls.auto_approve_oauth is False


def test_backstaged_is_matched_by_host_not_by_substring() -> None:
    with pytest.raises(GateNotSupportedError):
        get_handler_for_url("https://evil.example/?next=backstaged.io")


def test_an_unregistered_host_auto_approves_every_consent_screen() -> None:
    """What backstaged.io got before it was registered."""
    assert judgment_handler_for("https://backstaged.io/d/x").auto_approve_oauth is True


# --- #4: covered controls, sign-in links, unsure picks ---------------------------------

_BAR = """
<!doctype html><html><body style="margin:0;height:4000px">
  <div style="position:fixed;top:0;left:0;width:100%;height:80px;background:#000;z-index:10"></div>
  <button id="real" style="position:absolute;top:300px;left:20px">I did it</button>
</body></html>
"""


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_a_control_under_a_fixed_bar_is_scrolled_clear_of_it() -> None:
    handler = _handler()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(_BAR)
        await page.evaluate("window.scrollTo(0, 280)")
        before = await handler._snapshot(page)
        after = await handler._uncover_gate_controls(page, before)
        await browser.close()
    assert before["real"]["covered"] is True
    assert after["real"]["covered"] is False


@pytest.mark.asyncio
async def test_a_control_is_only_re_centred_once() -> None:
    handler = _handler()
    handle = MagicMock()
    handle.evaluate = AsyncMock()
    handler._find_element_by_key = AsyncMock(return_value=handle)
    handler._snapshot = AsyncMock(return_value={"x": _el("x", covered=True)})
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    snap = {"x": _el("x", covered=True)}

    await handler._uncover_gate_controls(page, snap)
    await handler._uncover_gate_controls(page, snap)

    handle.evaluate.assert_awaited_once()


@pytest.mark.parametrize(
    ("el", "expected"),
    [
        (_el("a", tag="a", text="Login to autocomplete matching steps"), True),
        (_el("b", text="Sign in"), True),
        (_el("c", tag="a", text="", href="/login?next=/track/1"), True),
        (_el("d", tag="a", text="Log in with Google"), False),
        (_el("d2", tag="a", text="Continue with Apple", href="/login/apple"), False),
        (_el("i", tag="a", text="", href="/auth/login"), True),
        (_el("j", tag="a", text="", href="/account/signin/"), True),
        (_el("k", tag="a", text="", href="/login?redirect=https://soundcloud.com/x"), True),
        (_el("l", tag="a", text="", href="https://secure.soundcloud.com/signin"), False),
        (_el("e", text="Login with SoundCloud"), False),
        (_el("f", text="Connect"), False),
        (_el("g", text="I did it"), False),
        (_el("h", tag="a", text="Blogging in public", href="/blog"), False),
    ],
)
def test_is_sign_in(el, expected) -> None:
    assert _is_sign_in(el) is expected


def _client_answering(choice: str, confidence: float) -> tuple[MagicMock, dict]:
    sent: dict = {}

    async def system_one(**kwargs):
        sent.update(kwargs)
        answer = types.SimpleNamespace(choice=choice, confidence=confidence)
        return types.SimpleNamespace(choices={"next_action": answer})

    return types.SimpleNamespace(system_one=system_one), sent


@pytest.mark.asyncio
async def test_a_sign_in_link_is_never_offered_to_the_model() -> None:
    handler = _handler()
    handler._client, sent = _client_answering("did", 0.9)
    page = types.SimpleNamespace(url="https://droploud.com/track/1")
    snapshot = {
        "login": _el("login", tag="a", text="Login to autocomplete matching steps"),
        "did": _el("did", text="I did it"),
    }

    await handler._ask_choice(page, snapshot)

    assert [e["key"] for e in sent["state"]["elements"]] == ["did"]
    assert "login" not in sent["questions"]["next_action"].criteria


@pytest.mark.asyncio
async def test_a_page_with_only_a_sign_in_link_asks_nothing() -> None:
    handler = _handler()

    def no_client():
        raise AssertionError

    handler._get_client = no_client
    snapshot = {"login": _el("login", tag="a", text="Log in")}
    page = types.SimpleNamespace(url="https://x.example/")
    assert await handler._ask_choice(page, snapshot) == ""


def test_an_empty_choice_is_an_idle_turn_not_an_unknown_key(caplog) -> None:
    handler = _handler()
    results: dict = {}
    with caplog.at_level(logging.INFO):
        target = handler._resolve_target("", {"did": _el("did")}, results, 4)
    assert target is None
    assert "unknown element key" not in caplog.text
    assert "el_4_unknown_choice" not in results
    assert "el_4_no_choice" in results


@pytest.mark.asyncio
@pytest.mark.parametrize(("confidence", "expected"), [(0.09, ""), (0.14, ""), (0.4, "did")])
async def test_a_pick_below_the_floor_is_an_idle_turn(confidence, expected) -> None:
    handler = _handler()
    handler._client, _ = _client_answering("did", confidence)
    page = types.SimpleNamespace(url="https://x.example/")
    assert await handler._ask_choice(page, {"did": _el("did")}) == expected


# --- #5: a cycle of chosen keys ---------------------------------------------------------


@pytest.mark.parametrize(
    ("history", "expected"),
    [
        (list("AANPAANPAANP"), list("AANP")),
        (list("ABABAB"), list("AB")),
        (list("XAANPAANPAANP"), list("AANP")),
        (list("AANPAANP"), None),
        (list("FVFV"), None),
        (list("AANPAANPAAN"), None),
        (list("AAAA"), None),
        (list("ABCDEF"), None),
        (list("ABCABD"), None),
        ([], None),
    ],
)
def test_repeating_cycle(history, expected) -> None:
    assert _repeating_cycle(history) == expected


@pytest.mark.asyncio
async def test_a_run_going_round_a_cycle_ends_early_with_the_reason(monkeypatch) -> None:
    """Valorizd: A A N P six times over, one changed page per lap, 25 turns burned."""
    counter = 0

    async def evaluate(_js, *_args):
        nonlocal counter
        counter += 1
        return [_el(k, text=f"{k} {counter}") for k in ("A", "N", "P")]

    page = MagicMock()
    page.evaluate = evaluate
    page.wait_for_timeout = AsyncMock()
    page.url = "https://gate.example.com/x"
    handle = MagicMock()
    handle.evaluate = AsyncMock()
    handle.click = AsyncMock()
    handle.is_visible = AsyncMock(return_value=True)
    handle.scroll_into_view_if_needed = AsyncMock()
    handle.as_element = MagicMock(return_value=handle)
    page.evaluate_handle = AsyncMock(return_value=handle)

    choices = iter("AANP" * 6)

    async def choose(self, _page, _snapshot, _dead=frozenset()):
        return next(choices)

    monkeypatch.setattr(JudgmentGateHandler, "_ask_choice", choose)
    monkeypatch.setattr(
        "soundcloud_dl.gate_handlers.judgment.detect_captcha", AsyncMock(return_value=None)
    )

    handler = _handler()
    with pytest.raises(StuckGate, match="repeating_4") as exc:
        await handler._run_steps(page, {})

    assert "jev_iter_12_" in str(exc.value.last_step_id)
    assert judgment_module._MAX_ITERATIONS > 12


# --- #6: a Drive folder is not a file ---------------------------------------------------


@pytest.mark.parametrize(
    ("url", "folder"),
    [
        ("https://drive.google.com/drive/folders/1AbC?usp=sharing", True),
        ("https://drive.google.com/drive/u/0/folders/1AbC", True),
        ("https://drive.google.com/drive/u/0/my-drive", False),
        ("https://drive.google.com/file/d/1AbC/view", False),
        ("https://evil.example/?x=drive.google.com/drive/folders/1", False),
        ("about:blank", False),
    ],
)
def test_drive_folder_url(url, folder) -> None:
    assert (drive_folder_url(url) is not None) is folder


def _popup(url: str) -> MagicMock:
    popup = MagicMock()
    popup.url = url
    popup.main_frame = types.SimpleNamespace(url=url)
    popup.on = MagicMock()
    return popup


def test_a_popup_that_opens_a_drive_folder_ends_the_run_as_unsupported() -> None:
    handler = _handler()
    popup = _popup("about:blank")
    handler.on_new_page(popup)
    navigated = next(c.args[1] for c in popup.on.call_args_list if c.args[0] == "framenavigated")
    popup.main_frame.url = "https://drive.google.com/drive/folders/1AbC"
    navigated(popup.main_frame)
    page = MagicMock()
    page.url = "https://droploud.com/track/1/success"

    with pytest.raises(GateNotSupportedError, match="drive/folders/1AbC"):
        handler._raise_if_drive_folder(page)


def test_a_drive_folder_in_an_iframe_is_ignored() -> None:
    handler = _handler()
    popup = _popup("about:blank")
    handler.on_new_page(popup)
    navigated = next(c.args[1] for c in popup.on.call_args_list if c.args[0] == "framenavigated")
    navigated(types.SimpleNamespace(url="https://drive.google.com/drive/folders/1AbC"))
    other = MagicMock()
    other.url = "https://droploud.com/track/1/success"
    handler._raise_if_drive_folder(other)


def test_the_drive_folder_reason_leads_with_what_it_is_and_keeps_the_url() -> None:
    """main.py stores only the first 180 characters of the reason."""
    handler = _handler()
    page = MagicMock()
    url = "https://drive.google.com/drive/folders/" + "x" * 33 + "?usp=sharing"
    page.url = url
    with pytest.raises(GateNotSupportedError) as exc:
        handler._raise_if_drive_folder(page)
    assert str(exc.value).startswith("Google Drive folder, fetch by hand: ")
    assert url in str(exc.value)[:180]


def test_the_gate_tab_itself_navigating_to_a_folder_ends_the_run() -> None:
    handler = _handler()
    page = MagicMock()
    page.url = "https://drive.google.com/drive/folders/1AbC"
    with pytest.raises(GateNotSupportedError):
        handler._raise_if_drive_folder(page)


@pytest.mark.asyncio
async def test_a_drive_folder_stops_the_wait_for_a_download() -> None:
    import asyncio

    handler = _handler()
    handler._drive_folder = "https://drive.google.com/drive/folders/1AbC"
    pending = asyncio.ensure_future(asyncio.sleep(30))
    assert await handler._download_unless_a_popup_took_it(pending) is None
    await asyncio.sleep(0)
    assert pending.cancelled()
