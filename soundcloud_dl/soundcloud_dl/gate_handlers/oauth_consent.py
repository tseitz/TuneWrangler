"""Tell an OAuth consent screen apart from a sign-in form, and say so accurately.

Detection never clicks. Approving is a decision about the operator's own account, so
approve_consent is its own call, made only by a handler that opted in via
GateHandler.oauth_approve_once. InfluencePlanner asks for SUPERFAN_CONNECT — a broad,
non-expiring grant — and a build that clicked Allow on every turn re-granted it thirteen
times without ever unlocking the gate.

What this replaces is a misdiagnosis: landing on secure.soundcloud.com/authorize was
reported as "sign in on that tab", to an operator who was already signed in and only
needed to press one button.
"""

from __future__ import annotations

import contextlib
import logging
import urllib.parse
from typing import TYPE_CHECKING

from soundcloud_dl.gate_handlers.oauth_popup import host_is, host_of

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("soundcloud_dl.gate_handlers.oauth_consent")

_CONSENT_HOSTS: tuple[str, ...] = ("soundcloud.com", "accounts.spotify.com")

# The host alone is not enough to tell the two screens apart, because the provider serves
# both from it. See is_consent_url.
_CONSENT_PATHS: tuple[str, ...] = ("/authorize", "/authorise", "/oauth", "/connect")

# Matched on the control's own text, unlike the popup path's selector, which ends in a
# bare input[type=submit]. That is safe in a window opened for consent and is not safe
# here, where the same host also serves the sign-in form.
_ALLOW = (
    "button:has-text('Allow'), button:has-text('Authorize'), "
    "button:has-text('Agree'), button:has-text('Accept')"
)

_CREDENTIAL_FIELD = "input[type='password']"

_ALLOW_WAIT_MS = 5_000
_RETURN_WAIT_MS = 15_000


def is_consent_url(url: str) -> bool:
    """True for a provider's consent endpoint specifically, not merely its domain.

    The path check is load-bearing, not tidying. secure.soundcloud.com serves the sign-in
    form from the same host, that form is email-first — so step one has no password field
    for the check below to catch — and _ALLOW matches text anywhere in the subtree. A
    cookie banner's "Accept all" on a sign-in page would otherwise satisfy both tests, and
    the operator would be told to press an Allow button that is not on the screen.
    """
    if not any(host_is(host_of(url), domain) for domain in _CONSENT_HOSTS):
        return False
    path = (urllib.parse.urlparse(url).path or "").lower()
    return any(p in path for p in _CONSENT_PATHS)


async def looks_like_consent(page: Page) -> bool:
    """True when this page is asking to approve access, not asking who you are.

    A password field anywhere disqualifies it. Being signed in already is what makes this
    a yes/no question rather than a login, and a sign-in form must never be described as
    something the operator can just click through.
    """
    if not is_consent_url(page.url):
        return False
    with contextlib.suppress(Exception):
        await page.wait_for_selector(_ALLOW, state="visible", timeout=_ALLOW_WAIT_MS)
    try:
        if await page.query_selector(_CREDENTIAL_FIELD) is not None:
            return False
        return await page.query_selector(_ALLOW) is not None
    except Exception:  # noqa: BLE001
        logger.debug("could not inspect a suspected consent page", exc_info=True)
        return False


async def stop_reason(page: Page, fallback: str) -> str:
    """The reason to report for a page the run refuses to drive past.

    Falls back to the caller's wording, so a genuine sign-in wall still reads as one.
    """
    if await looks_like_consent(page):
        return (
            "this gate wants a grant on your SoundCloud account, and that is yours to give "
            "— press Allow on the open tab once, then re-run"
        )
    return fallback


async def approve_consent(page: Page, gate_name: str) -> bool:
    """Press Allow on a consent screen `looks_like_consent` already confirmed.

    True once the page has left the consent screen, which is the only sign the grant went
    through: the provider redirects back to the gate after it.
    """
    allow = await page.query_selector(_ALLOW)
    if allow is None:
        return False
    logger.info("[%s] SoundCloud consent: clicking Allow (once for this gate)", gate_name)
    await allow.click()
    try:
        await page.wait_for_url(lambda u: not is_consent_url(u), timeout=_RETURN_WAIT_MS)
    except Exception:  # noqa: BLE001
        logger.warning("[%s] still on the consent screen after Allow: %s", gate_name, page.url)
        return False
    logger.info("[%s] SoundCloud consent approved; back on %s", gate_name, page.url)
    return True
