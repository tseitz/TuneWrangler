"""Laylo: RSVP by email where the drop offers it, else by phone; then fetch the sent link.

The page never serves a file. Laylo mails or texts the link (by phone, after a texted code
for a number it has not seen), and gmail_inbox reads it out of Gmail.

A drop is recorded once its RSVP is final, and every later step resumes from that record:
a second RSVP would sign the address up twice.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from soundcloud_dl import laylo_drops
from soundcloud_dl.downloads import _AUDIO_EXTS
from soundcloud_dl.gate_handlers import is_laylo_host
from soundcloud_dl.gate_handlers.base import StepResult, StuckGate
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, CaptchaKind, detect_captcha
from soundcloud_dl.gate_handlers.jev import JevHandler
from soundcloud_dl.gmail_inbox import (
    LAYLO_SENDERS,
    email_download_link,
    extract_link,
    wait_for_code,
    wait_for_email,
    wait_for_text,
)

if TYPE_CHECKING:
    from playwright.async_api import Page, Response

    from soundcloud_dl.gate_handlers.judgment import _DownloadOutcome

logger = logging.getLogger("soundcloud_dl.gate_handlers.laylo")

_GOALS = {
    "sms": (
        "This is a Laylo drop page. Get the free download by RSVPing with a phone number: "
        "keep 'RSVP by SMS' selected, make sure the phone number field holds the number, then "
        "press the submit button ('Download' or 'RSVP') once. Never choose 'RSVP by EMAIL', "
        "'Make a drop like this', 'Share', the Laylo logo, or anything that signs in or "
        "creates an account."
    ),
    "email": (
        "This is a Laylo drop page. Get the free download by RSVPing with an email address: "
        "keep 'RSVP by EMAIL' selected, make sure the email field holds the address, then "
        "press the submit button ('Download' or 'RSVP') once. Never choose 'RSVP by SMS', "
        "'Make a drop like this', 'Share', the Laylo logo, or anything that signs in or "
        "creates an account."
    ),
}
_TOGGLE = {"sms": '[aria-label="RSVP by SMS"]', "email": '[aria-label="RSVP by EMAIL"]'}
_CONTACT_FIELD = {"sms": 'input[type="tel"][name="phone"]', "email": 'input[name="email"]'}
_CHANNEL_VAR = {"sms": "phone", "email": "email"}
# The six one-digit code boxes. The phone box can still be on screen mid-transition.
_CODE_BOX = ", ".join(
    f'input{attr}:not([name="phone"])'
    for attr in ('[autocomplete="one-time-code"]', '[inputmode="numeric"]', '[name*="code" i]')
)

# The click lands a moment before the hook sees it, and Gmail can stamp a text just ahead of
# our clock.
_CLOCK_SLACK_S = 5.0
_ELEMENT_WAIT_MS = 10_000
_TOGGLE_SETTLE_MS = 1500
# Long enough for the page to restore a remembered number before it is overwritten.
_FORM_SETTLE_MS = 2000
_CHALLENGE_WAIT_MS = 3000
_ACK_WAIT_S = 10.0
_ACK_DRAIN_S = 3.0
_CODE_ACCEPT_WAIT_MS = 15_000
# Past this a message is more likely spam than Laylo's; --laylo-forget RSVPs again.
_LINK_WINDOW_S = 24 * 3600


def _is_submit_button(target: dict[str, Any]) -> bool:
    if target["tag"] != "button":
        return False
    return target.get("type") == "submit" or target["text"].strip().lower() in {"download", "rsvp"}


def _is_ack_response(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    on_laylo = host == "laylo.com" or host.endswith(".laylo.com")
    return on_laylo and (parsed.path.endswith("/graphql") or "/rsvp" in parsed.path)


class LayloHandler(JevHandler):
    """Jev drives the RSVP form; the download comes from the link Laylo sends afterwards."""

    gate_slug = "laylo_jev"
    #: Read by main.gate_template_vars: this gate gets the Laylo contacts and no SC actions.
    rsvp_gate = True

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        kwargs.setdefault("goal", _GOALS["sms"])
        super().__init__(**kwargs)
        self.review_reason: str | None = None
        self._submitted_at: float | None = None
        self._page: Page | None = None
        self._captcha_after_submit: CaptchaKind | None = None
        #: Laylo's answer to the RSVP: "code" (texted a code) or "rsvp" (accepted as is).
        self._ack: str | None = None
        self._ack_reads: list[asyncio.Task[None]] = []
        self._acked = asyncio.Event()
        self._code_asked = asyncio.Event()
        # Set as the submit is clicked: an answer from before it is not to this RSVP.
        self._armed = False
        # Captured before _choose_channel narrows template_vars: the page can restore the
        # other channel's contact into a field, and it must stay masked all the same.
        self._contacts = [v for k, v in self.template_vars.items() if k in _CHANNEL_VAR.values()]

    def _typed_values(self) -> list[str]:
        return [*super()._typed_values(), *self._contacts]

    async def _on_laylo(self, el: Any) -> bool:  # noqa: ANN401
        # The element's own document, checked just before typing: a page that navigated
        # since the last check resolves selectors against the new site.
        host = await el.evaluate("e => e.ownerDocument.location.href")
        return is_laylo_host(str(host))

    def _on_response(self, response: Response) -> None:
        # Laylo's API is the only reliable witness: the page reads "Check your texts"
        # whether the RSVP went through, needs a code, or was silently dropped.
        if self._armed and _is_ack_response(response.url):
            self._ack_reads.append(asyncio.create_task(self._read_ack(response)))

    async def _read_ack(self, response: Response) -> None:
        try:
            body = await response.text()
        except (PlaywrightError, UnicodeDecodeError):
            logger.debug("[%s] unreadable %s", self.gate_name, response.url, exc_info=True)
            return
        if "Code added to request" in body:
            self._ack = "code"
            self._code_asked.set()
        elif "/rsvp" in response.url and '"success":true' in body.replace(" ", ""):
            self._ack = self._ack or "rsvp"
        else:
            return
        self._acked.set()

    async def _await_ack(self) -> str | None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._acked.wait(), _ACK_WAIT_S)
        # Both answers can come back for one click. "code" must win over an "rsvp" that
        # landed first, or the code is never typed and the drop waits on a link for good.
        if self._ack == "rsvp":
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._code_asked.wait(), _ACK_DRAIN_S)
        return self._ack

    def _match_template_field(self, el: dict[str, Any]) -> str | None:
        # Every fill asks this. The class was picked from the URL before the page loaded,
        # and a redirect or a clicked link can move the page anywhere.
        var_key = super()._match_template_field(el)
        on_laylo = self._page is not None and is_laylo_host(self._page.url)
        if var_key in ("phone", "email") and not on_laylo:
            return None
        return var_key

    async def _maybe_download(
        self,
        page: Page,  # noqa: ARG002
        snapshot: dict[str, dict[str, Any]],  # noqa: ARG002
        results: dict[str, StepResult],  # noqa: ARG002
        i: int,  # noqa: ARG002
    ) -> tuple[str | None, _DownloadOutcome]:
        # The submit button reads "Download". The capture path would take it for the file,
        # click it again by script and retry, and every one of those clicks is an RSVP.
        return None, "not_ready"

    def _action_kind(self, target: dict[str, Any], *, download_key: str | None) -> str:
        kind = super()._action_kind(target, download_key=download_key)
        return "click" if kind == "download" else kind

    async def _act(self, page: Page, kind: str, target: dict[str, Any]) -> tuple[StepResult, bool]:
        if _is_submit_button(target) and not target.get("disabled"):
            self._armed = True
        return await super()._act(page, kind, target)

    async def _form_submitted(self, page: Page, target: dict[str, Any]) -> bool:
        # A disabled submit does nothing when clicked.
        if not _is_submit_button(target) or target.get("disabled"):
            return False
        self._submitted_at = time.time() - _CLOCK_SLACK_S
        await page.wait_for_timeout(_CHALLENGE_WAIT_MS)
        self._captcha_after_submit = await detect_captcha(page)
        logger.info("[%s] RSVP submitted", self.gate_name)
        return True

    async def _enter_code(self, page: Page) -> str | None:
        """Type the texted code in. Returns why it could not be, or None once accepted."""
        assert self._submitted_at is not None  # noqa: S101
        try:
            await page.wait_for_selector(_CODE_BOX, state="visible", timeout=_ELEMENT_WAIT_MS)
        except PlaywrightTimeoutError:
            return "laylo: it texted a code but the page showed nowhere to enter it"
        code = await wait_for_code(self._submitted_at)
        if code is None:
            return "laylo: the verification code never arrived; the next run RSVPs again"
        # Queried again: the wait for the text can outlast the element first found.
        box = await page.wait_for_selector(_CODE_BOX, state="visible", timeout=_ELEMENT_WAIT_MS)
        assert box is not None  # noqa: S101
        if not await self._on_laylo(box):
            return "laylo: the page left laylo.com before the code was entered"
        await box.click()
        await box.type(code, delay=self.type_delay_ms)
        try:
            await page.wait_for_selector(_CODE_BOX, state="hidden", timeout=_CODE_ACCEPT_WAIT_MS)
        except PlaywrightTimeoutError:
            return "laylo: the code was not accepted; the next run RSVPs again"
        logger.info("[%s] code accepted", self.gate_name)
        return None

    async def _type_contact(self, page: Page, channel: str) -> str | None:
        """Put this channel's contact in its field. Returns why it could not, or None.

        Typed here, not left to autofill: a page that remembers a number restores it after
        load, and autofill skips a field that is not empty.
        """
        if not is_laylo_host(page.url):
            return "laylo: the page left laylo.com before the RSVP"
        try:
            field = await page.wait_for_selector(
                _CONTACT_FIELD[channel], state="visible", timeout=_ELEMENT_WAIT_MS
            )
        except PlaywrightTimeoutError:
            return f"laylo: no {channel} field on the drop page"
        assert field is not None  # noqa: S101
        await page.wait_for_timeout(_FORM_SETTLE_MS)
        if not await self._on_laylo(field):
            return "laylo: the page left laylo.com before the RSVP"
        value = self.template_vars[_CHANNEL_VAR[channel]]
        await field.fill("")
        await field.type(value, delay=self.type_delay_ms)
        typed = await field.input_value()
        if re.sub(r"\D", "", typed) != re.sub(r"\D", "", value) or (
            channel == "email" and typed.strip() != value.strip()
        ):
            return f"laylo: the {channel} field did not keep what was typed"
        return None

    async def _visible(self, page: Page, selector: str) -> Any:  # noqa: ANN401
        el = await page.query_selector(selector)
        return el if el is not None and await el.is_visible() else None

    async def _choose_channel(self, page: Page) -> str | None:
        """Email where the drop offers it and an address is set, else phone. None: neither.

        Leaves the form on the chosen channel, and template_vars holding only its contact.
        """
        # The form renders after load; asked too early, an email drop reads as SMS-only.
        with contextlib.suppress(PlaywrightTimeoutError):
            await page.wait_for_selector(
                f"{_TOGGLE['email']}, {_CONTACT_FIELD['sms']}, {_CONTACT_FIELD['email']}",
                state="visible",
                timeout=_ELEMENT_WAIT_MS,
            )
            await page.wait_for_timeout(_TOGGLE_SETTLE_MS)
        offers_email = (
            await self._visible(page, _TOGGLE["email"])
            or await self._visible(page, _CONTACT_FIELD["email"])
        ) is not None
        if offers_email and self.template_vars.get("email"):
            channel = "email"
        elif self.template_vars.get("phone"):
            channel = "sms"
        else:
            return None
        # A page can remember the other channel as the one last used.
        toggle = await self._visible(page, _TOGGLE[channel])
        if toggle is not None and await toggle.get_attribute("aria-pressed") != "true":
            await toggle.click()
            await page.wait_for_timeout(_TOGGLE_SETTLE_MS)
        keep = _CHANNEL_VAR[channel]
        self.template_vars = {k: v for k, v in self.template_vars.items() if k == keep}
        self.goal = _GOALS[channel]
        logger.info("[%s] RSVPing by %s", self.gate_name, channel)
        return channel

    async def _rsvp(self, page: Page) -> tuple[dict[str, StepResult], str | None]:
        """RSVP the drop. Returns the steps and the channel, or no channel when it did not take.

        Nothing is recorded when it did not: the address is not signed up until Laylo
        accepts the RSVP or its code, and another RSVP only asks for a fresh code.
        """
        results: dict[str, StepResult] = {}
        channel = await self._choose_channel(page)
        if channel is None:
            self.review_reason = "laylo: no contact set for the channels this drop offers"
            return results, None
        if (problem := await self._type_contact(page, channel)) is not None:
            self.review_reason = problem
            return results, None
        page.on("response", self._on_response)
        try:
            results = await super().run(page)
            if self._submitted_at is None:
                raise StuckGate(self.gate_name, last_step_id="laylo RSVP never submitted")
            if self._captcha_after_submit is not None:
                raise CaptchaEncountered(self._captcha_after_submit, self.gate_name)
            ack = await self._await_ack()
        finally:
            page.remove_listener("response", self._on_response)
        if ack is None:
            self.review_reason = (
                "laylo: Laylo never acknowledged the RSVP (a headless run is often dropped)"
            )
            return results, None
        if ack == "code":
            problem = (
                await self._enter_code(page)
                if channel == "sms"
                else "laylo: it asked an email RSVP for a code"
            )
            if problem is not None:
                self.review_reason = problem
                return results, None
        return results, channel

    async def run(self, page: Page) -> dict[str, StepResult]:
        self._page = page
        key = laylo_drops.drop_key(page.url)
        record = laylo_drops.load(key) or laylo_drops.DropRecord()
        results: dict[str, StepResult] = {}
        if record.submitted_at is None:
            results, channel = await self._rsvp(page)
            if channel is None:
                return results
            record = replace(record, submitted_at=self._submitted_at, channel=channel)
            laylo_drops.save(key, record)
        else:
            logger.info("[%s] %s was already submitted; not RSVPing again", self.gate_name, key)
        await self._finish(key, record)
        return results

    async def _await_link(self, record: laylo_drops.DropRecord) -> laylo_drops.DropRecord | None:
        """The record with its link filled in from Gmail, or None (review_reason says why)."""
        assert record.submitted_at is not None  # noqa: S101
        if time.time() > record.submitted_at + _LINK_WINDOW_S:
            self.review_reason = "laylo: no link within 24h of the RSVP; --laylo-forget to retry"
            return None
        used = laylo_drops.used_gmail_ids()
        if record.channel == "email":
            mail = await wait_for_email(record.submitted_at, used)
            if mail is None:
                self.review_reason = "laylo: no email with a link yet; the next run checks"
                return None
            return replace(
                record,
                link=email_download_link(mail.body),
                gmail_id=mail.gmail_id,
                message=mail.subject,
            )
        senders = LAYLO_SENDERS | laylo_drops.known_senders()
        text = await wait_for_text(record.submitted_at, used, senders)
        if text is None:
            self.review_reason = "laylo: no text with a link yet; the next run checks"
            return None
        return replace(
            record,
            link=extract_link(text.body),
            gmail_id=text.gmail_id,
            message=text.body,
            sender=text.sender,
        )

    async def _finish(self, key: str, record: laylo_drops.DropRecord) -> None:
        if record.link is None:
            linked = await self._await_link(record)
            if linked is None:
                return
            record = linked
            laylo_drops.save(key, record)
        assert record.link is not None  # noqa: S101

        if record.folder is None:
            if laylo_drops.dropbox_direct(record.link) is None:
                self.review_reason = f"laylo: link is not Dropbox, get it by hand: {record.link}"
                return
            # Named for the link too: after --laylo-forget a new link must not land in, and
            # be matched against, the folder the old one filled.
            tag = hashlib.sha256(record.link.encode()).hexdigest()[:8]
            slug = key.replace("/", "-") + f"-{tag}"
            try:
                folder = await laylo_drops.fetch(record.link, slug)
            except laylo_drops.LayloFetchError as exc:
                self.review_reason = f"laylo: fetching the link failed ({exc})"
                return
            record = replace(record, folder=str(folder), fetched_at=time.time())
            laylo_drops.save(key, record)
        assert record.folder is not None  # noqa: S101

        folder = Path(record.folder)
        match = laylo_drops.match_track(folder, self.track_title) if self.track_title else None
        if match is None:
            # A drop holding one track is that track, whatever the artist named the file.
            audio = [
                p
                for p in folder.rglob("*")
                if p.is_file() and p.suffix.lower() in _AUDIO_EXTS and not p.name.startswith("._")
            ]
            match = audio[0] if len(audio) == 1 else None
        if match is None:
            self.review_reason = f"laylo: folder kept at {folder}; no single file matched"
            return
        placed = await asyncio.to_thread(
            laylo_drops.place_match, match, laylo_drops.save_dir(), str(self.track_title)
        )
        if placed is None:
            self.review_reason = f"laylo: {match.name} matched but its name is already taken"
            return
        self._note_saved(placed, via=f"from laylo folder {folder}")
