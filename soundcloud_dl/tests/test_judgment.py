"""Unit tests for JudgmentGateHandler's decision logic (judgment.py).

Mocks the Choice call's return value rather than hitting the real API — only the real
browser + real paid API call stay manual-only (see the plan's Verify section).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl.gate_handlers import dom_snapshot
from soundcloud_dl.gate_handlers.base import StepResult, StuckGate
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, CaptchaKind
from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler


@pytest.fixture(autouse=True)
def _stub_detect_captcha(monkeypatch):
    """Stub detect_captcha to return None by default for gate-handler tests."""

    async def _none(_page):
        return None

    monkeypatch.setattr("soundcloud_dl.gate_handlers.judgment.detect_captcha", _none)


def make_handler(**kwargs) -> JudgmentGateHandler:
    kwargs.setdefault("template_vars", {"email": "test@test.com", "name": "Tom"})
    return JudgmentGateHandler(**kwargs)


def make_element() -> MagicMock:
    el = MagicMock()
    el.scroll_into_view_if_needed = AsyncMock()
    el.click = AsyncMock()
    el.fill = AsyncMock()
    el.type = AsyncMock()
    el.get_attribute = AsyncMock(return_value=None)
    el.is_visible = AsyncMock(return_value=True)
    el.evaluate = AsyncMock()
    return el


def make_page(snapshots: list[list[dict]], *, found_element=None) -> MagicMock:
    """Return a mock page whose snapshot evaluation yields successive snapshots.

    Calls past the end keep returning the last one, which models a page that has stopped
    changing — the loop's settle poll then reads no progress, as it would in the browser.
    """
    page = MagicMock()
    call_index = 0

    async def evaluate(_js, *_args):
        nonlocal call_index
        idx = min(call_index, len(snapshots) - 1)
        call_index += 1
        return snapshots[idx]

    handle = MagicMock()
    handle.as_element = MagicMock(return_value=found_element)

    async def evaluate_handle(_js, _key):
        return handle

    page.evaluate = evaluate
    page.evaluate_handle = evaluate_handle
    page.wait_for_timeout = AsyncMock()
    page.url = "https://gate.example.com/track"
    return page


def make_changing_page(*, found_element=None) -> MagicMock:
    """A page that returns a distinct snapshot on every call — never reads as no-progress."""
    page = make_page([[]], found_element=found_element)
    counter = 0

    async def evaluate(_js, *_args):
        nonlocal counter
        counter += 1
        return [{**PLAIN_BUTTON, "text": f"Continue {counter}"}]

    page.evaluate = evaluate
    return page


def stub_choice(monkeypatch, choices: list[str]) -> None:
    """Make handler._ask_choice return each value in order, one per call."""
    choice_iter = iter(choices)

    async def fake_ask_choice(self, _page, _snapshot, _dead=frozenset()):
        return next(choice_iter)

    monkeypatch.setattr(JudgmentGateHandler, "_ask_choice", fake_ask_choice)


def element(**overrides) -> dict:
    base = {
        "key": "k",
        "id": "",
        "step": "",
        "tag": "button",
        "cls": "",
        "href": "",
        "disabled": False,
        "visible": True,
        "text": "",
        "placeholder": "",
        "name": "",
    }
    return base | overrides


EMAIL_INPUT = element(key="el_email", tag="input", placeholder="Your email", name="email")
PLAIN_BUTTON = element(key="el_btn", text="Continue")
READY_DOWNLOAD_LINK = element(
    key="downloadProcess",
    id="downloadProcess",
    tag="a",
    href="https://gate.example.com/download/123",
    text="Download",
)
DISABLED_DOWNLOAD_LINK = element(
    key="gateDownloadButton",
    id="gateDownloadButton",
    tag="a",
    cls="free_dwln disable disabled",
    href="javascript:void(0);",
    text="Get Free Download",
)


@pytest.mark.asyncio
async def test_fill_dispatch_matches_input_by_name(monkeypatch):
    """Choosing an <input> whose name matches a template_vars key fills it, not clicks it."""
    handler = make_handler()
    el = make_element()
    page = make_page([[EMAIL_INPUT]], found_element=el)
    stub_choice(monkeypatch, ["el_email"] * 20)

    results = {}
    with pytest.raises(StuckGate, match="no_progress"):
        await handler._run_steps(page, results)

    assert results["el_1_fill"] == StepResult.EXECUTED
    el.type.assert_awaited()
    el.click.assert_not_called()


@pytest.mark.asyncio
async def test_click_dispatch_for_non_fillable_element(monkeypatch):
    """Choosing a <button> clicks it, not fills it."""
    handler = make_handler()
    el = make_element()
    page = make_page([[PLAIN_BUTTON]], found_element=el)
    stub_choice(monkeypatch, ["el_btn"] * 20)

    results = {}
    with pytest.raises(StuckGate, match="no_progress"):
        await handler._run_steps(page, results)

    assert results["el_1_click"] == StepResult.EXECUTED
    el.fill.assert_not_called()


@pytest.mark.asyncio
async def test_click_uses_force_so_an_overlay_costs_5s_not_30s(monkeypatch):
    """Playwright's default actionability wait is 30s; hypeddit's carousel triggers it."""
    handler = make_handler()
    el = make_element()
    page = make_page([[PLAIN_BUTTON]], found_element=el)
    stub_choice(monkeypatch, ["el_btn"] * 20)

    with pytest.raises(StuckGate):
        await handler._run_steps(page, {})

    assert el.click.await_args.kwargs == {"force": True, "timeout": 5_000}


@pytest.mark.asyncio
async def test_unlocked_gate_downloads_without_consulting_the_model(monkeypatch):
    """An open gate is a deterministic fact — spending a paid Choice call on it is waste.

    download_dir=None means the capture path reports no download (mirrors base.py), so the
    run then continues and eventually reads as stuck. That is the assertion's backdrop, not
    the point of the test.
    """
    handler = make_handler(download_dir=None)
    el = make_element()
    page = make_page([[READY_DOWNLOAD_LINK]], found_element=el)
    asked_before_download = []

    async def record_then_answer(self, _page, _snapshot, _dead=frozenset()):
        asked_before_download.append("el_1_download" not in results)
        return "downloadProcess"

    monkeypatch.setattr(JudgmentGateHandler, "_ask_choice", record_then_answer)

    results = {}
    with pytest.raises(StuckGate):
        await handler._run_steps(page, results)

    assert results["el_1_download"] == StepResult.SKIPPED
    assert not any(asked_before_download)
    el.click.assert_awaited()


@pytest.mark.asyncio
async def test_already_unlocked_with_only_a_locked_button_keeps_looping_then_gets_stuck(
    monkeypatch,
):
    """A locked #gateDownloadButton must not satisfy already_unlocked, semicolon or not."""
    handler = make_handler()
    page = make_page([[DISABLED_DOWNLOAD_LINK]], found_element=None)
    stub_choice(monkeypatch, ["already_unlocked"] * 20)

    results = {}
    with pytest.raises(StuckGate, match="no_progress"):
        await handler._run_steps(page, results)

    assert results["el_1_claimed_unlocked"] == StepResult.SKIPPED


@pytest.mark.asyncio
async def test_unknown_choice_key_is_skipped_not_crashed(monkeypatch):
    """A hallucinated element key that isn't in the snapshot is logged and skipped."""
    handler = make_handler()
    page = make_page([[PLAIN_BUTTON]], found_element=None)
    stub_choice(monkeypatch, ["nonexistent_key"] * 20)

    results = {}
    with pytest.raises(StuckGate, match="no_progress"):
        await handler._run_steps(page, results)

    assert results["el_1_unknown_choice"] == StepResult.SKIPPED


@pytest.mark.asyncio
async def test_one_idle_turn_is_tolerated(monkeypatch):
    """An OAuth popup can still be resolving a turn later — don't call that stuck."""
    handler = make_handler()
    el = make_element()
    page = make_page([[PLAIN_BUTTON]], found_element=el)
    stub_choice(monkeypatch, ["el_btn"] * 20)

    results = {}
    with pytest.raises(StuckGate, match="no_progress"):
        await handler._run_steps(page, results)

    assert results["el_2_click"] == StepResult.EXECUTED


@pytest.mark.asyncio
async def test_iteration_cap_raises_stuck_gate(monkeypatch):
    """A page that always changes never reads as stuck — the cap stops it instead."""
    handler = make_handler()
    page = make_changing_page(found_element=make_element())
    stub_choice(monkeypatch, ["el_btn"] * 40)

    with pytest.raises(StuckGate, match="jev_cap_15"):
        await handler._run_steps(page, {})


@pytest.mark.asyncio
async def test_captcha_raises_captcha_encountered(monkeypatch):
    async def fake_detect(_page):
        return CaptchaKind.HCAPTCHA

    monkeypatch.setattr("soundcloud_dl.gate_handlers.judgment.detect_captcha", fake_detect)
    handler = make_handler()
    page = make_page([[PLAIN_BUTTON]])

    with pytest.raises(CaptchaEncountered) as exc:
        await handler._run_steps(page, {})
    assert exc.value.kind == CaptchaKind.HCAPTCHA


@pytest.mark.asyncio
async def test_snapshot_keeps_the_first_of_two_colliding_keys():
    """find_element_by_key returns the first match; the snapshot must describe that one."""
    handler = make_handler()
    first = element(key="dupe", text="first")
    second = element(key="dupe", text="second")
    page = make_page([[first, second]])

    snapshot = await handler._snapshot(page)
    assert snapshot["dupe"]["text"] == "first"


def test_key_derivation_is_not_positional():
    """Regression guard: a tag+index key silently re-points when a node is inserted ahead.

    The derivation is JavaScript and needs a browser to execute, so this asserts the source
    carries no index term rather than executing it.
    """
    assert "querySelectorAll" in dom_snapshot.SNAPSHOT_JS
    assert "map((el, i)" not in dom_snapshot.SNAPSHOT_JS
    assert "'#' + i" not in dom_snapshot.SNAPSHOT_JS
    assert dom_snapshot.SNAPSHOT_JS.count("const elKey") == 1
    assert dom_snapshot.FIND_BY_KEY_JS.count("const elKey") == 1


@pytest.mark.asyncio
async def test_a_control_that_changed_nothing_is_not_offered_again(monkeypatch):
    """Hypeddit's SoundCloud Next stays on screen after its page is done.

    The model re-picked it at 0.94+ for three turns while the gate sat still, because a
    dead end looks identical to a live one in a snapshot.
    """
    handler = make_handler()
    page = make_page([[PLAIN_BUTTON, element(key="el_other", text="Connect")]], found_element=None)
    seen: list[frozenset] = []

    async def capture(self, _page, _snapshot, dead=frozenset()):
        seen.append(dead)
        return "el_btn"

    monkeypatch.setattr(JudgmentGateHandler, "_ask_choice", capture)

    with pytest.raises(StuckGate):
        await handler._run_steps(page, {})

    assert seen[0] == frozenset()
    assert "el_btn" in seen[-1]


@pytest.mark.asyncio
async def test_dead_key_is_forgiven_once_it_works(monkeypatch):
    """A control can be dead on one page and live on the next — don't ban it forever."""
    handler = make_handler()
    el = make_element()
    page = make_changing_page(found_element=el)
    seen: list[frozenset] = []

    async def capture(self, _page, _snapshot, dead=frozenset()):
        seen.append(dead)
        return "el_btn"

    monkeypatch.setattr(JudgmentGateHandler, "_ask_choice", capture)

    with pytest.raises(StuckGate, match="jev_cap_15"):
        await handler._run_steps(page, {})

    assert all(d == frozenset() for d in seen)
