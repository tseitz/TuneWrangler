"""Perform follow/like/repost/comment on SoundCloud itself, and read back whether they stuck.

A gate's own buttons mark themselves done on click — Hypeddit's do it in the onclick handler,
before SoundCloud has been asked anything. So the gate's UI cannot be used as proof. These
functions drive soundcloud.com directly and verify against SoundCloud's own control state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from playwright.async_api import BrowserContext, Page

from soundcloud_dl.config import PAGE_LOAD_WAIT_SECONDS
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, detect_captcha
from soundcloud_dl.playwright_browser import new_page
from soundcloud_dl.soundcloud_api import (
    AccountMismatch,
    ApiError,
    api_client,
    assert_same_account,
    ensure_on_soundcloud,
    is_liked,
    is_reposted,
    me,
    my_comment_on,
    post_comment,
    resolve,
    resolve_user,
    set_following,
    set_like,
    set_repost,
    write_by_token,
)
from soundcloud_dl.soundcloud_auth import SoundCloudAuthError

logger = logging.getLogger("soundcloud_dl.soundcloud_actions")

# Dumps every control SoundCloud renders, with the attributes that carry on/off state.
# aria-pressed and the sc-button-selected class are the two ways their UI encodes it.
_PROBE_JS = """
() => {
  const els = Array.from(document.querySelectorAll(
    'button, a[role=button], [role=button], input, textarea, div[contenteditable]'
  ));
  return els.filter((el) => el.offsetParent !== null).map((el) => ({
    tag: el.tagName.toLowerCase(),
    cls: (el.className || '').toString().slice(0, 120),
    id: el.id || '',
    title: el.getAttribute('title') || '',
    aria: el.getAttribute('aria-label') || '',
    pressed: el.getAttribute('aria-pressed') || '',
    placeholder: el.getAttribute('placeholder') || '',
    text: (el.innerText || el.value || '').trim().slice(0, 50),
    selected: el.classList.contains('sc-button-selected'),
    ancestors: (() => {
      const out = [];
      let n = el.parentElement;
      while (n && out.length < 6) {
        const c = (n.className || '').toString().split(/\\s+/)
          .filter((x) => x && !x.startsWith('sc-') && !x.startsWith('g-'));
        if (c.length) out.push(c[0]);
        n = n.parentElement;
      }
      return out.join(' < ');
    })(),
  }));
}
"""

_INTERESTING = ("like", "repost", "follow", "comment", "share", "more", "download")

# Blocked for speed and quiet logs only. Blocking these does NOT fix the track page, which
# renders its body in no profile here — "AF is not defined" turned out to be a symptom.
_AD_HOSTS = (
    "aditude.io",
    "googletagservices.com",
    "googlesyndication.com",
    "doubleclick.net",
    "adnxs.com",
    "amazon-adsystem.com",
    "criteo.com",
    "pubmatic.com",
    "rubiconproject.com",
    "casalemedia.com",
    "sharethrough.com",
    "33across.com",
    "alb.reddit.com",
)


async def block_ads(page: Page) -> None:
    """Drop ad requests before they can load the script that breaks track pages."""
    await page.route(
        "**/*",
        lambda route: (
            route.abort() if any(h in route.request.url for h in _AD_HOSTS) else route.continue_()
        ),
    )


_CONTENT_POLL_MS = 500
_CONTENT_TIMEOUT_MS = 20_000


async def _poll(check: Callable[[], Awaitable[object]], page: Page) -> bool:
    for _ in range(_CONTENT_TIMEOUT_MS // _CONTENT_POLL_MS):
        if await check() is not None:
            return True
        await page.wait_for_timeout(_CONTENT_POLL_MS)
    return False


async def _wait_for_actions(page: Page) -> None:
    """Wait for SoundCloud's engagement controls, not a fixed sleep.

    A 3s sleep read 17 controls on a cold load and 60+ on a warm one, which is how a
    selector gets declared missing when it was only late.
    """
    # A track page's body never renders in a background tab — Chrome throttles the timers
    # its SPA renders on. Artist pages are unaffected, which is what made this look like a
    # per-track problem. Same reason judgment.py re-focuses before every snapshot.
    try:
        await page.bring_to_front()
    except Exception as e:  # noqa: BLE001
        logger.warning("bring_to_front failed: %s", e)

    # Waiting on .sc-button-like alone returns in 4s because the mini player at the bottom
    # of every page has one. track_content_frame looks for the page's own content, in the
    # top document on the legacy layout and in the layout iframe on v2.
    from soundcloud_dl.soundcloud_page import track_content_frame  # noqa: PLC0415

    for attempt in (1, 2):
        if await _poll(lambda: track_content_frame(page), page):
            break
        state = await page.evaluate(
            "() => [document.visibilityState, document.readyState,"
            " document.querySelectorAll('.sound').length,"
            " document.querySelectorAll('iframe.webiIframeV2Layout').length,"
            " document.body.children.length, location.href]"
        )
        logger.warning(
            "attempt %d: no content. visibility=%s ready=%s .sound=%d v2frame=%d bodyKids=%d "
            "url=%s",
            attempt,
            *state,
        )
        if attempt == 1:
            logger.info("reloading once")
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
    if PAGE_LOAD_WAIT_SECONDS > 0:
        await page.wait_for_timeout(PAGE_LOAD_WAIT_SECONDS * 1000)


async def probe(context: BrowserContext, url: str) -> None:
    """Log SoundCloud's own controls on a page, so selectors are read rather than guessed."""
    page = await new_page(context)
    problems: list[str] = []
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"[:200]))
    page.on(
        "console",
        lambda m: (
            problems.append(f"console.{m.type}: {m.text}"[:200])
            if m.type in ("error", "warning")
            else None
        ),
    )
    page.on(
        "response",
        lambda r: problems.append(f"HTTP {r.status} {r.url}"[:200]) if r.status >= 400 else None,  # noqa: PLR2004
    )
    # A request killed by a proxy or blocklist never produces a response, so it is invisible
    # to the handler above — and a missing script is exactly what "AF is not defined" means.
    page.on(
        "requestfailed",
        lambda r: problems.append(f"FAILED {r.failure} {r.url}"[:200]),
    )
    try:
        await block_ads(page)
        logger.info("Probing: %s", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await _wait_for_actions(page)

        if await page.query_selector(".auth-modal") is not None:
            logger.warning("SoundCloud is showing a login prompt — run: deno task py --login")

        for p in problems[:15]:
            logger.info("  ! %s", p)
        logger.info("final url: %s", page.url)
        logger.info("title: %s", await page.title())
        body = await page.evaluate("() => (document.body.innerText || '').trim().slice(0, 400)")
        logger.info("body text: %r", body)
        for container in (".listenEngagement", ".visualSound__wrapper", ".userInfoBar"):
            logger.info(
                "container %s → %s", container, await page.query_selector(container) is not None
            )

        controls = await page.evaluate(_PROBE_JS)
        logger.info("%d visible controls", len(controls))
        logger.info("─" * 70)
        for c in controls:
            haystack = f"{c['cls']} {c['aria']} {c['title']} {c['text']}".lower()
            if not any(word in haystack for word in _INTERESTING):
                continue
            logger.info(
                "<%s> title=%r sel=%s text=%r id=%r\n         in: %s",
                c["tag"],
                c["title"],
                c["selected"],
                c["text"],
                c["id"],
                c["ancestors"],
            )
        logger.info("─" * 70)
    finally:
        await page.close()


async def _raise_on_captcha(page: Page) -> None:
    """Stop the moment SoundCloud challenges us, rather than clicking at an overlay.

    Playwright will happily retry a click for 30s against a DataDome iframe and then
    report a pointer-intercept, which reads as a selector problem instead of a block.
    """
    kind = await detect_captcha(page)
    if kind is not None:
        raise CaptchaEncountered(kind, "soundcloud")


@dataclass(frozen=True)
class ActionResult:
    """Outcome of one action, judged by SoundCloud's own control state afterwards."""

    action: str
    ok: bool
    detail: str
    # Whether this run altered the state, as opposed to finding it already right. Only a
    # follow this run added may be given back afterwards; one the user already had is theirs.
    changed: bool = False
    # The SoundCloud user a follow landed on. A gate names several profiles, so the action
    # name alone no longer says who to give back.
    subject_id: int | None = None


# Each control encodes its state in title/aria-label. "Like" means not yet liked; once it
# lands SoundCloud rewrites it to "Unlike" and adds sc-button-selected.
_TOGGLES = {
    "like": ("button.sc-button-like", "Like", "Unlike"),
    "repost": ("button.sc-button-repost", "Repost", "Unpost"),
    "follow": ("button.sc-button-follow", "Follow", "Unfollow"),
}


def artist_url_for(track_url: str) -> str:
    """The artist page owning a track. Track pages never render here, artist pages do."""
    return "/".join(track_url.split("?", maxsplit=1)[0].split("/")[:4])


def track_path_for(track_url: str) -> str:
    """The site-relative path SoundCloud uses in its own links, e.g. /urboin8/mph-raw."""
    return "/" + "/".join(track_url.split("?", maxsplit=1)[0].split("/")[3:5])


async def _state(el: Any) -> str:  # noqa: ANN401
    return (await el.get_attribute("title")) or (await el.get_attribute("aria-label")) or ""


async def _toggle(page: Page, scope: Any, kind: str, *, want_on: bool) -> ActionResult:  # noqa: ANN401
    """Click a toggle only if it is not already where we want it, then re-read its state."""
    selector, off, on = _TOGGLES[kind]
    target, current = (on, off) if want_on else (off, on)

    el = await scope.query_selector(selector)
    if el is None:
        return ActionResult(kind, ok=False, detail=f"no {selector} in scope")

    before = await _state(el)
    if before == target:
        return ActionResult(kind, ok=True, detail=f"already {target.lower()}")
    if before != current:
        return ActionResult(kind, ok=False, detail=f"unexpected state {before!r}")

    await el.click()
    # SoundCloud rewrites the control only once its own API call returns, so this wait IS
    # the verification — not a cosmetic settle.
    for _ in range(20):
        await page.wait_for_timeout(500)
        after = await _state(el)
        if after == target:
            # Reaching here means the "already" branch above was not taken, so this click
            # is what moved it. Without changed=True a follow taken on this path reads as
            # one the user already had, and is never given back.
            return ActionResult(kind, ok=True, detail=f"{before!r} → {after!r}", changed=True)
    return ActionResult(kind, ok=False, detail=f"still {await _state(el)!r} after 10s")


async def _find_track_item(page: Page, track_url: str) -> Any | None:  # noqa: ANN401
    """The artist-page list entry for this track, found by the href SoundCloud itself uses."""
    path = track_path_for(track_url)
    for _ in range(10):
        link = await page.query_selector(f'a.soundTitle__title[href="{path}"]')
        if link is not None:
            handle = await link.evaluate_handle("el => el.closest('.sound')")
            return handle.as_element()
        await page.evaluate("window.scrollBy(0, 1200)")
        await page.wait_for_timeout(800)
    return None


async def _post_comment(page: Page, item: Any, text: str) -> ActionResult:  # noqa: ANN401
    """Type a comment into this track's box and confirm it appears in the thread."""
    box = await item.query_selector("input.commentForm__input")
    if box is None:
        return ActionResult("comment", ok=False, detail="no comment box on this item")
    await box.click()
    await box.fill(text)
    await page.keyboard.press("Enter")

    for _ in range(20):
        await page.wait_for_timeout(500)
        posted = await item.evaluate(
            "(el, t) => Array.from(el.querySelectorAll('.commentItem'))"
            ".some((c) => (c.innerText || '').includes(t))",
            text,
        )
        if posted:
            return ActionResult("comment", ok=True, detail="comment visible in thread")
    return ActionResult("comment", ok=False, detail="comment never appeared")


def _recorder(results: dict[str, ActionResult]) -> Callable[[ActionResult], None]:
    """Log each outcome as it lands, not in a summary at the end.

    A later action that throws must not take the record of the earlier successes with it.
    """

    def record(r: ActionResult) -> None:
        results[r.action] = r
        log = logger.info if r.ok else logger.warning
        log("%s %-7s — %s", "OK  " if r.ok else "FAIL", r.action, r.detail)

    return record


async def _verified(
    name: str,
    write: Callable[[], Awaitable[tuple[bool, str]]],
    read_back: Callable[[], Awaitable[bool]],
    *,
    want: bool,
) -> ActionResult:
    """Ask SoundCloud the state, write only if it is wrong, then ask again.

    The write's own status is not the verification. api-v2 answers 204 for a repost while
    telling us nothing about whether it stuck.

    Reading first is what makes `changed` mean something here, the same way it does for a
    follow: a like this run added may be given back, one the user already had is theirs.
    """
    if await read_back() is want:
        return ActionResult(name, ok=True, detail=f"already {'on' if want else 'off'}")
    ok, detail = await write()
    if not ok:
        return ActionResult(name, ok=False, detail=detail)
    landed = await read_back()
    if landed is want:
        return ActionResult(name, ok=True, detail=f"{detail}, confirmed", changed=True)
    return ActionResult(name, ok=False, detail=f"{detail} but SoundCloud still says {landed}")


async def _comment_once(
    client: httpx.AsyncClient, track_id: int, user_id: int, text: str
) -> ActionResult:
    """Post the comment unless this account already left one on the track.

    A like and a repost are sets, so re-running one costs a wasted write and nothing else.
    A comment is a list: every re-run leaves another copy on the artist's track, and only
    the user can delete them.
    """
    try:
        existing = await my_comment_on(client, track_id, user_id)
    except ApiError as e:
        # Not treated as "no comment found": that reading is what posts the duplicate.
        return ActionResult("comment", ok=False, detail=f"could not read comments: {e}")
    if existing is not None:
        return ActionResult("comment", ok=True, detail=f"already commented ({existing})")
    ok, detail = await post_comment(client, track_id, text)
    return ActionResult("comment", ok=ok, detail=detail, changed=ok)


async def _token_then_page(
    by_token: Callable[[], Awaitable[tuple[bool, str]]],
    by_page: Callable[[], Awaitable[tuple[bool, str]]],
    *,
    want: bool,
) -> tuple[bool, str]:
    """Write through the token API, falling back to the page's api-v2.

    Undo goes straight to the page: the token API's DELETE has never been checked.
    """
    if not want:
        return await by_page()
    ok, detail = await by_token()
    if ok:
        return ok, detail
    page_ok, page_detail = await by_page()
    return page_ok, f"{detail}; then {page_detail}"


async def _perform_via_api(
    context: BrowserContext,
    track_url: str,
    *,
    comment_text: str | None,
    undo: bool,
    into: dict[str, ActionResult] | None = None,
) -> dict[str, ActionResult]:
    """Act by track id, so nothing depends on finding a control on a rendered page."""
    want = not undo
    results: dict[str, ActionResult] = {} if into is None else into
    record = _recorder(results)

    async with api_client() as client:
        track = await resolve(client, track_url)
        if track.get("kind") != "track":
            msg = f"{track_url} resolved to {track.get('kind')!r}, not a track"
            raise ApiError(msg)
        track_id = int(track["id"])
        artist_id = int(track["user"]["id"])
        token_user_id = int((await me(client))["id"])

        page = await new_page(context)
        try:
            await block_ads(page)
            await ensure_on_soundcloud(page)
            await _raise_on_captcha(page)
            # Before anything is written, so a split account is caught while nothing has
            # been half-done across two users.
            user_id = await assert_same_account(page, token_user_id)
            logger.info("Acting as user %d on track %d", user_id, track_id)

            ok, detail, changed = await set_following(client, artist_id, on=want)
            record(
                ActionResult("follow", ok=ok, detail=detail, changed=changed, subject_id=artist_id)
            )

            record(
                await _verified(
                    "like",
                    lambda: _token_then_page(
                        lambda: write_by_token(client, "likes", track_id),
                        lambda: set_like(page, user_id, track_id, on=want),
                        want=want,
                    ),
                    lambda: is_liked(client, track_id),
                    want=want,
                )
            )
            record(
                await _verified(
                    "repost",
                    lambda: _token_then_page(
                        lambda: write_by_token(client, "reposts", track_id),
                        lambda: set_repost(page, track_id, on=want),
                        want=want,
                    ),
                    lambda: is_reposted(client, track_id),
                    want=want,
                )
            )

            if comment_text and not undo:
                record(await _comment_once(client, track_id, token_user_id, comment_text))
            return results
        finally:
            await page.close()


# A gate page is content we do not control, and every handle read off it becomes a real
# follow on a real stranger from the user's account. Droploud asks for two.
#
# This caps ONE call. A gate is asked for its requirements repeatedly, so enforcing the
# per-run ceiling is the caller's job — see requirement_follower in sc_actions_flow.py,
# which counts what the run has already spent before asking for more.
MAX_GATE_FOLLOWS = 5


async def follow_handles(handles: list[str]) -> dict[str, ActionResult]:
    """Follow the profiles a gate named by @handle, up to MAX_GATE_FOLLOWS.

    Separate from perform() because a gate does not say who it wants until partway through
    its own flow — droploud prints its terms on step 2 — so this runs mid-run, after the
    track's own artist has already been followed.

    Needs no browser: following is one of the things api.soundcloud.com does itself.
    """
    if len(handles) > MAX_GATE_FOLLOWS:
        logger.warning(
            "gate named %d profiles; following only the first %d: %s",
            len(handles),
            MAX_GATE_FOLLOWS,
            ", ".join(handles[:MAX_GATE_FOLLOWS]),
        )
        handles = handles[:MAX_GATE_FOLLOWS]

    results: dict[str, ActionResult] = {}
    record = _recorder(results)
    async with api_client() as client:
        for handle in handles:
            name = f"follow:{handle}"
            try:
                user = await resolve_user(client, handle)
                user_id = int(user["id"])
                ok, detail, changed = await set_following(client, user_id, on=True)
            except Exception as exc:  # noqa: BLE001
                # Caught per handle, never around the loop. A timeout on the third of five
                # must not discard the record of the first two — without their subject_id
                # nothing can give those follows back, and they leak silently.
                record(ActionResult(name, ok=False, detail=f"{type(exc).__name__}: {exc}"))
                continue
            record(ActionResult(name, ok=ok, detail=detail, changed=changed, subject_id=user_id))
    return results


async def release_follows(user_ids: list[int]) -> list[ActionResult]:
    """Give back follows this run added, by id.

    SoundCloud caps followings at 2000 and every gate charges one or more, so a pipeline
    that keeps them fills the account and then quietly cannot follow at all — which arrives
    as a bare 422 on a run that otherwise looks fine. Likes and reposts are not capped, are
    the point of the account, and are left alone.
    """
    out: list[ActionResult] = []
    async with api_client() as client:
        for user_id in user_ids:
            ok, detail, changed = await set_following(client, user_id, on=False)
            out.append(
                ActionResult("unfollow", ok=ok, detail=detail, changed=changed, subject_id=user_id)
            )
    return out


async def perform(
    context: BrowserContext,
    track_url: str,
    *,
    comment_text: str | None = None,
    undo: bool = False,
    into: dict[str, ActionResult] | None = None,
) -> dict[str, ActionResult]:
    """Do follow/like/repost (and optionally comment) on SoundCloud, verifying each.

    API first. Clicking is kept as the fallback because it is the only path that needs no
    stored token, but it is the one that failed: a half-rendered track page still offers
    the player bar's like button, which acts on whatever was played last.

    `into` is the caller's own dict, and passing one is what makes a partial run
    recoverable: the follow is taken first and like/repost/comment can each raise, so a
    dict that only exists as a return value takes the record of that follow with it when
    one does — leaving a real follow on the account that nothing can give back.
    """
    results = {} if into is None else into
    try:
        return await _perform_via_api(
            context, track_url, comment_text=comment_text, undo=undo, into=results
        )
    except AccountMismatch:
        # Never fall back. Clicking would act as the browser's user, which is exactly the
        # mismatch that was just detected.
        raise
    except (ApiError, SoundCloudAuthError) as exc:
        logger.warning("API path unavailable (%s) — falling back to clicking", exc)
    return await _perform_via_ui(
        context, track_url, comment_text=comment_text, undo=undo, into=results
    )


async def _perform_via_ui(
    context: BrowserContext,
    track_url: str,
    *,
    comment_text: str | None = None,
    undo: bool = False,
    into: dict[str, ActionResult] | None = None,
) -> dict[str, ActionResult]:
    """Fallback: drive the buttons on the artist page."""
    page = await new_page(context)
    results: dict[str, ActionResult] = {} if into is None else into
    try:
        await block_ads(page)
        await page.goto(artist_url_for(track_url), wait_until="domcontentloaded", timeout=30_000)
        await _wait_for_actions(page)
        record = _recorder(results)
        await _raise_on_captcha(page)

        bar = await page.query_selector(".userInfoBar__buttons")
        if bar is None:
            record(ActionResult("follow", ok=False, detail="artist page did not load"))
        else:
            followed = await _toggle(page, bar, "follow", want_on=not undo)
            record(followed)
            if followed.changed and followed.subject_id is None:
                # This path runs because the API was unavailable, so there is no id to
                # resolve and release_follows has nothing to act on. Say so loudly rather
                # than letting it read as tidied up: the account keeps this one.
                logger.warning(
                    "Followed %s by clicking, so there is no user id to give it back with "
                    "— unfollow by hand if the gate does not unlock",
                    artist_url_for(track_url),
                )

        item = await _find_track_item(page, track_url)
        if item is None:
            detail = f"{track_path_for(track_url)} not in the artist's listing"
            for kind in ("like", "repost"):
                record(ActionResult(kind, ok=False, detail=detail))
            return results

        for kind in ("like", "repost"):
            await _raise_on_captcha(page)
            record(await _toggle(page, item, kind, want_on=not undo))

        if comment_text and not undo:
            await _raise_on_captcha(page)
            record(await _post_comment(page, item, comment_text))
        return results
    finally:
        await page.close()


async def run_actions(track_url: str, comment_text: str | None, *, undo: bool = False) -> None:
    """Entry point for --sc-do / --sc-undo."""
    from soundcloud_dl.playwright_browser import attached_browser  # noqa: PLC0415

    async with attached_browser() as context:
        try:
            await perform(context, track_url, comment_text=comment_text, undo=undo)
        except CaptchaEncountered as e:
            logger.warning(
                "BLOCKED | %s — SoundCloud is challenging this browser. Solve it by hand in "
                "the Chrome window, then re-run. Anything reported OK above already landed.",
                e.kind,
            )


async def probe_urls(track_url: str) -> None:
    """Probe a track page and its artist page — follow lives on the artist page."""
    from soundcloud_dl.playwright_browser import attached_browser  # noqa: PLC0415

    async with attached_browser() as context:
        await probe(context, track_url)
        artist_url = "/".join(track_url.split("?", maxsplit=1)[0].split("/")[:4])
        logger.info("")
        await probe(context, artist_url)
