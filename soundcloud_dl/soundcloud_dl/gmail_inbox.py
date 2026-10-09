"""Read what Laylo sends after an RSVP, out of Gmail.

By email: a confirmation carrying the drop's link. By SMS: a verification code, then a text
with the link, both as Google Voice's forwarded copies.
"""

from __future__ import annotations

import asyncio
import base64
import html
import logging
import re
import time
from dataclasses import dataclass
from email.utils import parseaddr
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx

from soundcloud_dl.gmail_auth import GMAIL_API, load_gmail_access_token
from soundcloud_dl.laylo_drops import dropbox_direct

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("soundcloud_dl.gmail_inbox")

_VOICE_DOMAIN = "txt.voice.google.com"
# Narrowing only. Gmail's from: also matches the display name, so the address on each
# message is checked again by _sender_domain.
_QUERY_TEXTS = f"from:{_VOICE_DOMAIN}"
_QUERY_LAYLO_MAIL = "from:laylo.com"
# The number Laylo texted SPAG's link from. More are learned from drop records.
LAYLO_SENDERS = frozenset({"2134748783"})
_SUBJECT_NUMBER = re.compile(r"from\s+(.+)$", re.IGNORECASE)
# Laylo's code text ends "@laylo.com #<code>" (the WebOTP form), whatever number sends it.
_CODE = re.compile(r"Your code is (\d{4,8})\b.*@laylo\.com", re.DOTALL)
_URL = re.compile(r"https?://[^\s<>\"')\]]+")
# Gmail's `after:` is coarse and on its own clock; internalDate makes the precise cut.
_SEARCH_SLACK_S = 60


@dataclass(frozen=True)
class TextMessage:
    gmail_id: str
    received_ms: int
    subject: str
    body: str
    from_address: str = ""

    @property
    def sender(self) -> str:
        """The texting number's digits, off Google Voice's "New text message from …" subject."""
        found = _SUBJECT_NUMBER.search(self.subject)
        return re.sub(r"\D", "", found.group(1)) if found else ""

    @property
    def sender_domain(self) -> str:
        return parseaddr(self.from_address)[1].rpartition("@")[2].lower()


def _is_text(message: TextMessage) -> bool:
    return message.sender_domain == _VOICE_DOMAIN


def _is_laylo_mail(message: TextMessage) -> bool:
    domain = message.sender_domain
    return domain == "laylo.com" or domain.endswith(".laylo.com")


def extract_link(body: str) -> str | None:
    """The first link in a forwarded text that is not Google Voice's own footer."""
    for found in _URL.findall(body):
        url = found.rstrip(".,;!")
        host = (urlparse(url).hostname or "").lower()
        if host == "google.com" or host.endswith(".google.com"):
            continue
        return url
    return None


def extract_code(body: str) -> str | None:
    """The verification code in Laylo's code text, or None for any other text."""
    found = _CODE.search(body)
    return found.group(1) if found else None


def pick_code(messages: list[TextMessage], since_epoch: float) -> TextMessage | None:
    """The newest code text since the submit: a resend supersedes the code before it."""
    since_ms = int(since_epoch * 1000)
    codes = [
        m for m in messages if _is_text(m) and m.received_ms >= since_ms and extract_code(m.body)
    ]
    return max(codes, key=lambda m: m.received_ms, default=None)


def email_download_link(body: str) -> str | None:
    """The Dropbox link in Laylo's confirmation email, or None.

    Only Dropbox: the mail also links Laylo's own pages, unsubscribe and tracking.
    """
    for found in _URL.findall(body):
        url = found.rstrip(".,;!")
        if dropbox_direct(url) is not None:
            return url
    return None


def pick_email(
    messages: list[TextMessage], since_epoch: float, used_ids: set[str]
) -> TextMessage | None:
    """The oldest Laylo email since the RSVP that carries a Dropbox link and is not taken."""
    since_ms = int(since_epoch * 1000)
    fresh = [
        m
        for m in messages
        if _is_laylo_mail(m)
        and m.received_ms >= since_ms
        and m.gmail_id not in used_ids
        and email_download_link(m.body)
    ]
    return min(fresh, key=lambda m: m.received_ms, default=None)


def _from_laylo(message: TextMessage, senders: frozenset[str]) -> bool:
    # Every SMS to the number is forwarded, spam included. A known Laylo sender, or else a
    # Dropbox link (a new drop may text from a new number), makes a text Laylo's — and the
    # winner is written into the drop's record for good.
    link = extract_link(message.body)
    return link is not None and (message.sender in senders or dropbox_direct(link) is not None)


def pick_message(
    messages: list[TextMessage],
    since_epoch: float,
    used_ids: set[str],
    senders: frozenset[str] = LAYLO_SENDERS,
) -> TextMessage | None:
    """The oldest Laylo text that arrived after the submit and is not spoken for.

    used_ids is every message an earlier drop already took: a late text for one drop can
    land inside the next drop's window.
    """
    since_ms = int(since_epoch * 1000)
    fresh = [
        m
        for m in messages
        if _is_text(m)
        and m.received_ms >= since_ms
        and m.gmail_id not in used_ids
        and _from_laylo(m, senders)
    ]
    return min(fresh, key=lambda m: m.received_ms, default=None)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _plain_text(payload: dict[str, Any], mime: str = "text/plain") -> str:
    if payload.get("mimeType") == mime and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        if text := _plain_text(part, mime):
            return text
    return ""


def _body(payload: dict[str, Any]) -> str:
    # Laylo's emails are HTML only. Unescaped, not stripped: "&amp;" inside the href would
    # break the link's rlkey parameter.
    return _plain_text(payload) or html.unescape(_plain_text(payload, "text/html"))


def _header(payload: dict[str, Any], name: str) -> str:
    for header in payload.get("headers", []) or []:
        if header.get("name", "").lower() == name:
            return str(header.get("value", ""))
    return ""


async def _recent_texts(
    client: httpx.AsyncClient,
    since_epoch: float,
    query: str = _QUERY_TEXTS,
    seen: dict[str, TextMessage] | None = None,
) -> list[TextMessage]:
    """Messages matching query since since_epoch; seen caches bodies across polls."""
    seen = {} if seen is None else seen
    after = int(since_epoch) - _SEARCH_SLACK_S
    # Trash in, spam out: forwarded texts get binned within minutes, often before the run
    # reads them, while spam is where Gmail files the spoofs.
    params = {
        "q": f"{query} after:{after} -in:spam",
        "maxResults": 20,
        "includeSpamTrash": "true",
    }
    resp = await client.get(f"{GMAIL_API}/messages", params=params)
    resp.raise_for_status()
    found: list[TextMessage] = []
    for ref in resp.json().get("messages", []) or []:
        if ref["id"] not in seen:
            msg = await client.get(f"{GMAIL_API}/messages/{ref['id']}", params={"format": "full"})
            msg.raise_for_status()
            data = msg.json()
            payload = data.get("payload", {})
            seen[ref["id"]] = TextMessage(
                gmail_id=str(data["id"]),
                received_ms=int(data.get("internalDate", 0)),
                subject=_header(payload, "subject"),
                body=_body(payload),
                from_address=_header(payload, "from"),
            )
        found.append(seen[ref["id"]])
    return found


async def _poll(  # noqa: PLR0913
    since_epoch: float,
    pick: Callable[[list[TextMessage]], TextMessage | None],
    what: str,
    *,
    timeout_s: float,
    poll_s: float,
    transport: httpx.AsyncBaseTransport | None,
    query: str = _QUERY_TEXTS,
) -> TextMessage | None:
    deadline = time.monotonic() + timeout_s
    seen: dict[str, TextMessage] = {}
    async with httpx.AsyncClient(timeout=30.0, transport=transport) as client:
        while True:
            token = await asyncio.to_thread(load_gmail_access_token)
            client.headers["Authorization"] = f"Bearer {token}"
            picked = pick(await _recent_texts(client, since_epoch, query, seen))
            if picked is not None:
                logger.info("laylo %s arrived (gmail id %s)", what, picked.gmail_id)
                return picked
            if time.monotonic() >= deadline:
                logger.warning("no laylo %s arrived within %ds", what, int(timeout_s))
                return None
            await asyncio.sleep(poll_s)


async def wait_for_code(
    since_epoch: float,
    *,
    timeout_s: float = 180.0,
    poll_s: float = 5.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str | None:
    """Poll Gmail for Laylo's verification code sent after since_epoch, or give up."""
    picked = await _poll(
        since_epoch,
        lambda msgs: pick_code(msgs, since_epoch),
        "code",
        timeout_s=timeout_s,
        poll_s=poll_s,
        transport=transport,
    )
    return None if picked is None else extract_code(picked.body)


async def wait_for_text(  # noqa: PLR0913
    since_epoch: float,
    used_ids: set[str],
    senders: frozenset[str] = LAYLO_SENDERS,
    *,
    timeout_s: float = 180.0,
    poll_s: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TextMessage | None:
    """Poll Gmail until a text with a link arrives after since_epoch, or give up."""
    return await _poll(
        since_epoch,
        lambda msgs: pick_message(msgs, since_epoch, used_ids, senders),
        "text with a link",
        timeout_s=timeout_s,
        poll_s=poll_s,
        transport=transport,
    )


async def wait_for_email(
    since_epoch: float,
    used_ids: set[str],
    *,
    timeout_s: float = 180.0,
    poll_s: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TextMessage | None:
    """Poll Gmail for Laylo's confirmation email carrying the link, or give up."""
    return await _poll(
        since_epoch,
        lambda msgs: pick_email(msgs, since_epoch, used_ids),
        "email with a link",
        timeout_s=timeout_s,
        poll_s=poll_s,
        transport=transport,
        query=_QUERY_LAYLO_MAIL,
    )
