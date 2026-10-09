import base64
import json

import httpx
import pytest

from soundcloud_dl import gmail_inbox
from soundcloud_dl.gmail_inbox import TextMessage, extract_link, pick_message, wait_for_text

# The body Google Voice forwarded for SPAG's drop, 2026-10-09.
SPAG_BODY = """<https://voice.google.com>
This is: SPAG. Here's your exclusive access to my flips and bootlegs!

https://www.dropbox.com/scl/fo/mhq70g6jprl3qn17l5o0s/ADaJiLppiZvXdLFzdeFbMYc?rlkey=la8rhae0awq05gtk5h5hq9pwv&dl=0
Msg frequency will vary. Msg&Data rates may apply. Reply HELP for help,
STOP to cancel
To respond to this text message, reply to this email or visit Google Voice.
YOUR ACCOUNT <https://voice.google.com> HELP CENTER
<https://support.google.com/voice#topic=1707989> HELP FORUM
<https://productforums.google.com/forum/#!forum/voice>
"""
SPAG_LINK = (
    "https://www.dropbox.com/scl/fo/mhq70g6jprl3qn17l5o0s/ADaJiLppiZvXdLFzdeFbMYc"
    "?rlkey=la8rhae0awq05gtk5h5hq9pwv&dl=0"
)
MMS_BODY = """<https://voice.google.com>
MMS Received
YOUR ACCOUNT <https://voice.google.com> HELP CENTER
<https://support.google.com/voice#topic=1707989> HELP FORUM
"""


def test_extract_link_takes_the_texted_link_not_the_footer():
    assert extract_link(SPAG_BODY) == SPAG_LINK


@pytest.mark.parametrize("body", [MMS_BODY, "", "no links here"])
def test_extract_link_none_without_a_real_link(body):
    assert extract_link(body) is None


VOICE = "(213) 474-8783 <13143120691.12134748783.bRS449@txt.voice.google.com>"
LAYLO_MAIL = "AG <hello@pro.laylo.com>"


def _msg(gmail_id, at_s, body=SPAG_BODY, sender=VOICE):
    return TextMessage(
        gmail_id=gmail_id,
        received_ms=int(at_s * 1000),
        subject="",
        body=body,
        from_address=sender,
    )


def test_pick_message_takes_the_oldest_fresh_text_with_a_link():
    msgs = [_msg("late", 1_000_050), _msg("mms", 1_000_001, MMS_BODY), _msg("first", 1_000_010)]
    assert pick_message(msgs, 1_000_000, set()).gmail_id == "first"


def test_pick_message_ignores_texts_from_before_the_submit():
    # internalDate is milliseconds; one second before the submit is too early.
    assert pick_message([_msg("old", 999_999)], 1_000_000, set()) is None


def test_pick_message_skips_a_text_another_drop_already_took():
    msgs = [_msg("taken", 1_000_005), _msg("ours", 1_000_020)]
    assert pick_message(msgs, 1_000_000, {"taken"}).gmail_id == "ours"


def _gmail_transport(messages):
    def encode(text):
        return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": m[0]} for m in messages]})
        gmail_id = request.url.path.rsplit("/", 1)[-1]
        mid, at_ms, body = next(m for m in messages if m[0] == gmail_id)
        payload = {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": "New text message from (213) 474-8783"},
                {"name": "From", "value": VOICE},
            ],
            "parts": [
                {"mimeType": "text/html", "body": {"data": encode("<p>html</p>")}},
                {"mimeType": "text/plain", "body": {"data": encode(body)}},
            ],
        }
        return httpx.Response(
            200, content=json.dumps({"id": mid, "internalDate": str(at_ms), "payload": payload})
        )

    return httpx.MockTransport(handler)


async def test_wait_for_text_decodes_the_plain_part(monkeypatch):
    monkeypatch.setattr(gmail_inbox, "load_gmail_access_token", lambda: "tok")
    transport = _gmail_transport([("m1", 1_000_010_000, SPAG_BODY)])
    got = await wait_for_text(1_000_000, set(), timeout_s=0, transport=transport)
    assert got is not None
    assert got.gmail_id == "m1"
    assert extract_link(got.body) == SPAG_LINK


async def test_wait_for_text_gives_up_when_nothing_arrives(monkeypatch):
    monkeypatch.setattr(gmail_inbox, "load_gmail_access_token", lambda: "tok")
    transport = _gmail_transport([("mms", 1_000_010_000, MMS_BODY)])
    assert await wait_for_text(1_000_000, set(), timeout_s=0, transport=transport) is None


def _from(gmail_id, number, body):
    return TextMessage(
        gmail_id=gmail_id,
        received_ms=1_000_010_000,
        subject=f"New text message from {number}",
        body=body,
        from_address=VOICE,
    )


def test_sender_is_the_digits_of_the_subject_number():
    assert _from("a", "(213) 474-8783", "").sender == "2134748783"


def test_a_stranger_texting_a_non_dropbox_link_is_not_laylo():
    spam = _from("spam", "(555) 000-0000", "You won! https://scam.example/claim")
    assert pick_message([spam], 1_000_000, set()) is None


def test_a_stranger_texting_a_dropbox_link_is_taken():
    new_drop = _from("new", "(555) 000-0000", f"This is: X. {SPAG_LINK}")
    assert pick_message([new_drop], 1_000_000, set()).gmail_id == "new"


def test_the_known_laylo_number_is_taken_whatever_host_it_links():
    drive = _from("lay", "(213) 474-8783", "This is: Y. https://drive.google.example/x")
    assert pick_message([drive], 1_000_000, set()).gmail_id == "lay"


CODE_BODY = "<https://voice.google.com>\nYour code is 292859 @laylo.com #292859\nYOUR ACCOUNT"


def test_extract_code_reads_laylos_code_text():
    from soundcloud_dl.gmail_inbox import extract_code

    assert extract_code(CODE_BODY) == "292859"
    # A code from anyone but Laylo is not Laylo's code.
    assert extract_code("Your code is 123456 for SomeBank") is None
    assert extract_code(SPAG_BODY) is None


def test_pick_code_takes_the_newest_code_since_the_submit():
    from soundcloud_dl.gmail_inbox import pick_code

    old = _msg("old", 999_990, CODE_BODY)
    first = _msg("first", 1_000_010, CODE_BODY)
    resend = _msg("resend", 1_000_040, CODE_BODY.replace("292859", "111111"))
    assert pick_code([old, first, resend], 1_000_000).gmail_id == "resend"
    assert pick_code([old], 1_000_000) is None


# Laylo's confirmation email for AG's drop, 2026-10-09 (HTML only; link trimmed).
AG_HTML = (
    "<p>Access confirmed. Your free download of Summit (AG Reboot) is available now: "
    '<a href="https://www.dropbox.com/scl/fo/ld86/ANW0?rlkey=bmf&amp;st=x&amp;dl=0">'
    "https://www.dropbox.com/scl/fo/ld86/ANW0?rlkey=bmf&amp;st=x&amp;dl=0</a></p>"
    '<a href="https://pro.laylo.com/unsubscribe?u=1">Unsubscribe</a>'
)


def test_the_email_body_is_read_from_html_with_entities_undone():
    import html

    from soundcloud_dl.gmail_inbox import email_download_link

    link = email_download_link(html.unescape(AG_HTML))
    assert link == "https://www.dropbox.com/scl/fo/ld86/ANW0?rlkey=bmf&st=x&dl=0"


def test_an_email_without_a_dropbox_link_is_not_taken():
    import html

    from soundcloud_dl.gmail_inbox import pick_email

    unsub_only = '<a href="https://pro.laylo.com/unsubscribe?u=1">Unsubscribe</a>'
    msgs = [
        _msg("promo", 1_000_005, unsub_only, LAYLO_MAIL),
        _msg("ag", 1_000_020, html.unescape(AG_HTML), LAYLO_MAIL),
    ]
    assert pick_email(msgs, 1_000_000, set()).gmail_id == "ag"
    assert pick_email(msgs, 1_000_000, {"ag"}) is None


async def test_the_search_reaches_into_trash(monkeypatch):
    monkeypatch.setattr(gmail_inbox, "load_gmail_access_token", lambda: "tok")
    seen = {}
    inner = _gmail_transport([("m1", 1_000_010_000, SPAG_BODY)])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            seen["trash"] = request.url.params.get("includeSpamTrash")
            seen["q"] = request.url.params.get("q")
        return inner.handle_request(request)

    await wait_for_text(1_000_000, set(), timeout_s=0, transport=httpx.MockTransport(handler))
    assert seen["trash"] == "true"
    # Trash in, spam out: spam is where Gmail files the spoofs.
    assert "-in:spam" in seen["q"]


@pytest.mark.parametrize(
    "sender",
    [
        # Gmail's from: search matches these too; the address is what counts.
        '"hello@laylo.com" <x@attacker.example>',
        "Laylo <hello@laylo.com.attacker.example>",
        "<hello@notlaylo.com>",
    ],
)
def test_an_email_not_from_laylo_is_never_taken(sender):
    import html

    from soundcloud_dl.gmail_inbox import pick_email

    spoof = _msg("spoof", 1_000_005, html.unescape(AG_HTML), sender)
    assert pick_email([spoof], 1_000_000, set()) is None


@pytest.mark.parametrize(
    "sender",
    ['"txt.voice.google.com" <x@attacker.example>', "<x@txt.voice.google.com.attacker.example>"],
)
def test_a_text_not_forwarded_by_google_voice_is_never_taken(sender):
    from soundcloud_dl.gmail_inbox import pick_code

    assert pick_message([_msg("spoof", 1_000_005, SPAG_BODY, sender)], 1_000_000, set()) is None
    assert pick_code([_msg("spoof", 1_000_005, CODE_BODY, sender)], 1_000_000) is None
