"""Unit tests for JudgmentGateHandler's decision logic (judgment.py).

Mocks the Choice call's return value rather than hitting the real API — only the real
browser + real paid API call stay manual-only (see the plan's Verify section).
"""

import asyncio
import contextlib
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl.downloads import MIN_TRACK_BYTES
from soundcloud_dl.gate_handlers import dom_snapshot
from soundcloud_dl.gate_handlers.base import StepResult, StuckGate
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, CaptchaKind
from soundcloud_dl.gate_handlers import judgment as judgment_module
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
    assert handler._match_template_field(el) == expected  # noqa: SLF001


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
    desc = handler._describe(box)  # noqa: SLF001
    assert "type='checkbox'" in desc
    assert "checked=False" in desc


def test_describe_omits_checked_for_things_that_cannot_be_checked():
    handler = make_handler()
    btn = {"tag": "button", "text": "Continue", "cls": "", "href": "", "type": "", "checked": False}
    assert "checked=" not in handler._describe(btn)  # noqa: SLF001


def test_snapshot_offers_the_label_that_wraps_a_styled_checkbox():
    """droploud hides the real input (display:none, 0x0) inside a visible <label>.

    The input fails isVisible and is never offered, so the label is the only thing that
    can be clicked — and clicking it toggles the input natively.
    """
    assert "label" in dom_snapshot._SELECTOR  # noqa: SLF001
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
    offered = judgment_module._on_screen(  # noqa: SLF001
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
    offered = judgment_module._on_screen(_snap(_el("header_dl", chrome=True)))  # noqa: SLF001
    assert set(offered) == {"header_dl"}


def test_on_screen_falls_back_when_the_whole_gate_is_off_screen():
    offered = judgment_module._on_screen(_snap(_el("gate_dl", onscreen=False)))  # noqa: SLF001
    assert set(offered) == {"gate_dl"}


def test_on_screen_tolerates_elements_without_the_new_fields():
    """Hand-built elements elsewhere in these tests carry neither field."""
    bare = {"key": "b", "visible": True}
    assert set(judgment_module._on_screen({"b": bare})) == {"b"}  # noqa: SLF001


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

    assert await handler._download_unless_a_popup_took_it(
        asyncio.ensure_future(arrives())
    ) is download


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
