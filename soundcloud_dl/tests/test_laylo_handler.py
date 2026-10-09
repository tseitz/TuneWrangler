import asyncio
import time

import pytest

from soundcloud_dl import laylo_drops
from soundcloud_dl.gate_handlers import laylo as laylo_mod
from soundcloud_dl.gate_handlers.jev import JevHandler
from soundcloud_dl.gate_handlers.laylo import LayloHandler
from soundcloud_dl.gmail_inbox import TextMessage
from soundcloud_dl.main import gate_template_vars

DROP = "https://laylo.com/spagheddy/flips"
KEY = "laylo.com/spagheddy/flips"
LINK = "https://www.dropbox.com/scl/fo/abc/def?rlkey=k&dl=0"
NOW = time.time()
PHONE = "+15550001111"
GMAIL = "me@gmail.example"


class _Toggle:
    """Laylo's "RSVP by EMAIL" button."""

    def __init__(self):
        self.clicked = False

    async def is_visible(self):
        return True

    async def get_attribute(self, _name):
        return "true" if self.clicked else "false"

    async def click(self):
        self.clicked = True


class _Page:
    url = DROP

    def on(self, event, handler):
        self.listeners = {**getattr(self, "listeners", {}), event: handler}

    def remove_listener(self, event, _handler):
        getattr(self, "listeners", {}).pop(event, None)

    def __init__(self, *, offers_email=False):
        self.toggle = _Toggle() if offers_email else None

    async def query_selector(self, selector):
        return self.toggle if "RSVP by EMAIL" in selector else None

    async def wait_for_selector(self, *_a, **_k):
        return None

    async def wait_for_timeout(self, _ms):
        return None


def _button(text, tag="button", kind="submit"):
    return {"key": "k", "tag": tag, "text": text, "href": "", "type": kind}


def _handler(**kwargs):
    kwargs.setdefault("template_vars", {"phone": PHONE, "email": GMAIL})
    return LayloHandler(**kwargs)


def test_laylo_gets_its_own_contacts_and_nothing_else(monkeypatch):
    monkeypatch.setattr("soundcloud_dl.main.DOWNLOAD_PHONE", PHONE)
    monkeypatch.setattr("soundcloud_dl.main.LAYLO_EMAIL", GMAIL)
    monkeypatch.setattr("soundcloud_dl.main.DOWNLOAD_EMAIL", "gates@outlook.example")
    assert gate_template_vars(LayloHandler) == {"phone": PHONE, "email": GMAIL}
    others = gate_template_vars(JevHandler)
    assert "phone" not in others
    assert others["email"] == "gates@outlook.example"


def test_an_unset_contact_is_left_out(monkeypatch):
    monkeypatch.setattr("soundcloud_dl.main.DOWNLOAD_PHONE", "")
    monkeypatch.setattr("soundcloud_dl.main.LAYLO_EMAIL", GMAIL)
    assert gate_template_vars(LayloHandler) == {"email": GMAIL}


async def test_email_wins_where_the_drop_offers_it():
    page = _Page(offers_email=True)
    handler = _handler()
    assert await handler._choose_channel(page) == "email"
    assert page.toggle.clicked
    # The number is withheld: nothing on the page can be filled with it now.
    assert handler.template_vars == {"email": GMAIL}


async def test_phone_is_the_fallback_on_an_sms_only_drop():
    handler = _handler()
    assert await handler._choose_channel(_Page()) == "sms"
    assert handler.template_vars == {"phone": PHONE}


async def test_an_sms_only_drop_without_a_phone_is_left_for_review():
    handler = _handler(template_vars={"email": GMAIL})
    await handler.run(_Page())
    assert "no contact set" in handler.review_reason
    assert laylo_drops.load(KEY) is None


async def test_the_capture_path_never_takes_the_rsvp_button(monkeypatch):
    from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler

    async def would_capture(*_a, **_k):
        return "k", "got_it"

    # The parent would take Laylo's "Download" button as the file; the override must not ask.
    monkeypatch.setattr(JudgmentGateHandler, "_maybe_download", would_capture)
    handler = _handler()
    assert await handler._maybe_download(None, {}, {}, 1) == (None, "not_ready")
    assert handler._action_kind(_button("Download"), download_key="k") == "click"


async def test_only_the_submit_button_counts_as_the_submit(monkeypatch):
    async def none(_page):
        return None

    monkeypatch.setattr(laylo_mod, "detect_captcha", none)
    handler = _handler()
    assert not await handler._form_submitted(_Page(), _button("RSVP by SMS", kind="button"))
    assert not await handler._form_submitted(_Page(), {**_button("Download"), "disabled": True})
    assert handler._submitted_at is None
    assert await handler._form_submitted(_Page(), _button("RSVP"))
    assert handler._submitted_at is not None


def _submits(monkeypatch, calls, *, code_problem=None, ack="code"):
    async def fake_run(self, _page):
        calls.append(1)
        self._submitted_at = NOW
        return {}

    async def fake_code(self, _page):
        return code_problem

    async def typed(self, _page, _channel):
        return None

    async def acked(self):
        return ack

    monkeypatch.setattr(JevHandler, "run", fake_run)
    monkeypatch.setattr(LayloHandler, "_enter_code", fake_code)
    monkeypatch.setattr(LayloHandler, "_type_contact", typed)
    monkeypatch.setattr(LayloHandler, "_await_ack", acked)


async def test_a_phone_rsvp_is_recorded_once_its_code_is_accepted(monkeypatch):
    _submits(monkeypatch, [])

    async def boom(*_a, **_k):
        msg = "gmail down"
        raise RuntimeError(msg)

    monkeypatch.setattr(laylo_mod, "wait_for_text", boom)
    with pytest.raises(RuntimeError):
        await _handler().run(_Page())
    record = laylo_drops.load(KEY)
    assert record.submitted_at == NOW
    assert record.channel == "sms"


async def test_a_phone_rsvp_whose_code_never_came_is_not_recorded(monkeypatch):
    _submits(monkeypatch, [], code_problem="laylo: the verification code never arrived")
    handler = _handler()
    await handler.run(_Page())
    assert "code never arrived" in handler.review_reason
    # Unrecorded on purpose: the number is not signed up until a code is accepted.
    assert laylo_drops.load(KEY) is None


async def test_an_email_rsvp_is_recorded_at_once_and_reads_the_email(monkeypatch, tmp_path):
    _submits(monkeypatch, [], code_problem="must not be asked for a code", ack="rsvp")
    # As gmail_inbox hands it over: the HTML with its entities already undone.
    mail = f'<p>Access confirmed. <a href="{LINK}">{LINK}</a></p>'

    async def email(*_a, **_k):
        return TextMessage(gmail_id="e1", received_ms=0, subject="You're confirmed", body=mail)

    async def no_text(*_a, **_k):
        raise AssertionError

    folder = tmp_path / "drop"
    folder.mkdir()

    async def fetch(_link, _slug):
        return folder

    monkeypatch.setattr(laylo_mod, "wait_for_email", email)
    monkeypatch.setattr(laylo_mod, "wait_for_text", no_text)
    monkeypatch.setattr(laylo_drops, "fetch", fetch)
    handler = _handler(track_title="EPTIC - OCTANE (SPAG FLIP)")
    await handler.run(_Page(offers_email=True))
    record = laylo_drops.load(KEY)
    assert record.channel == "email"
    assert record.link == LINK
    assert record.gmail_id == "e1"


async def test_a_submitted_drop_is_never_rsvped_again(monkeypatch):
    laylo_drops.save(KEY, laylo_drops.DropRecord(submitted_at=NOW, channel="sms"))
    calls = []
    _submits(monkeypatch, calls)

    async def no_text(*_a, **_k):
        return None

    monkeypatch.setattr(laylo_mod, "wait_for_text", no_text)
    handler = _handler()
    await handler.run(_Page())
    assert calls == []
    assert "next run" in handler.review_reason
    assert not handler.downloaded


async def test_a_matching_file_in_the_texted_folder_is_the_download(monkeypatch, tmp_path):
    _submits(monkeypatch, [])
    body = f"This is: SPAG.\n{LINK}\n"

    async def text(*_a, **_k):
        return TextMessage(gmail_id="m1", received_ms=1_000_500, subject="", body=body)

    folder = tmp_path / "drop"
    folder.mkdir()
    (folder / "EPTIC - OCTANE (SPAG FLIP).wav").write_bytes(b"RIFF....WAVE")

    async def fetch(_link, _slug):
        return folder

    monkeypatch.setattr(laylo_mod, "wait_for_text", text)
    monkeypatch.setattr(laylo_drops, "fetch", fetch)
    monkeypatch.setattr(laylo_drops, "save_dir", lambda: tmp_path / "out")
    (tmp_path / "out").mkdir()

    handler = _handler(track_title="EPTIC - OCTANE (SPAG FLIP)")
    await handler.run(_Page())
    assert handler.downloaded, handler.review_reason
    record = laylo_drops.load(KEY)
    assert record.gmail_id == "m1"
    assert record.link == LINK
    assert record.folder == str(folder)


async def test_a_drop_of_one_file_is_the_track_whatever_its_name(monkeypatch, tmp_path):
    single = "https://www.dropbox.com/scl/fi/abc/WANNACRY-FLOZONE-FLIP.wav?rlkey=k&dl=0"
    laylo_drops.save(KEY, laylo_drops.DropRecord(submitted_at=NOW, channel="sms", link=single))
    folder = tmp_path / "drop"
    folder.mkdir()
    (folder / "WANNACRY-FLOZONE-FLIP.wav").write_bytes(b"RIFF....WAVE")

    async def fetch(_link, _slug):
        return folder

    monkeypatch.setattr(laylo_drops, "fetch", fetch)
    monkeypatch.setattr(laylo_drops, "save_dir", lambda: tmp_path / "out")
    (tmp_path / "out").mkdir()
    handler = _handler(track_title="FLOZONE - ninajirachi x porter robinson - WANNACRY")
    await handler.run(_Page())
    assert handler.downloaded, handler.review_reason


class _At:
    def __init__(self, url):
        self.url = url


_PHONE_FIELD = {"tag": "input", "name": "phone", "id": "p", "placeholder": "Your number"}
_EMAIL_FIELD = {"tag": "input", "name": "email", "id": "e", "placeholder": "Your email"}


@pytest.mark.parametrize(
    ("url", "on_laylo"),
    [
        ("https://laylo.com/spagheddy/flips", True),
        ("https://www.laylo.com/a/b", True),
        ("https://evil.example/?ref=laylo.com", False),
        ("https://laylo.com.evil.example/x", False),
    ],
)
@pytest.mark.parametrize(("field", "var"), [(_PHONE_FIELD, "phone"), (_EMAIL_FIELD, "email")])
def test_contacts_are_only_typed_on_laylo(url, on_laylo, field, var):
    handler = _handler()
    handler._page = _At(url)
    assert handler._match_template_field(field) == (var if on_laylo else None)


def test_a_typed_number_is_masked_in_what_jev_is_sent():
    handler = _handler()
    field = {**_PHONE_FIELD, "text": "+1 555 000 1111"}
    assert handler._redact(field)["text"] == "<filled>"
    assert handler._redact({**_PHONE_FIELD, "text": ""})["text"] == ""
    button = {"tag": "button", "text": "+1 555 000 1111"}
    assert handler._redact(button) is button


async def test_a_drop_stops_polling_a_day_after_the_rsvp(monkeypatch):
    laylo_drops.save(KEY, laylo_drops.DropRecord(submitted_at=1_000.0))

    async def never(*_a, **_k):
        raise AssertionError

    monkeypatch.setattr(laylo_mod, "wait_for_text", never)
    handler = _handler()
    await handler.run(_Page())
    assert "24h" in handler.review_reason


async def test_a_challenge_after_the_click_records_nothing(monkeypatch):
    from soundcloud_dl.gate_handlers.captcha import (
        CaptchaEncountered,
        CaptchaKind,
    )

    async def fake_run(self, page):
        await self._form_submitted(page, _button("Download"))
        return {}

    async def challenged(_page):
        return CaptchaKind.RECAPTCHA

    async def typed(self, _page, _channel):
        return None

    monkeypatch.setattr(JevHandler, "run", fake_run)
    monkeypatch.setattr(LayloHandler, "_type_contact", typed)
    monkeypatch.setattr(laylo_mod, "detect_captcha", challenged)
    with pytest.raises(CaptchaEncountered):
        await _handler().run(_Page())
    assert laylo_drops.load(KEY) is None


async def test_a_folder_of_several_unmatched_files_is_left_for_review(monkeypatch, tmp_path):
    laylo_drops.save(KEY, laylo_drops.DropRecord(submitted_at=NOW, channel="sms", link=LINK))
    folder = tmp_path / "drop"
    folder.mkdir()
    (folder / "one.wav").write_bytes(b"RIFF....WAVE")
    (folder / "two.wav").write_bytes(b"RIFF....WAVE")

    async def fetch(_link, _slug):
        return folder

    monkeypatch.setattr(laylo_drops, "fetch", fetch)
    handler = _handler(track_title="SPAG - SOMETHING ELSE")
    await handler.run(_Page())
    assert not handler.downloaded
    assert "folder kept" in handler.review_reason


async def test_a_code_with_nowhere_to_enter_it_is_reported(monkeypatch):
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    class _NoCodeScreen(_Page):
        async def wait_for_selector(self, *_a, **_k):
            msg = "no code boxes"
            raise PlaywrightTimeoutError(msg)

    handler = _handler()
    handler._submitted_at = NOW
    assert "nowhere to enter it" in await handler._enter_code(_NoCodeScreen())


class _Field:
    def __init__(self, *, keeps=True):
        self.value = "+1 314 312 0000"  # what the page restored: someone else's number
        self.keeps = keeps

    async def fill(self, text):
        self.value = text

    async def type(self, text, delay=0):
        if self.keeps:
            self.value += text

    async def input_value(self):
        return self.value

    async def evaluate(self, _script):
        return self.page_url


class _FormPage(_Page):
    def __init__(self, field, url=DROP, field_url=None):
        super().__init__()
        self.field = field
        self.url = url
        field.page_url = field_url or url

    async def wait_for_selector(self, *_a, **_k):
        return self.field


async def test_the_contact_replaces_whatever_the_page_restored():
    field = _Field()
    handler = _handler()
    assert await handler._type_contact(_FormPage(field), "sms") is None
    assert field.value == PHONE


async def test_a_field_that_drops_the_typing_is_reported():
    handler = _handler()
    problem = await handler._type_contact(_FormPage(_Field(keeps=False)), "sms")
    assert "did not keep" in problem


async def test_nothing_is_typed_once_the_page_has_left_laylo():
    field = _Field()
    handler = _handler()
    problem = await handler._type_contact(_FormPage(field, url="https://evil.example/x"), "sms")
    assert "left laylo.com" in problem
    assert field.value != PHONE


async def test_an_rsvp_laylo_never_acknowledged_is_not_recorded(monkeypatch):
    _submits(monkeypatch, [], ack=None)
    handler = _handler()
    await handler.run(_Page())
    assert "never acknowledged" in handler.review_reason
    assert laylo_drops.load(KEY) is None


async def test_a_known_number_is_accepted_without_a_code(monkeypatch):
    _submits(monkeypatch, [], code_problem="must not be asked for a code", ack="rsvp")

    async def no_text(*_a, **_k):
        return None

    monkeypatch.setattr(laylo_mod, "wait_for_text", no_text)
    handler = _handler()
    await handler.run(_Page())
    assert laylo_drops.load(KEY).channel == "sms"
    assert "next run" in handler.review_reason


class _Resp:
    def __init__(self, url, body):
        self.url = url
        self._body = body

    async def text(self):
        return self._body


@pytest.mark.parametrize(
    ("responses", "ack"),
    [
        ([("https://laylo.com/api/graphql", '{"body":"Code added to request for key x"}')], "code"),
        ([("https://events.laylo.com/actions/rsvp/rsvp", '{"success": true}')], "rsvp"),
        (
            [
                ("https://events.laylo.com/actions/rsvp/rsvp", '{"success":true}'),
                ("https://laylo.com/api/graphql", "Code added to request"),
            ],
            "code",
        ),
        ([("https://evil.example/rsvp", '{"success":true}')], None),
        ([("https://events.laylo.com/actions/rsvp/rsvp", '{"success":false}')], None),
    ],
)
async def test_lay_los_answer_decides_what_follows_the_click(responses, ack):
    handler = _handler()
    handler._armed = True
    for url, body in responses:
        handler._on_response(_Resp(url, body))
    for read in handler._ack_reads:
        await read
    assert handler._ack == ack


async def test_nothing_is_typed_into_a_field_that_has_left_laylo():
    # The page passed the host check, then navigated while the field was awaited.
    field = _Field()
    page = _FormPage(field, field_url="https://evil.example/form")
    problem = await _handler()._type_contact(page, "sms")
    assert "left laylo.com" in problem
    assert field.value != PHONE


async def test_an_answer_from_before_the_click_is_ignored():
    handler = _handler()
    handler._on_response(_Resp("https://events.laylo.com/actions/rsvp/rsvp", '{"success":true}'))
    assert handler._ack_reads == []


async def test_a_code_that_follows_an_accepted_rsvp_still_gets_entered(monkeypatch):
    """The wiring end to end: page listener, both answers, and the code step after them."""
    entered = []

    async def fake_run(self, page):
        self._armed = True
        await self._form_submitted(page, _button("Download"))
        listener = page.listeners["response"]
        listener(_Resp("https://events.laylo.com/actions/rsvp/rsvp", '{"success":true}'))

        async def late_code():
            await asyncio.sleep(0.05)
            listener(_Resp("https://laylo.com/api/graphql", "Code added to request for key k"))

        self._late = asyncio.create_task(late_code())
        return {}

    async def no_captcha(_page):
        return None

    async def typed(self, _page, _channel):
        return None

    async def enter(self, _page):
        entered.append(1)

    async def no_text(*_a, **_k):
        return None

    monkeypatch.setattr(JevHandler, "run", fake_run)
    monkeypatch.setattr(LayloHandler, "_type_contact", typed)
    monkeypatch.setattr(LayloHandler, "_enter_code", enter)
    monkeypatch.setattr(laylo_mod, "detect_captcha", no_captcha)
    monkeypatch.setattr(laylo_mod, "wait_for_text", no_text)
    monkeypatch.setattr(laylo_mod, "_CHALLENGE_WAIT_MS", 0)
    page = _Page()
    await _handler().run(page)
    assert entered == [1]
    assert laylo_drops.load(KEY) is not None
    assert "response" not in page.listeners
