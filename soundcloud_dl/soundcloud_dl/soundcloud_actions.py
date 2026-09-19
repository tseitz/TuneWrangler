"""Perform follow/like/repost/comment on SoundCloud itself, and read back whether they stuck.

A gate's own buttons mark themselves done on click — Hypeddit's do it in the onclick handler,
before SoundCloud has been asked anything. So the gate's UI cannot be used as proof. These
functions drive soundcloud.com directly and verify against SoundCloud's own control state.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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


async def probe_urls(track_url: str) -> None:
    """Probe a track page and its artist page — follow lives on the artist page."""
    from soundcloud_dl.playwright_browser import attached_browser  # noqa: PLC0415

    async with attached_browser() as context:
        await probe(context, track_url)
        artist_url = "/".join(track_url.split("?", maxsplit=1)[0].split("/")[:4])
        logger.info("")
        await probe(context, artist_url)
