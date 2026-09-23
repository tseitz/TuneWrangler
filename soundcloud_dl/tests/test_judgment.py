"""Unit tests for JudgmentGateHandler's decision logic (judgment.py).

Mocks the Choice call's return value rather than hitting the real API — only the real
browser + real paid API call stay manual-only (see the plan's Verify section).
"""

import asyncio
import contextlib
import logging
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import Error as PlaywrightError

from soundcloud_dl.downloads import MIN_TRACK_BYTES
from soundcloud_dl.gate_handlers import dom_snapshot
from soundcloud_dl.gate_handlers import judgment as judgment_module
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
    """Make handler._ask_choice return each value in order, one per call.

    Calls past the end repeat the last, matching make_page. Raising StopIteration instead
    tied every caller's list length to _MAX_ITERATIONS, so raising the cap failed tests
    that had nothing to do with it.
    """
    calls = 0

    async def fake_ask_choice(self, _page, _snapshot, _dead=frozenset()):
        nonlocal calls
        idx = min(calls, len(choices) - 1)
        calls += 1
        return choices[idx]

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


def stub_requirements(monkeypatch, blocks_per_turn: list[list[str]]) -> None:
    """Make the per-turn requirement read yield each list in order, then repeat the last."""
    calls = 0

    async def fake_read(_page):
        nonlocal calls
        idx = min(calls, len(blocks_per_turn) - 1)
        calls += 1
        return blocks_per_turn[idx]

    monkeypatch.setattr(judgment_module, "read_requirements", fake_read)


@pytest.mark.asyncio
async def test_terms_the_gate_states_are_shown_to_the_model(monkeypatch):
    """The snapshot only collects interactive elements, so a stated term is invisible
    to the model unless it is carried in separately."""
    handler = make_handler()
    stub_requirements(monkeypatch, [["FOLLOW @A ON SOUNDCLOUD"]])
    page = make_page([[PLAIN_BUTTON]], found_element=make_element())
    stub_choice(monkeypatch, ["el_btn"] * 20)

    with pytest.raises(StuckGate):
        await handler._run_steps(page, {})

    assert handler._requirements == ["FOLLOW @A ON SOUNDCLOUD"]


@pytest.mark.asyncio
async def test_terms_restated_on_every_slide_only_fire_the_callback_once(monkeypatch):
    """A gate re-renders its terms as it advances. Acting on them again would re-follow
    profiles the run has already followed."""
    seen: list[list[str]] = []

    async def on_requirements(blocks):
        seen.append(blocks)

    handler = make_handler(on_requirements=on_requirements)
    stub_requirements(monkeypatch, [["FOLLOW @A ON SOUNDCLOUD"]])
    page = make_page([[PLAIN_BUTTON]], found_element=make_element())
    stub_choice(monkeypatch, ["el_btn"] * 20)

    with pytest.raises(StuckGate):
        await handler._run_steps(page, {})

    assert seen == [["FOLLOW @A ON SOUNDCLOUD"]]


@pytest.mark.asyncio
async def test_terms_that_appear_later_still_fire(monkeypatch):
    """Droploud states nothing on the page it opens on — its terms arrive on step 2."""
    seen: list[list[str]] = []

    async def on_requirements(blocks):
        seen.append(blocks)

    handler = make_handler(on_requirements=on_requirements)
    stub_requirements(monkeypatch, [[], [], ["FOLLOW @LATE ON SOUNDCLOUD"]])
    page = make_changing_page(found_element=make_element())
    stub_choice(monkeypatch, ["el_btn"] * 20)

    with pytest.raises(StuckGate):
        await handler._run_steps(page, {})

    assert seen == [["FOLLOW @LATE ON SOUNDCLOUD"]]


@pytest.mark.asyncio
async def test_a_failing_callback_does_not_end_the_run(monkeypatch):
    """The gate can still be driven by clicking, so failing to act on its terms
    out-of-band must not abort a run that has not tried the page yet."""

    async def on_requirements(_blocks):
        msg = "SoundCloud said no"
        raise RuntimeError(msg)

    handler = make_handler(on_requirements=on_requirements)
    stub_requirements(monkeypatch, [["FOLLOW @A ON SOUNDCLOUD"]])
    page = make_page([[PLAIN_BUTTON]], found_element=make_element())
    stub_choice(monkeypatch, ["el_btn"] * 20)

    with pytest.raises(StuckGate):
        await handler._run_steps(page, {})


def fake_download(
    name: str = "track.mp3",
    url: str = "https://cdn.example/dl/abc",
    size: int = MIN_TRACK_BYTES,
) -> MagicMock:
    """A stand-in for Playwright's Download, writing real bytes so save_download works.

    url is set explicitly: left as a MagicMock attribute it is not a string, and the asset
    filter that reads it cannot be exercised.

    size clears MIN_TRACK_BYTES by default because the handler now discards anything
    below it as a stream fragment. Pass a smaller one to exercise that.
    """
    download = MagicMock()
    download.suggested_filename = name
    download.url = url

    async def save_as(path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"a" * size)

    download.save_as = save_as
    return download


@pytest.mark.asyncio
async def test_a_download_the_page_started_itself_is_saved(tmp_path):
    """Droploud starts the file on its success page with nothing clicked.

    The expect_download wrapped around a click of ours can never see that one.
    """
    handler = make_handler(download_dir=tmp_path)
    handler._caught.append(fake_download())

    assert await handler._take_caught_download() is True
    assert (tmp_path / "track.mp3").stat().st_size == MIN_TRACK_BYTES


@pytest.mark.asyncio
async def test_a_page_started_download_that_is_only_a_fragment_is_thrown_away(tmp_path):
    """The gate page's embedded player streams while the gate is worked through. Keeping
    one of its segments reports a success and records the track done, for good."""
    handler = make_handler(download_dir=tmp_path)
    handler._caught.append(fake_download(size=197_000))

    assert await handler._take_caught_download() is False
    assert list(tmp_path.iterdir()) == []
    assert handler.downloaded is False


def test_the_download_handler_can_carry_playwrights_marker_attribute():
    """Playwright tags the handler it is given with an attribute.

    self._caught.append is a builtin and cannot hold one, so page.on raised AttributeError
    at attach time — before the gate had been opened at all.
    """
    handler = make_handler()
    page = MagicMock()

    handler._watch_downloads(page)

    event, registered = page.on.call_args.args
    assert event == "download"
    registered._pw_impl_instance_ = object()


def test_the_registered_handler_actually_collects():
    handler = make_handler()
    page = MagicMock()
    handler._watch_downloads(page)

    page.on.call_args.args[1]("a-download")

    assert handler._caught == ["a-download"]


@pytest.mark.asyncio
async def test_nothing_caught_is_not_reported_as_a_download(tmp_path):
    handler = make_handler(download_dir=tmp_path)
    assert await handler._take_caught_download() is False


@pytest.mark.asyncio
async def test_a_caught_download_ends_the_run_before_any_more_clicking(monkeypatch, tmp_path):
    """Once the file is in hand the gate's state stops mattering.

    Without this the success page reads as just another page to keep clicking, and the run
    burns every remaining turn on it.
    """
    handler = make_handler(download_dir=tmp_path)
    handler._caught.append(fake_download())
    page = make_page([[PLAIN_BUTTON]], found_element=make_element())
    stub_choice(monkeypatch, ["el_btn"] * 20)

    results = await handler._run_steps(page, {})

    assert results["el_1_download"] == StepResult.EXECUTED


GATE_URL = "https://gate.example.com/track/abc-123"


@pytest.mark.parametrize(
    ("url", "on_gate"),
    [
        (GATE_URL, True),
        # A gate that advances by putting its step in the query string is still on its own
        # page; snapping that back would undo the step it had just taken.
        (GATE_URL + "?step=2", True),
        (GATE_URL + "#comments", True),
        (GATE_URL + "/", True),
        # Droploud's finish line. Read as leaving, this dragged the page back and re-ran a
        # gate that had already succeeded — twice, until the run gave up.
        (GATE_URL + "/success", True),
        ("https://gate.example.com/artist/inda", False),
        ("https://gate.example.com/track/other-id", False),
        # A prefix of the gate path is not under it.
        ("https://gate.example.com/track", False),
        ("https://gate.example.com/", False),
    ],
)
def test_the_gate_owns_its_own_subtree(url, on_gate):
    handler = make_handler()
    handler._gate_url = GATE_URL
    assert handler._still_on_the_gate(url) is on_gate


@pytest.mark.asyncio
async def test_a_click_that_wanders_off_the_gate_is_walked_back():
    """The host does not change, so the login-wall guard never fires.

    On droploud this left the run on the artist's profile clicking "FREE DL" on other
    people's tracks until it gave up.
    """
    handler = make_handler()
    handler._gate_url = GATE_URL
    page = make_page([[]])
    page.url = "https://gate.example.com/artist/inda"
    page.goto = AsyncMock()

    assert await handler._reanchor_page(page) is True
    page.goto.assert_awaited_once()
    assert page.goto.await_args.args[0] == GATE_URL


@pytest.mark.asyncio
async def test_a_page_still_on_the_gate_is_not_reloaded():
    handler = make_handler()
    handler._gate_url = GATE_URL
    page = make_page([[]])
    page.url = GATE_URL
    page.goto = AsyncMock()

    assert await handler._reanchor_page(page) is False
    page.goto.assert_not_called()


def test_the_link_that_led_off_the_gate_is_not_offered_again():
    handler = make_handler()
    dead: set[str] = set()
    handler._note_off_gate(dead, "a@theartistlink")
    assert dead == {"a@theartistlink"}


def test_a_gate_that_keeps_navigating_away_ends_the_run_saying_so():
    """Better than the bare "no progress" this used to surface three turns later."""
    handler = make_handler()
    handler._off_gate_returns = judgment_module._MAX_OFF_GATE_RETURNS - 1
    with pytest.raises(StuckGate, match="navigating away"):
        handler._note_off_gate(set(), None)


@pytest.mark.asyncio
async def test_an_empty_field_we_have_a_value_for_is_filled_before_the_model_is_asked(monkeypatch):
    """A gate's continue button is commonly disabled until its fields have content.

    Asked to choose against an empty box the model picked the dead button at 0.51 and
    spent the turn on a control it could not press. This is not a decision, so it is not
    put to the model — and that also saves the API call.
    """

    class Asked(Exception):
        """Raised the moment the model is consulted, to pin which turn that first happens."""

    async def boom(self, _page, _snapshot, _dead=frozenset()):
        raise Asked

    monkeypatch.setattr(JudgmentGateHandler, "_ask_choice", boom)
    handler = make_handler()
    el = make_element()
    page = make_page([[EMAIL_INPUT]], found_element=el)

    results = {}
    # Turn 1 fills and restarts; the model is not reached until turn 2, once the field
    # it would have had to reason around already has content.
    with pytest.raises(Asked):
        await handler._run_steps(page, results)

    assert results["el_1_autofill"] == StepResult.EXECUTED
    el.type.assert_awaited()
    el.click.assert_not_called()


@pytest.mark.asyncio
async def test_a_field_is_only_autofilled_once(monkeypatch):
    """A page that blanks a field it does not like would otherwise loop for every turn."""
    stub_choice(monkeypatch, ["el_email"] * 20)
    handler = make_handler()
    el = make_element()
    # The snapshot keeps reporting it empty, as a page that clears the field would.
    page = make_page([[EMAIL_INPUT]], found_element=el)

    results = {}
    with pytest.raises(StuckGate):
        await handler._run_steps(page, results)

    autofills = [k for k in results if k.endswith("_autofill")]
    assert autofills == ["el_1_autofill"]


@pytest.mark.asyncio
async def test_a_field_that_already_has_content_is_left_to_the_model(monkeypatch):
    """Autofill only supplies what is missing. Replacing existing text is a judgment call."""
    handler = make_handler()
    el = make_element()
    prefilled = element(
        key="el_email", tag="input", placeholder="Your email", name="email", text="a@b.com"
    )
    page = make_page([[prefilled]], found_element=el)
    stub_choice(monkeypatch, ["el_email"] * 20)

    results = {}
    with pytest.raises(StuckGate, match="no_progress"):
        await handler._run_steps(page, results)

    assert results["el_1_fill"] == StepResult.EXECUTED
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


def test_download_due_spaces_retries_and_caps_attempts():
    """A fresh key is due immediately; a tried one waits, then is retired for good.

    Droploud's download button carries no locked class or icon at any point, so the fast
    path calls it ready before the gate's real requirements are met. A miss there is not
    proof the click was wrong — only that it was early — so it must stay retryable rather
    than banked forever the first time.
    """
    handler = make_handler()
    assert handler._download_due("k", 1) is True

    handler._download_attempts["k"] = 1
    handler._download_last_attempt_turn["k"] = 1
    assert handler._download_due("k", 2) is False
    assert handler._download_due("k", 1 + judgment_module._DOWNLOAD_RETRY_EVERY_TURNS) is True

    handler._download_attempts["k"] = judgment_module._MAX_DOWNLOAD_ATTEMPTS_PER_KEY
    handler._download_last_attempt_turn["k"] = 4
    assert handler._download_due("k", 1_000) is False


@pytest.mark.asyncio
async def test_a_missed_download_is_retried_once_the_gate_has_had_more_turns(monkeypatch):
    """The fast path's first miss must not lock the real download out for the rest of the run.

    Revert _download_due to the old set-based _tried_downloads and this fails: the second
    attempt never fires, _try_download is called once, and the run spends the rest of its
    turns asking Jev to click el_btn instead.
    """
    handler = make_handler()
    page = make_page([[PLAIN_BUTTON, READY_DOWNLOAD_LINK]], found_element=make_element())
    stub_choice(monkeypatch, ["el_btn"] * 30)

    attempts: list[int] = []

    async def fake_try_download(self, _page, _results, _target, i):
        attempts.append(i)
        return len(attempts) == 2

    monkeypatch.setattr(JudgmentGateHandler, "_try_download", fake_try_download)

    results = await handler._run_steps(page, {})

    assert attempts == [1, 1 + judgment_module._DOWNLOAD_RETRY_EVERY_TURNS]
    assert results is not None


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

    with pytest.raises(StuckGate, match=f"jev_cap_{judgment_module._MAX_ITERATIONS}"):
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


@pytest.mark.asyncio
async def test_a_dropped_gate_action_says_so(caplog):
    """Hypeddit's two data-step="follow" buttons collided into a single key.

    The second was never offered, so the gate could not be finished, and the run reported
    the download it could not reach rather than the button it was never shown.
    """
    handler = make_handler()
    first = element(key="dupe", step="follow", text="Follow Buntai")
    second = element(key="dupe", step="follow", text="Follow Saint Jabir")
    page = make_page([[first, second]])

    with caplog.at_level(logging.WARNING):
        await handler._snapshot(page)

    assert "share the key" in caplog.text
    assert "Follow Saint Jabir" in caplog.text


@pytest.mark.asyncio
async def test_repeated_page_furniture_is_not_warned_about(caplog):
    """A genre list rendered into two menus dropped 40 keys and would bury the one above."""
    handler = make_handler()
    page = make_page([[element(key="dupe", text="Techno"), element(key="dupe", text="Techno")]])

    with caplog.at_level(logging.WARNING):
        await handler._snapshot(page)

    assert caplog.text == ""


def test_a_repeated_data_step_gets_its_own_key():
    """One follow button per artist, both data-step="follow", is normal on hypeddit.

    Source-level for the same reason as the test below: the derivation is JavaScript.
    """
    assert "'data-step=' + step + stepSuffix(el)" in dom_snapshot.SNAPSHOT_JS
    assert "'data-step=' + step;" not in dom_snapshot.SNAPSHOT_JS
    assert "data-url" in dom_snapshot.SNAPSHOT_JS
    assert dom_snapshot.SNAPSHOT_JS.count("const stepSuffix") == 1
    assert dom_snapshot.FIND_BY_KEY_JS.count("const stepSuffix") == 1


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

    with pytest.raises(StuckGate, match=f"jev_cap_{judgment_module._MAX_ITERATIONS}"):
        await handler._run_steps(page, {})

    assert all(d == frozenset() for d in seen)


@pytest.mark.parametrize(
    ("name", "placeholder", "expected"),
    [
        # The real miss: Hypeddit's name box is name="email_name", and a first-match-wins
        # scan of _FIELD_HINTS typed the email address into it.
        ("email_name", "", "name"),
        ("email_address", "", "email"),
        ("name", "", "name"),
        ("", "Your email", "email"),
        ("fullname", "", "name"),
        ("subscribe", "", None),
    ],
)
def test_match_template_field_picks_the_role_not_the_prefix(name, placeholder, expected):
    handler = make_handler()
    el = {"name": name, "id": name, "placeholder": placeholder}
    assert handler._match_template_field(el) == expected


def test_describe_surfaces_checkbox_state_to_the_model():
    """droploud's continue button stays disabled until a consent box is ticked.

    Without type and checked in the per-choice text, a blocking unticked box and a
    finished ticked one read identically.
    """
    handler = make_handler()
    box = {
        "tag": "label",
        "text": "I agree to receive this track",
        "cls": "ds-check",
        "href": "",
        "type": "checkbox",
        "checked": False,
    }
    desc = handler._describe(box)
    assert "type='checkbox'" in desc
    assert "checked=False" in desc


def test_describe_omits_checked_for_things_that_cannot_be_checked():
    handler = make_handler()
    btn = {"tag": "button", "text": "Continue", "cls": "", "href": "", "type": "", "checked": False}
    assert "checked=" not in handler._describe(btn)


def test_snapshot_offers_the_label_that_wraps_a_styled_checkbox():
    """droploud hides the real input (display:none, 0x0) inside a visible <label>.

    The input fails isVisible and is never offered, so the label is the only thing that
    can be clicked — and clicking it toggles the input natively.
    """
    assert "label" in dom_snapshot._SELECTOR
    assert "checked:" in dom_snapshot.SNAPSHOT_JS
    assert "type:" in dom_snapshot.SNAPSHOT_JS
    # A label with no toggle inside it is caption text, not a control.
    assert "el.tagName === 'LABEL' && toggle === null" in dom_snapshot.SNAPSHOT_JS


def _el(key, **over):
    base = {
        "key": key,
        "tag": "button",
        "text": key,
        "cls": "",
        "href": "",
        "type": "",
        "checked": False,
        "disabled": False,
        "visible": True,
        "chrome": False,
        "onscreen": True,
    }
    base.update(over)
    return base


def _snap(*els):
    return {el["key"]: el for el in els}


def test_on_screen_drops_site_chrome_and_anything_below_the_fold():
    """The real miss: a droploud run spent eight turns opening FAQ accordions.

    Every expand redrew the page, so the stuck-detector stayed quiet while the run burned
    all fifteen turns on marketing content.
    """
    offered = judgment_module._on_screen(
        _snap(
            _el("gate_continue"),
            _el("footer_terms", chrome=True),
            _el("faq_accordion", onscreen=False),
            _el("hidden_thing", visible=False),
        )
    )
    assert set(offered) == {"gate_continue"}


def test_on_screen_keeps_chrome_rather_than_offering_nothing():
    """A gate that does put its control in a header must still be reachable."""
    offered = judgment_module._on_screen(_snap(_el("header_dl", chrome=True)))
    assert set(offered) == {"header_dl"}


def test_on_screen_falls_back_when_the_whole_gate_is_off_screen():
    offered = judgment_module._on_screen(_snap(_el("gate_dl", onscreen=False)))
    assert set(offered) == {"gate_dl"}


def test_on_screen_tolerates_elements_without_the_new_fields():
    """Hand-built elements elsewhere in these tests carry neither field."""
    bare = {"key": "b", "visible": True}
    assert set(judgment_module._on_screen({"b": bare})) == {"b"}


def test_a_pending_gate_action_gets_the_long_settle():
    """Hypeddit clears 'undone' only after confirming the action against the SoundCloud API."""
    pending = element(key="k", step="follow", cls="hype-btn undone")
    assert judgment_module._settle_attempts(pending) == judgment_module._SETTLE_POLL_ATTEMPTS


@pytest.mark.parametrize(
    "cls",
    [
        "hype-btn button-next",  # a carousel Next
        "hype-btn button-instagram-1 done",  # Instagram: no callback, done in the onclick
        "",
    ],
)
def test_everything_else_gets_the_short_settle(cls):
    """Three no-op Next clicks at 20s each spent a minute of a two-minute run."""
    assert judgment_module._settle_attempts(element(key="k", cls=cls)) == (
        judgment_module._FAST_SETTLE_ATTEMPTS
    )


def test_undone_is_matched_as_a_token_not_a_substring():
    """'done' is inside 'undone'; a naive check reads a finished action as still pending."""
    assert judgment_module._settle_attempts(element(key="k", cls="btn done")) == (
        judgment_module._FAST_SETTLE_ATTEMPTS
    )


@pytest.mark.asyncio
async def test_a_visible_element_wins_over_a_hidden_one_with_the_same_key():
    """find_element_by_key returns the first VISIBLE match, so the snapshot must describe it.

    Keeping the first in document order let a hidden element be described here and a
    different, visible one be clicked.
    """
    handler = make_handler()
    hidden = element(key="dupe", text="hidden", visible=False)
    shown = element(key="dupe", text="shown", visible=True)
    page = make_page([[hidden, shown]])

    snapshot = await handler._snapshot(page)
    assert snapshot["dupe"]["text"] == "shown"


@pytest.mark.asyncio
async def test_a_collision_is_warned_about_once_per_run(caplog):
    """_snapshot runs on every settle poll; a per-call warning buried the run in repeats."""
    handler = make_handler()
    pair = [element(key="dupe", step="follow", text="a"), element(key="dupe", step="follow")]
    page = make_page([pair])

    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            await handler._snapshot(page)

    assert caplog.text.count("share the key") == 1


def test_the_step_suffix_is_unique_bounded_and_selector_safe():
    """Two data-urls ending '/follow' must not collide, and a key reaches a CSS selector."""
    assert "const hash" in dom_snapshot.SNAPSHOT_JS
    assert "hash(sub)" in dom_snapshot.SNAPSHOT_JS
    assert "[^A-Za-z0-9._-]" in dom_snapshot.SNAPSHOT_JS
    assert ".slice(0, 24)" in dom_snapshot.SNAPSHOT_JS


def test_class_is_read_as_a_string_for_svg_anchors():
    """An SVG <a> matches 'a' but its className is an SVGAnimatedString, and every reader
    calls .lower().split() on it."""
    assert "typeof el.className === 'string'" in dom_snapshot.SNAPSHOT_JS


@pytest.mark.asyncio
async def test_a_caught_page_asset_is_not_taken_as_the_track(tmp_path):
    """Any popup can fire a download now, and taking one ends the run as DOWNLOAD_SUCCESS.

    resume.py then marks the track done forever, with the gate's follow and repost already
    spent — so a stylesheet must not count.
    """
    handler = make_handler(download_dir=tmp_path)
    handler._caught.append(fake_download(name="fontawesome-webfont.woff2"))

    assert await handler._take_caught_download() is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_an_extensionless_download_url_is_still_taken(tmp_path):
    """ToneDen serves the real file from /<uuid> with no extension and no content type."""
    handler = make_handler(download_dir=tmp_path)
    handler._caught.append(
        fake_download(
            name="LYES & IZZY VADIM - PRESSURE (STONED LEVEL EDIT).wav",
            url="https://io.toneden.io/523319/c971d7da-9975-4414-9a19-389a583c80ec",
        )
    )

    assert await handler._take_caught_download() is True


@pytest.mark.asyncio
async def test_a_popup_download_short_circuits_the_gate_page_wait():
    """The gate page's wait would otherwise run its full 45s for an event on another page."""
    handler = make_handler()
    handler._caught.append(fake_download())
    pending = asyncio.ensure_future(asyncio.sleep(3600))

    assert await handler._download_unless_a_popup_took_it(pending) is None
    with contextlib.suppress(asyncio.CancelledError):
        await pending
    assert pending.cancelled()


@pytest.mark.asyncio
async def test_the_gate_pages_own_download_is_still_returned():
    """Hypeddit serves the file from the gate page itself; that path must not change."""
    handler = make_handler()
    download = fake_download()

    async def arrives():
        return download

    assert (
        await handler._download_unless_a_popup_took_it(asyncio.ensure_future(arrives())) is download
    )


@pytest.mark.asyncio
async def test_waiting_ends_when_a_popup_download_arrives_late():
    """The popup fires after the click, not before it, so _caught starts empty."""
    handler = make_handler()

    async def land_later():
        await asyncio.sleep(0.05)
        handler._caught.append(fake_download())

    task = asyncio.ensure_future(land_later())
    pending = asyncio.ensure_future(asyncio.sleep(3600))
    assert await handler._download_unless_a_popup_took_it(pending) is None
    await task


@pytest.mark.asyncio
async def test_the_click_is_made_before_the_wait_is_raced():
    """Playwright waits for the event when expect_download's block EXITS, not at .value.

    Racing .value alone never got a turn until the full 45s had already been spent, so the
    click and the wait have to be raced together as one task.
    """
    handler = make_handler()
    clicked = asyncio.Event()

    async def click_then_hang():
        clicked.set()
        await asyncio.sleep(3600)

    pending = asyncio.ensure_future(click_then_hang())

    async def land_after_click():
        await clicked.wait()
        handler._caught.append(fake_download())

    task = asyncio.ensure_future(land_after_click())
    assert await handler._download_unless_a_popup_took_it(pending) is None
    assert clicked.is_set()
    await task


def _ctl(tag, *, onscreen=True, step="", visible=True, chrome=False):
    return {
        "tag": tag,
        "step": step,
        "cls": "",
        "visible": visible,
        "chrome": chrome,
        "onscreen": onscreen,
    }


def test_two_social_icons_on_the_sleeve_are_not_a_gate():
    """gaterush opens on the artwork, so the only things inside the viewport were the
    SoundCloud and Instagram links on the sleeve. _on_screen returned them because the set
    was non-empty, the fallback to the whole body never fired, and the gate below the fold
    was never offered — three turns of picking between two dead links, then StuckGate.
    """
    from soundcloud_dl.gate_handlers.judgment import _is_control, _on_screen

    snapshot = {
        "a@1": _ctl("a"),
        "a@2": _ctl("a"),
        "button@3": _ctl("button", onscreen=False),
    }
    assert not any(_is_control(el) for el in _on_screen(snapshot).values())
    assert _is_control(snapshot["button@3"])


def test_a_control_on_screen_needs_no_scrolling():
    from soundcloud_dl.gate_handlers.judgment import _is_control, _on_screen

    snapshot = {"a@1": _ctl("a"), "button@2": _ctl("button")}
    assert any(_is_control(el) for el in _on_screen(snapshot).values())


def test_a_data_step_element_counts_as_a_control_whatever_its_tag():
    """Gate actions are the thing we most need to see, and hypeddit spells them on <a>."""
    from soundcloud_dl.gate_handlers.judgment import _is_control

    assert _is_control(_ctl("a", step="follow"))
    assert not _is_control(_ctl("a"))


@pytest.mark.asyncio
async def test_a_declined_grant_ends_the_run_instead_of_looping():
    """gaterush asks for an account grant its handler will not approve. The model cannot
    know that, so it keeps choosing the control that asks — 22 turns reopening the same
    consent screen before the iteration cap ended the run with nothing.
    """
    from unittest.mock import MagicMock

    from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler
    from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered

    h = JudgmentGateHandler(config={"gate": "g", "steps": []})
    page = MagicMock()
    page.url = "https://gaterush.me/x"

    h._raise_if_consent_declined(page)  # no grant seen yet — must not raise

    h.consent_declined = True
    with pytest.raises(LoginWallEncountered) as exc:
        h._raise_if_consent_declined(page)
    assert "grant" in exc.value.reason


@pytest.mark.asyncio
async def test_the_turn_loop_is_what_checks_the_declined_grant():
    """Testing the method alone passes with the call site deleted — the wiring is the
    part that stops the loop.
    """
    from unittest.mock import MagicMock

    from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler
    from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered

    h = JudgmentGateHandler(config={"gate": "g", "steps": []})
    h.consent_declined = True
    page = MagicMock()
    page.url = "https://gaterush.me/x"

    with pytest.raises(LoginWallEncountered):
        await h._turn_guards(page, set(), None)


def test_leaving_a_consent_popup_open_is_what_sets_the_flag():
    """on_keep_open fires only when a consent popup is declined, so it is the exact
    signal — if that ever changes, the run stops on popups it should have ignored.
    """
    import inspect

    from soundcloud_dl.gate_handlers import oauth_popup

    src = inspect.getsource(oauth_popup)
    assert src.count("on_keep_open(") == 1, "on_keep_open is no longer decline-only"


@pytest.mark.asyncio
async def test_a_page_with_nothing_on_screen_does_not_reach_the_model(monkeypatch):
    """An empty choice list is a 400 that kills the run, so it must never be sent.

    valorizd renders every control off-screen. The turn has no criteria to offer, and the
    right answer is "no progress this turn", not an API error.
    """
    handler = JudgmentGateHandler(config={"gate": "valorizd", "steps": []})

    def _no_client():
        msg = "the model must not be reached when there is nothing to choose between"
        raise AssertionError(msg)

    monkeypatch.setattr(handler, "_get_client", _no_client)

    page = types.SimpleNamespace(url="https://www.valorizd.app/gates/x")

    assert await handler._ask_choice(page, {}) == ""


@pytest.mark.asyncio
async def test_a_gate_that_is_still_loading_is_waited_for_not_abandoned():
    """An idle turn does not sleep, so three of them pass in well under a second.

    valorizd serves a spinner and fetches its gate afterwards; without a wait the run gave
    up before the page had drawn anything at all.
    """
    handler = JudgmentGateHandler(config={"gate": "valorizd", "steps": []})
    waited: list[int] = []
    page = types.SimpleNamespace(
        url="https://www.valorizd.app/gates/x",
        wait_for_timeout=_as_async(waited.append),
    )
    # Empty while the spinner is up, then the real gate.
    rendered = _snap(_el("continue"))
    snapshots = [{}, {}, rendered]

    async def fake_snapshot(_page):
        return snapshots.pop(0)

    handler._snapshot = fake_snapshot

    assert await handler._wait_for_the_gate_to_render(page, {}, 1) == rendered
    assert waited, "the loading page was never waited on"


def _as_async(fn):
    async def inner(*a, **k):
        return fn(*a, **k)

    return inner


@pytest.mark.asyncio
async def test_the_loop_waits_for_a_late_rendering_gate_before_giving_up(monkeypatch):
    """Through _run_steps, not the helper: the wait is only worth anything if it is wired in.

    The page stays empty for longer than the three idle turns the loop allows, which is what
    a gate fetched after load looks like.
    """
    # A sentinel, because _TRANSITION_MS is also 1500 and "the loop waited 1500ms" would
    # not say which wait did it.
    monkeypatch.setattr(judgment_module, "_RENDER_WAIT_MS", 4242)
    waited: list[int] = []
    page = make_page([[]], found_element=None)

    async def record_wait(ms):
        waited.append(ms)

    page.wait_for_timeout = record_wait
    stub_choice(monkeypatch, [""])
    handler = make_handler()

    with contextlib.suppress(StuckGate):
        await handler._run_steps(page, {})

    assert 4242 in waited, "an empty page was never waited on — the gate is abandoned mid-load"


def test_on_screen_drops_what_a_dialog_covers():
    """pl8list opens a dialog over its page, and the page's own comment box behind it is
    what got filled — the dialog's continue stayed disabled and the run stalled."""
    offered = judgment_module._on_screen(
        _snap(_el("dialog_input"), _el("page_textarea", tag="textarea", covered=True))
    )
    assert set(offered) == {"dialog_input"}


def test_on_screen_keeps_covered_controls_rather_than_offering_nothing():
    offered = judgment_module._on_screen(_snap(_el("only_one", covered=True)))
    assert set(offered) == {"only_one"}


def test_share_your_thoughts_is_a_comment_field():
    handler = make_handler(template_vars={"comment": "fire", "email": "a@b.c", "name": "T"})
    field = _el("input@x", tag="input", placeholder="share your thoughts")
    assert handler._match_template_field(field) == "comment"


def test_a_covered_download_waits_like_an_off_screen_one():
    """Force-clicking a download under a dialog lands on the backdrop and closes it."""
    handler = make_handler()
    target, deferred = handler._defer_offscreen_download(_el("dl", covered=True), 1)
    assert target is None
    assert deferred == "dl"
    assert judgment_module._visible_download_key(_snap(_el("dl", covered=True))) is None


def test_a_cover_coming_or_going_is_not_the_page_moving():
    """A spinner or toast flipping `covered` must not read as progress, or the stuck-detector
    never fires."""
    before = _snap(_el("b", covered=False))
    after = _snap(_el("b", covered=True))
    assert judgment_module._same_page(before, after)
    assert not judgment_module._same_page(before, _snap(_el("b", text="changed")))


@pytest.mark.asyncio
async def test_a_download_click_that_navigates_ends_the_turn(tmp_path):
    """pl8list's download click led to Cloudflare or its sign-in page. Reading the stale
    button afterwards raised "Execution context was destroyed" and ended the whole run as a
    bare "Error" instead of letting the next turn see where the page had gone."""
    handler = make_handler(download_dir=tmp_path)
    handler.scroll_before_click = False
    handler._random_delay = AsyncMock()
    el = MagicMock()
    el.is_visible = AsyncMock(return_value=True)
    el.get_attribute = AsyncMock(side_effect=AssertionError("read a stale element"))
    handler._find_element_by_key = AsyncMock(return_value=el)
    page = MagicMock()
    page.url = "https://pl8list.com/finnuh/actin-up"

    async def click_that_navigates(_page, _el, _key):
        page.url = "https://pl8list.com/verify"
        msg = "Timeout 45000ms exceeded"
        raise TimeoutError(msg)

    handler._click_then_wait_for_download = click_that_navigates

    assert await handler._click_and_capture_download(page, "button@dl") is False


@pytest.mark.asyncio
async def test_a_download_that_errors_is_a_miss_not_a_crash():
    handler = make_handler()
    handler._maybe_pause = AsyncMock()
    handler._act = AsyncMock(side_effect=PlaywrightError("Execution context was destroyed"))
    results: dict = {}
    assert await handler._try_download(MagicMock(), results, _el("dl"), 1) is False


@pytest.mark.asyncio
async def test_a_closed_browser_still_ends_the_run_from_a_download():
    handler = make_handler()
    handler._maybe_pause = AsyncMock()
    handler._act = AsyncMock(
        side_effect=PlaywrightError("Target page, context or browser has been closed")
    )
    with pytest.raises(PlaywrightError):
        await handler._try_download(MagicMock(), {}, _el("dl"), 1)


@pytest.mark.asyncio
async def test_a_captcha_is_seen_before_the_run_is_dragged_back_to_the_gate():
    """A click that navigated onto a Cloudflare wall off the gate path was pulled back to
    the gate first, so the wall was never classified."""
    handler = make_handler()
    order: list[str] = []

    async def captcha(_page):
        order.append("captcha")
        raise CaptchaEncountered(CaptchaKind.TURNSTILE, handler.gate_name)

    async def reanchor(_page):
        order.append("reanchor")
        return False

    handler._raise_on_captcha = captcha
    handler._reanchor_page = reanchor
    handler._raise_on_login_wall = AsyncMock()
    handler._reanchor_scroll = AsyncMock()
    page = MagicMock()
    page.bring_to_front = AsyncMock()
    with pytest.raises(CaptchaEncountered):
        await handler._turn_guards(page, set(), None)
    assert order == ["captcha"]


@pytest.mark.asyncio
async def test_a_hash_change_is_not_the_download_click_navigating(tmp_path):
    """A single-page gate can set #fragment on click without leaving the page, and the href
    fallback after it is still reading a live button."""
    handler = make_handler(download_dir=tmp_path)
    handler.scroll_before_click = False
    handler._random_delay = AsyncMock()
    el = MagicMock()
    el.is_visible = AsyncMock(return_value=True)
    el.get_attribute = AsyncMock(return_value=None)
    handler._find_element_by_key = AsyncMock(side_effect=[el, None])
    page = MagicMock()
    page.url = "https://gate.example/track"
    page.wait_for_timeout = AsyncMock()

    async def click_that_sets_a_hash(_page, _el, _key):
        page.url = "https://gate.example/track#download"
        msg = "Timeout 45000ms exceeded"
        raise TimeoutError(msg)

    handler._click_then_wait_for_download = click_that_sets_a_hash

    await handler._click_and_capture_download(page, "button@dl")
    el.get_attribute.assert_awaited_once_with("href")


@pytest.mark.asyncio
async def test_a_clickable_download_is_tried_before_any_field_is_filled(monkeypatch, tmp_path):
    """pl8list's page has its own comment box next to its download button. Filling first
    typed the comment into the page instead of the dialog the download opens."""
    handler = make_handler(
        download_dir=tmp_path,
        template_vars={"email": "a@b.c", "name": "T", "comment": "fire"},
    )
    page_comment = element(key="el_body", tag="textarea", placeholder="add a comment...")
    field = make_element()
    page = make_page([[page_comment, READY_DOWNLOAD_LINK]], found_element=field)
    handler._click_and_capture_download = AsyncMock(return_value=True)
    stub_choice(monkeypatch, ["el_btn"] * 20)

    await handler._run_steps(page, {})

    handler._click_and_capture_download.assert_awaited()
    field.type.assert_not_awaited()
