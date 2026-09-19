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
    from playwright.async_api import BrowserContext, Page

from soundcloud_dl.config import PAGE_LOAD_WAIT_SECONDS
from soundcloud_dl.playwright_browser import new_page

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
    # of every page has one. These two are the page's own content.
    for attempt in (1, 2):
        try:
            await page.wait_for_selector(
                ".soundActions, .userInfoBar", state="attached", timeout=20_000
            )
            break
        except Exception:  # noqa: BLE001
            state = await page.evaluate(
                "() => [document.visibilityState, document.readyState,"
                " document.querySelectorAll('.sound').length, document.body.children.length,"
                " location.href]"
            )
            logger.warning(
                "attempt %d: no content. visibility=%s ready=%s .sound=%d bodyKids=%d url=%s",
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


@dataclass(frozen=True)
class ActionResult:
    """Outcome of one action, judged by SoundCloud's own control state afterwards."""

    action: str
    ok: bool
    detail: str


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
            return ActionResult(kind, ok=True, detail=f"{before!r} → {after!r}")
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


async def perform(
    context: BrowserContext,
    track_url: str,
    *,
    comment_text: str | None = None,
    undo: bool = False,
) -> dict[str, ActionResult]:
    """Do follow/like/repost (and optionally comment) on SoundCloud, verifying each."""
    page = await new_page(context)
    results: dict[str, ActionResult] = {}
    try:
        await block_ads(page)
        await page.goto(artist_url_for(track_url), wait_until="domcontentloaded", timeout=30_000)
        await _wait_for_actions(page)

        bar = await page.query_selector(".userInfoBar__buttons")
        if bar is None:
            results["follow"] = ActionResult("follow", ok=False, detail="artist page did not load")
        else:
            results["follow"] = await _toggle(page, bar, "follow", want_on=not undo)

        item = await _find_track_item(page, track_url)
        if item is None:
            detail = f"{track_path_for(track_url)} not in the artist's listing"
            for kind in ("like", "repost"):
                results[kind] = ActionResult(kind, ok=False, detail=detail)
        else:
            for kind in ("like", "repost"):
                results[kind] = await _toggle(page, item, kind, want_on=not undo)
            if comment_text and not undo:
                results["comment"] = await _post_comment(page, item, comment_text)

        for r in results.values():
            log = logger.info if r.ok else logger.warning
            log("%s %s — %s", "OK  " if r.ok else "FAIL", r.action, r.detail)
        return results
    finally:
        await page.close()


async def run_actions(track_url: str, comment_text: str | None, *, undo: bool = False) -> None:
    """Entry point for --sc-do / --sc-undo."""
    from soundcloud_dl.playwright_browser import attached_browser  # noqa: PLC0415

    async with attached_browser() as context:
        await perform(context, track_url, comment_text=comment_text, undo=undo)


async def probe_urls(track_url: str) -> None:
    """Probe a track page and its artist page — follow lives on the artist page."""
    from soundcloud_dl.playwright_browser import attached_browser  # noqa: PLC0415

    async with attached_browser() as context:
        await probe(context, track_url)
        artist_url = "/".join(track_url.split("?", maxsplit=1)[0].split("/")[:4])
        logger.info("")
        await probe(context, artist_url)
