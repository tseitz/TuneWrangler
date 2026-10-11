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
@pytest.mark.parametrize("confidence", [0.06, 0.4])
async def test_a_low_confidence_pick_is_still_acted_on(confidence) -> None:
    # backstaged's right answer, its Instagram button, came back at 0.06 with two options.
    handler = _handler()
    handler._client, _ = _client_answering("did", confidence)
    page = types.SimpleNamespace(url="https://x.example/")
    assert await handler._ask_choice(page, {"did": _el("did")}) == "did"


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


# --- backstaged: an open section header is not a way forward ---------------------------


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_the_snapshot_marks_section_headers_and_whether_they_are_open() -> None:
    html = (
        '<button id="open" aria-expanded="true">One</button>'
        '<button id="shut" aria-expanded="false">Two</button>'
        '<button id="plain">Connect SoundCloud</button>'
    )
    by_id = {e["id"]: e for e in await _snapshot_of(html) if e["id"]}
    assert (by_id["open"]["disclosure"], by_id["open"]["expanded"]) == (True, True)
    assert (by_id["shut"]["disclosure"], by_id["shut"]["expanded"]) == (True, False)
    assert (by_id["plain"]["disclosure"], by_id["plain"]["expanded"]) == (False, False)


def _header(key: str, *, expanded: bool) -> dict:
    return _el(key, disclosure=True, expanded=expanded)


@pytest.mark.asyncio
async def test_an_open_section_header_is_not_offered_but_a_closed_one_is() -> None:
    handler = _handler()
    handler._client, sent = _client_answering("shut", 0.9)
    page = types.SimpleNamespace(url="https://backstaged.io/d/x")
    snapshot = {
        "open": _header("open", expanded=True),
        "shut": _header("shut", expanded=False),
        "real": _el("real", text="Follow on Instagram"),
    }

    await handler._ask_choice(page, snapshot)

    assert [e["key"] for e in sent["state"]["elements"]] == ["shut", "real"]
    shut = sent["questions"]["next_action"].criteria["shut"]
    assert "section header, closed" in shut
    assert "section header" not in sent["questions"]["next_action"].criteria["real"]


@pytest.mark.asyncio
async def test_an_open_header_is_still_offered_when_nothing_else_is() -> None:
    handler = _handler()
    handler._client, sent = _client_answering("open", 0.9)
    page = types.SimpleNamespace(url="https://x.example/")

    await handler._ask_choice(page, {"open": _header("open", expanded=True)})

    assert [e["key"] for e in sent["state"]["elements"]] == ["open"]
    assert "section header, open" in sent["questions"]["next_action"].criteria["open"]


# --- droploud: the site's own Instagram card is not the gate ---------------------------

_DROPLOUD_PAGE = """
<!doctype html><html><body>
  <section>
    <p>Follow @secret_stvsh on Instagram</p>
    <button id="artist">@secret_stvsh</button>
    <a id="artist_link" href="https://www.instagram.com/secret_stvsh/">profile</a>
    <button id="did">I did it</button>
  </section>
  <section>
    <p>FOLLOW @droploud AND @BADMOUTHRECS ON SOUNDCLOUD</p>
    <button id="sc_step">Connect SoundCloud</button>
    <a id="sc_link" href="https://soundcloud.com/droploud">droploud</a>
  </section>
  <div id="card">
    <p>Droploud</p><h2>Follow us on Instagram</h2><p>@droploud.official</p>
    <button id="promo_follow">Follow</button>
  </div>
  <a id="promo_link" href="https://www.instagram.com/droploud.official/"></a>
</body></html>
"""


async def _chrome_at(url: str, html: str) -> dict[str, bool]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.fulfill(body=html, content_type="text/html"))
        await page.goto(url)
        els = await snapshot_elements(page)
        await browser.close()
    return {e["id"]: e["chrome"] for e in els if e["id"]}


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_the_gate_sites_own_social_promo_is_chrome_but_the_artists_links_are_not() -> None:
    chrome = await _chrome_at("https://droploud.com/track/1", _DROPLOUD_PAGE)
    assert chrome["promo_follow"] is True
    assert chrome["promo_link"] is True
    assert chrome["artist"] is False
    assert chrome["artist_link"] is False
    assert chrome["did"] is False
    # A gate may genuinely ask for the site's own SoundCloud.
    assert chrome["sc_step"] is False
    assert chrome["sc_link"] is False


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_another_sites_page_is_not_judged_by_droplouds_brand() -> None:
    chrome = await _chrome_at("https://other-gate.com/track/1", _DROPLOUD_PAGE)
    assert chrome["promo_follow"] is False
    assert chrome["promo_link"] is False


@pytest.mark.asyncio
async def test_after_a_header_opens_a_step_the_other_headers_are_withheld() -> None:
    """Backstaged: opening "Repost on SoundCloud" reveals Connect SoundCloud, and with the
    other closed header still on offer the run opened the headers in turn instead."""
    handler = _handler()
    handler._client, sent = _client_answering("connect", 0.9)
    page = types.SimpleNamespace(url="https://backstaged.io/d/x")
    before = {
        "insta_hdr": _header("insta_hdr", expanded=False),
        "repost_hdr": _header("repost_hdr", expanded=False),
        "insta_btn": _el("insta_btn", text="Follow on Instagram"),
    }
    after = {
        "insta_hdr": _header("insta_hdr", expanded=False),
        "repost_hdr": _header("repost_hdr", expanded=True),
        "connect": _el("connect", text="Connect SoundCloud"),
    }
    handler._header_prior = {k for k, e in before.items() if e["visible"]}

    await handler._ask_choice(page, after)

    assert [e["key"] for e in sent["state"]["elements"]] == ["connect"]


@pytest.mark.asyncio
async def test_headers_stay_on_offer_when_opening_one_revealed_nothing() -> None:
    handler = _handler()
    handler._client, sent = _client_answering("repost_hdr", 0.9)
    page = types.SimpleNamespace(url="https://backstaged.io/d/x")
    snap = {
        "insta_hdr": _header("insta_hdr", expanded=False),
        "repost_hdr": _header("repost_hdr", expanded=False),
        "btn": _el("btn"),
    }
    handler._header_prior = set(snap)

    await handler._ask_choice(page, snap)

    assert [e["key"] for e in sent["state"]["elements"]] == ["insta_hdr", "repost_hdr", "btn"]


@pytest.mark.asyncio
async def test_a_header_click_in_the_run_loop_withholds_headers_on_the_next_turn(
    monkeypatch,
) -> None:
    """The two-turn shape from the backstaged retest, through the real loop."""
    clicked = False
    closed = [
        _header("insta_hdr", expanded=False),
        _header("repost_hdr", expanded=False),
        _el("insta_btn", text="Follow on Instagram"),
    ]
    opened = [
        _header("insta_hdr", expanded=False),
        _header("repost_hdr", expanded=True),
        _el("connect", text="Connect SoundCloud"),
    ]

    async def evaluate(_js, *_args):
        return opened if clicked else closed

    handle = MagicMock()

    async def click(**_kwargs):
        nonlocal clicked
        clicked = True

    handle.click = click
    handle.is_visible = AsyncMock(return_value=True)
    handle.scroll_into_view_if_needed = AsyncMock()
    handle.evaluate = AsyncMock()
    handle.as_element = MagicMock(return_value=handle)
    page = MagicMock()
    page.evaluate = evaluate
    page.evaluate_handle = AsyncMock(return_value=handle)
    page.wait_for_timeout = AsyncMock()
    page.url = "https://backstaged.io/d/x"

    offered: list[list[str]] = []

    class _Stop(Exception):  # noqa: N818
        pass

    async def system_one(**kwargs):
        offered.append([e["key"] for e in kwargs["state"]["elements"]])
        if len(offered) > 1:
            raise _Stop
        answer = types.SimpleNamespace(choice="repost_hdr", confidence=0.5)
        return types.SimpleNamespace(choices={"next_action": answer})

    monkeypatch.setattr(
        "soundcloud_dl.gate_handlers.judgment.read_requirements", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "soundcloud_dl.gate_handlers.judgment.detect_captcha", AsyncMock(return_value=None)
    )
    handler = _handler()
    handler._client = types.SimpleNamespace(system_one=system_one)

    with pytest.raises(_Stop):
        await handler._run_steps(page, {})

    assert offered[0] == ["insta_hdr", "repost_hdr", "insta_btn"]
    assert offered[1] == ["connect"]


@pytest.mark.asyncio
async def test_a_non_header_click_clears_the_header_memory_in_the_run_loop(monkeypatch) -> None:
    """Header, then a plain control, then a turn that shows something new. The memory of the
    header click must not outlive the click after it, or the third turn loses its headers."""
    clicks = 0
    states = [
        [_header("hdr_a", expanded=False), _header("hdr_b", expanded=False), _el("plain")],
        # Opening hdr_b reveals nothing new, so the closed header stays on offer.
        [_header("hdr_a", expanded=False), _header("hdr_b", expanded=True), _el("plain")],
        [
            _header("hdr_a", expanded=False),
            _header("hdr_b", expanded=False),
            _el("plain"),
            _el("new_control"),
        ],
    ]

    async def evaluate(_js, *_args):
        return states[min(clicks, len(states) - 1)]

    handle = MagicMock()

    async def click(**_kwargs):
        nonlocal clicks
        clicks += 1

    handle.click = click
    handle.is_visible = AsyncMock(return_value=True)
    handle.scroll_into_view_if_needed = AsyncMock()
    handle.evaluate = AsyncMock()
    handle.as_element = MagicMock(return_value=handle)
    page = MagicMock()
    page.evaluate = evaluate
    page.evaluate_handle = AsyncMock(return_value=handle)
    page.wait_for_timeout = AsyncMock()
    page.url = "https://backstaged.io/d/x"

    offered: list[list[str]] = []
    picks = iter(["hdr_b", "plain"])

    class _Stop(Exception):  # noqa: N818
        pass

    async def system_one(**kwargs):
        offered.append([e["key"] for e in kwargs["state"]["elements"]])
        try:
            choice = next(picks)
        except StopIteration:
            raise _Stop from None
        answer = types.SimpleNamespace(choice=choice, confidence=0.5)
        return types.SimpleNamespace(choices={"next_action": answer})

    monkeypatch.setattr(
        "soundcloud_dl.gate_handlers.judgment.read_requirements", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "soundcloud_dl.gate_handlers.judgment.detect_captcha", AsyncMock(return_value=None)
    )
    handler = _handler()
    handler._client = types.SimpleNamespace(system_one=system_one)

    with pytest.raises(_Stop):
        await handler._run_steps(page, {})

    assert offered == [
        ["hdr_a", "hdr_b", "plain"],
        ["hdr_a", "plain"],
        ["hdr_a", "hdr_b", "plain", "new_control"],
    ]


# --- backstaged: the enabled Unlock button, a form is not a control, the offered log -----

_UNLOCK_FORM = """
<!doctype html><html><body>
  <form>
    <p>Support TRINIST in 2 steps to unlock</p>
    <button type="submit" id="unlock"
      class="inline-flex disabled:pointer-events-none disabled:opacity-50 hover:bg-primary/85
             [&_svg]:pointer-events-none focus-visible:ring-2 bg-primary h-9">
      <svg class="lucide lucide-lock"></svg>Unlock for free</button>
  </form>
</body></html>
"""


@pytest.mark.requires_browser
@pytest.mark.asyncio
async def test_variant_prefixed_classes_are_not_shown() -> None:
    unlock = next(e for e in await _snapshot_of(_UNLOCK_FORM) if e["id"] == "unlock")
    assert unlock["disabled"] is False
    assert "disabled" not in unlock["cls"]
    assert unlock["cls"].split() == ["inline-flex", "bg-primary", "h-9"]


@pytest.mark.asyncio
async def test_a_form_is_not_offered_but_a_form_with_a_step_is() -> None:
    handler = _handler()
    handler._client, sent = _client_answering("unlock", 0.9)
    page = types.SimpleNamespace(url="https://backstaged.io/d/x")
    snapshot = {
        "form": _el("form", tag="form", text="Support TRINIST in 2 steps"),
        "stepped": _el("stepped", tag="form", step="follow"),
        "unlock": _el("unlock", text="Unlock for free"),
    }

    await handler._ask_choice(page, snapshot)

    assert [e["key"] for e in sent["state"]["elements"]] == ["stepped", "unlock"]


@pytest.mark.asyncio
async def test_each_ask_logs_the_offered_keys_with_a_little_text(caplog) -> None:
    handler = _handler()
    handler._client, _ = _client_answering("unlock", 0.9)
    page = types.SimpleNamespace(url="https://backstaged.io/d/x")
    snapshot = {
        "unlock": _el("unlock", text="Unlock for free"),
        "long": _el("long", text="x" * 80 + "\nsecond line"),
    }

    with caplog.at_level(logging.INFO):
        await handler._ask_choice(page, snapshot)

    line = next(r.getMessage() for r in caplog.records if "offered to jev" in r.getMessage())
    assert "'unlock'='Unlock for free'" in line
    assert "'long'='" + "x" * 30 + "'" in line
    assert "x" * 31 not in line
    assert "\n" not in line
