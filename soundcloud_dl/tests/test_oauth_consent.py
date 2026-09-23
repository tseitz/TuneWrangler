"""Unit tests for consent detection and the no-auto-approve opt-out."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from soundcloud_dl.gate_handlers.base import GateHandler
from soundcloud_dl.gate_handlers.jev import DroploudHandler, InfluencePlannerHandler, JevHandler
from soundcloud_dl.gate_handlers.oauth_consent import (
    is_consent_url,
    looks_like_consent,
    stop_reason,
)
from soundcloud_dl.gate_handlers.oauth_popup import handle_oauth_popup


def fake_page(url: str, *, allow: object | None = None, password: object | None = None):
    """A Page whose query_selector answers by selector kind, not by call order."""
    page = MagicMock()
    page.url = url
    page.wait_for_selector = AsyncMock()

    async def query(selector: str):
        return password if "password" in selector else allow

    page.query_selector = AsyncMock(side_effect=query)
    return page


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://secure.soundcloud.com/authorize?client_id=x", True),
        ("https://accounts.spotify.com/authorize", True),
        ("https://gate.influenceplanner.com/Na9k2IGP", False),
        ("https://accounts.google.com/v3/signin", False),
        # The substring trap host_is exists to close.
        ("https://evil.example/?next=secure.soundcloud.com", False),
        # Right host, wrong screen. The provider serves sign-in from here too, and that
        # form is email-first, so the password check cannot be what separates them.
        ("https://secure.soundcloud.com/signin", False),
        ("https://soundcloud.com/you/library", False),
    ],
)
def test_is_consent_url(url, expected):
    assert is_consent_url(url) is expected


@pytest.mark.asyncio
async def test_a_cookie_banner_on_a_sign_in_page_is_not_consent():
    """_ALLOW matches text anywhere in the subtree, so "Accept all cookies" satisfies it,
    and SoundCloud's email-first sign-in has no password field on step one. Only the path
    tells the two apart — without it the operator is sent to press a button that is not
    on the screen."""
    page = fake_page("https://secure.soundcloud.com/signin", allow=MagicMock())
    assert await looks_like_consent(page) is False


@pytest.mark.asyncio
async def test_a_password_field_means_sign_in_not_consent():
    """secure.soundcloud.com serves the sign-in form from the same host as the consent
    screen. Describing a login as a one-button decision would be a lie to the operator."""
    page = fake_page(
        "https://secure.soundcloud.com/signin", allow=MagicMock(), password=MagicMock()
    )
    assert await looks_like_consent(page) is False
    assert await stop_reason(page, "the gate asked us to sign in") == "the gate asked us to sign in"


@pytest.mark.asyncio
async def test_a_consent_screen_is_reported_as_one():
    """The live misdiagnosis: already signed in as a named user, one Allow button away,
    and the run said 'sign in on that tab'."""
    page = fake_page("https://secure.soundcloud.com/authorize", allow=MagicMock())
    assert await looks_like_consent(page) is True
    assert "Allow" in await stop_reason(page, "left the gate for secure.soundcloud.com")


@pytest.mark.asyncio
async def test_an_unknown_host_keeps_the_callers_wording():
    page = fake_page("https://accounts.google.com/v3/signin", allow=MagicMock())
    assert await stop_reason(page, "left the gate for accounts.google.com") == (
        "left the gate for accounts.google.com"
    )


@pytest.mark.asyncio
async def test_nothing_in_consent_detection_ever_clicks():
    """Detection only. Approving is the operator's decision, not this module's."""
    allow = MagicMock()
    allow.click = AsyncMock()
    page = fake_page("https://secure.soundcloud.com/authorize", allow=allow)
    await stop_reason(page, "fallback")
    allow.click.assert_not_awaited()


def test_influenceplanner_does_not_auto_approve_but_others_still_do():
    """SUPERFAN_CONNECT is a broad, non-expiring grant on the account, unlike the
    per-download connect every other gate asks for."""
    assert InfluencePlannerHandler.auto_approve_oauth is False
    assert DroploudHandler.auto_approve_oauth is True
    assert JevHandler.auto_approve_oauth is True


@pytest.mark.asyncio
async def test_a_consent_popup_is_left_open_and_unclicked_when_approve_is_false():
    """Closing it would throw away the one thing the operator has to act on."""
    popup = MagicMock()
    popup.url = "https://secure.soundcloud.com/authorize?client_id=x"
    popup.wait_for_load_state = AsyncMock()
    popup.is_closed = MagicMock(return_value=False)
    popup.close = AsyncMock()
    popup.query_selector = AsyncMock(return_value=MagicMock())
    popup.wait_for_selector = AsyncMock()

    await handle_oauth_popup(popup, "influenceplanner_jev", approve=False)

    popup.close.assert_not_awaited()
    popup.query_selector.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_consent_popup_is_still_approved_by_default():
    """Every other gate asks for a throwaway connect, and stopping on those would mean
    no gate ever completes unattended."""
    allow = MagicMock()
    allow.click = AsyncMock()
    popup = MagicMock()
    popup.url = "https://secure.soundcloud.com/authorize?client_id=x"
    popup.wait_for_load_state = AsyncMock()
    popup.wait_for_selector = AsyncMock()
    popup.wait_for_timeout = AsyncMock()
    popup.wait_for_url = AsyncMock()
    popup.is_closed = MagicMock(return_value=False)
    popup.close = AsyncMock()
    popup.query_selector = AsyncMock(return_value=allow)

    await handle_oauth_popup(popup, "hypeddit", approve=True)

    allow.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_spotify_popup_is_closed_without_looking_for_allow():
    """Hypeddit records the step from the popup opening, not from what happens inside it.

    query_selector never awaited proves this: the old code waited up to 15s for an Allow
    button that a plain Spotify login screen (no active session) never shows, then closed
    anyway. Closing immediately is strictly better, not just equivalent.
    """
    popup = MagicMock()
    popup.url = "https://accounts.spotify.com/authorize?client_id=x"
    popup.wait_for_load_state = AsyncMock()
    popup.wait_for_timeout = AsyncMock()
    popup.is_closed = MagicMock(return_value=False)
    popup.close = AsyncMock()
    popup.query_selector = AsyncMock()

    await handle_oauth_popup(popup, "hypeddit", approve=True)

    popup.query_selector.assert_not_awaited()
    popup.close.assert_awaited()


class _FiresAPopupMidRun(GateHandler):
    """Minimal handler that produces one popup while run() is in progress."""

    auto_approve_oauth = False

    def __init__(self, popup, **kwargs):
        super().__init__(**kwargs)
        self._popup = popup

    async def _run_steps(self, page, results):
        for callback in page.context.listeners:
            callback(self._popup)
        return results


def _consent_popup():
    popup = MagicMock()
    popup.url = "https://secure.soundcloud.com/authorize?client_id=x&state=SUPERFAN_CONNECT"
    popup.wait_for_load_state = AsyncMock()
    popup.is_closed = MagicMock(return_value=False)
    popup.close = AsyncMock()
    return popup


def _page_with_context():
    page = MagicMock()
    context = MagicMock()
    context.listeners = []
    context.on = lambda _event, callback: context.listeners.append(callback)
    context.remove_listener = MagicMock()
    page.context = context
    return page


@pytest.mark.asyncio
async def test_run_leaves_a_declined_consent_popup_open():
    """The bug the isolated test above could not see: handle_oauth_popup suppressing its
    own close is not enough, because run()'s finally closed every popup it had seen. The
    operator was told to press Allow on a tab that had already been shut behind them.
    """
    popup = _consent_popup()
    handler = _FiresAPopupMidRun(popup, config={"gate": "ipln", "steps": []})

    await handler.run(_page_with_context())

    popup.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_still_closes_a_popup_it_did_approve():
    """The opt-out must not turn into a leak: a popup left behind keeps running script
    against the live SoundCloud session for the rest of the playlist."""
    popup = _consent_popup()
    popup.wait_for_selector = AsyncMock()
    popup.wait_for_timeout = AsyncMock()
    popup.wait_for_url = AsyncMock()
    allow = MagicMock()
    allow.click = AsyncMock()
    popup.query_selector = AsyncMock(return_value=allow)

    handler = _FiresAPopupMidRun(popup, config={"gate": "hypeddit", "steps": []})
    handler.auto_approve_oauth = True

    await handler.run(_page_with_context())

    popup.close.assert_awaited()


def _allowable_consent_popup():
    popup = _consent_popup()
    allow = MagicMock()
    allow.click = AsyncMock()
    popup.allow = allow
    popup.wait_for_selector = AsyncMock()
    popup.wait_for_timeout = AsyncMock()
    popup.wait_for_url = AsyncMock()
    popup.query_selector = AsyncMock(return_value=allow)
    return popup


class _FiresTwoPopups(_FiresAPopupMidRun):
    oauth_approve_once = True

    async def _run_steps(self, page, results):
        for popup in self._popup:
            for callback in page.context.listeners:
                callback(popup)
        return results


@pytest.mark.asyncio
async def test_an_approve_once_gate_approves_the_first_consent_popup_only():
    """Approving on every turn looped without unlocking; approving once and moving on to
    the comment is how a person gets through gaterush."""
    first, second = _allowable_consent_popup(), _allowable_consent_popup()
    handler = _FiresTwoPopups([first, second], config={"gate": "gaterush", "steps": []})

    await handler.run(_page_with_context())

    first.allow.click.assert_awaited_once()
    second.allow.click.assert_not_awaited()
    assert handler.consent_declined is True


@pytest.mark.asyncio
async def test_a_popup_that_is_not_consent_does_not_spend_the_allowance():
    popup = MagicMock()
    popup.url = "https://www.instagram.com/someone"
    popup.wait_for_load_state = AsyncMock()
    popup.wait_for_timeout = AsyncMock()
    popup.is_closed = MagicMock(return_value=False)
    popup.close = AsyncMock()
    approve = MagicMock(return_value=True)

    await handle_oauth_popup(popup, "gaterush", approve=approve)

    approve.assert_not_called()


def test_influenceplanner_and_gaterush_approve_once():
    from soundcloud_dl.gate_handlers.jev import GaterushHandler  # noqa: PLC0415

    assert InfluencePlannerHandler.oauth_approve_once is True
    assert GaterushHandler.oauth_approve_once is True


def _in_tab_handler(*, once: bool):
    from soundcloud_dl.gate_handlers.judgment import JudgmentGateHandler  # noqa: PLC0415

    handler = JudgmentGateHandler(config={"gate": "ipln", "steps": []})
    handler.auto_approve_oauth = False
    handler.oauth_approve_once = once
    handler._gate_host = "gate.influenceplanner.com"
    handler._wait_for_gate_ready = AsyncMock()
    return handler


def _in_tab_consent_page():
    allow = MagicMock()
    allow.click = AsyncMock()
    page = fake_page("https://secure.soundcloud.com/authorize?client_id=x", allow=allow)
    page.wait_for_url = AsyncMock()
    return page, allow


@pytest.mark.asyncio
async def test_an_in_tab_consent_is_approved_once_then_stops():
    """InfluencePlanner navigates the gate tab itself to the consent screen, so the popup
    path never sees it. After one Allow the gate shows its comment step."""
    from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered  # noqa: PLC0415

    handler = _in_tab_handler(once=True)
    page, allow = _in_tab_consent_page()

    await handler._raise_on_login_wall(page)
    allow.click.assert_awaited_once()
    handler._wait_for_gate_ready.assert_awaited_once()

    with pytest.raises(LoginWallEncountered, match="asked again"):
        await handler._raise_on_login_wall(page)
    allow.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_in_tab_consent_is_left_alone_without_the_opt_in():
    from soundcloud_dl.gate_handlers.login_wall import LoginWallEncountered  # noqa: PLC0415

    handler = _in_tab_handler(once=False)
    page, allow = _in_tab_consent_page()

    with pytest.raises(LoginWallEncountered, match="press Allow"):
        await handler._raise_on_login_wall(page)
    allow.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_popup_that_opens_blank_is_judged_where_it_lands():
    """Gaterush opens the window blank and points it at SoundCloud a moment later. Judged
    at about:blank it was closed as unrecognised, and the consent never appeared."""
    popup = _allowable_consent_popup()
    popup.url = "about:blank"

    async def lands(_predicate, timeout):  # noqa: ARG001
        popup.url = "https://secure.soundcloud.com/authorize?client_id=x"

    popup.wait_for_url = AsyncMock(side_effect=lands)

    await handle_oauth_popup(popup, "gaterush", approve=True)

    popup.allow.click.assert_awaited_once()
