"""Capture a gate page's DOM before and after a manual unlock, then report what changed.

Gate sites redesign without warning, and when they do, the handler's selectors go stale
in ways that are hard to guess at. The reliable way to find the new unlock condition is
to watch a person do it: snapshot the page, let them complete the gate by hand, snapshot
again, and report which elements changed. The element that flips from disabled to enabled
is the one the handler has to wait for.

A gate is one-shot — completing it satisfies it for this account forever — so everything
here is built to not lose a walkthrough that cannot be repeated.

Run it with: deno task py --inspect <gate-url>
"""

import asyncio
import logging
import select
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from soundcloud_dl.config import DOWNLOAD_DIR, get_debug_dir, get_log_dir
from soundcloud_dl.downloads import save_download
from soundcloud_dl.gate_handlers.dom_snapshot import SNAPSHOT_JS, snapshot_elements
from soundcloud_dl.playwright_browser import attached_browser

logger = logging.getLogger("soundcloud_dl.inspect_gate")

# Fields worth diffing. A gate unlock nearly always shows up as a class change
# (e.g. losing "disabled"), an href changing off the javascript:void(0) placeholder,
# or a previously hidden element becoming visible.
_TRACKED_FIELDS = ("cls", "href", "disabled", "visible", "text", "checked")

_SETTLE_POLL_MS = 500
# 15s. Long enough for a client-rendered gate to finish its first paint.
_SETTLE_ATTEMPTS = 30

_DONE_POLL_MS = 400
# ~2s of consecutive failures. Below that it is a navigation and will fix itself.
_DONE_STALL_WARN_AFTER = 5

# A WAV can still be transferring when Done is clicked.
_SAVE_TIMEOUT_S = 120

_DONE_BUTTON_ID = "tw-inspect-done"
_DONE_FLAG = "__tw_inspect_done"

_READ_DONE_FLAG_JS = "(flag) => window[flag] === true"

_ADD_DONE_BUTTON_JS = """
([id, flag]) => {
  if (document.getElementById(id)) return;
  const b = document.createElement('button');
  b.id = id;
  b.textContent = "Done — snapshot now";
  b.style.cssText = 'position:fixed;z-index:2147483647;top:12px;right:12px;'
    + 'padding:10px 14px;font:600 13px system-ui;background:#16a34a;color:#fff;'
    + 'border:0;border-radius:6px;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.4)';
  b.onclick = () => { window[flag] = true; b.textContent = 'Capturing...'; };
  document.body.appendChild(b);
}
"""

_REMOVE_DONE_BUTTON_JS = f"() => document.getElementById('{_DONE_BUTTON_ID}')?.remove()"


async def _snapshot(page: Page) -> dict[str, dict[str, Any]]:
    """Record the state of every interactive element, keyed so it survives a re-render.

    Same-site frames too: SoundCloud's v2 track page draws its whole body in one, and a
    top-document-only snapshot reported "Nothing changed" whatever was clicked.
    """
    snapshot: dict[str, dict[str, Any]] = {}
    for el in await snapshot_elements(page):
        snapshot.setdefault(el["key"], el)
    for frame in page.frames[1:]:
        if not _same_site(frame.url, page.url):
            continue
        try:
            els = await frame.evaluate(SNAPSHOT_JS)
        except PlaywrightError:
            logger.debug("could not snapshot frame %s", frame.url, exc_info=True)
            continue
        # Host and path, not the query: the frame's query carries per-load ids.
        where = urlparse(frame.url)
        for el in els:
            snapshot.setdefault(f"{where.hostname}{where.path}/{el['key']}", el)
    return snapshot


def _same_site(url: str, other: str) -> bool:
    """Ad and captcha frames are someone else's page and would only add noise."""
    a, b = urlparse(url).hostname or "", urlparse(other).hostname or ""
    return bool(a) and a.split(".")[-2:] == b.split(".")[-2:]


async def _settled_snapshot(page: Page, label: str) -> dict[str, dict[str, Any]]:
    """Return the first non-empty snapshot that two consecutive polls agree on.

    A gate page is a client-rendered app, and the markup present at domcontentloaded is a
    skeleton whose controls carry the same "not ready" classes a locked control does —
    InfluencePlanner hides both the label and the icon behind `text-transparent
    [&>svg]:opacity-0 opacity-50 pointer-events-none`. Snapshotting there measured
    hydration and reported it as the unlock.

    Non-empty is part of the condition, not a tidy-up: two agreeing empty polls are a page
    that has not started rendering, and settling there makes every control a NEW row.
    """
    snapshot: dict[str, dict[str, Any]] = {}
    for _ in range(_SETTLE_ATTEMPTS):
        try:
            current = await _snapshot(page)
        except Exception:  # noqa: BLE001
            # A navigation destroys the execution context mid-poll. Expected; retry.
            logger.debug("%s snapshot failed mid-settle", label, exc_info=True)
            await page.wait_for_timeout(_SETTLE_POLL_MS)
            continue
        if current and current == snapshot:
            return current
        snapshot = current
        await page.wait_for_timeout(_SETTLE_POLL_MS)
    logger.warning("%s snapshot: page was still changing after %ds.", label, _settle_budget_s())
    return snapshot


def _settle_budget_s() -> int:
    return _SETTLE_ATTEMPTS * _SETTLE_POLL_MS // 1000


def _stdin_is_a_terminal() -> bool:
    """True only when there is a real terminal to read a keypress from.

    sys.stdin is None when the interpreter was started with stdin closed, which is exactly
    the no-terminal case this module has to survive — an AttributeError here would crash
    the run that the in-page button exists to rescue.
    """
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (OSError, ValueError):
        return False


def _enter_pressed() -> bool:
    """True if a line is waiting on stdin. Never blocks, and never raises on a closed one."""
    if not _stdin_is_a_terminal():
        return False
    try:
        if not select.select([sys.stdin], [], [], 0)[0]:
            return False
        sys.stdin.readline()
    except (OSError, ValueError):
        return False
    return True


async def _poll_done_button(page: Page) -> bool:
    """True once the in-page button has been clicked, re-adding it if a nav wiped it.

    Raises if the page cannot be reached; the caller decides whether that is a passing
    navigation or a page this button can never be placed on.
    """
    if await page.evaluate(_READ_DONE_FLAG_JS, _DONE_FLAG):
        return True
    await page.evaluate(_ADD_DONE_BUTTON_JS, [_DONE_BUTTON_ID, _DONE_FLAG])
    return False


async def _wait_for_done(page: Page) -> None:
    """Hold until the human says the gate is complete.

    Two ways in because neither covers both cases. Enter needs a terminal, and a run
    launched from anything without one — a task wrapper, an IDE — used to die on a bare
    EOFError *after* the before-snapshot had already been spent. The in-page button also
    saves alt-tabbing back to the shell from the window you are already working in.
    """
    logger.info("")
    logger.info("Now complete the gate BY HAND in the Chrome window.")
    logger.info("Go all the way until the download button is genuinely clickable.")
    if _stdin_is_a_terminal():
        logger.info("Then press Enter here, or click 'Done' at the top right of the page.")
    else:
        logger.info("Then click the green 'Done' button at the top right of the page.")

    stalled = 0
    while True:
        if _enter_pressed():
            return
        try:
            if await _poll_done_button(page):
                return
        except Exception:  # noqa: BLE001
            stalled += 1
            logger.debug("could not poll the done button", exc_info=True)
            # A run of failures is not a navigation: the button will never appear, and
            # without a terminal there is no other way out of this loop. Say so once.
            if stalled == _DONE_STALL_WARN_AFTER:
                logger.warning(
                    "Cannot place the Done button on this page (%d tries). Press Enter here "
                    "if you have a terminal, otherwise Ctrl-C and re-run.",
                    stalled,
                )
        else:
            stalled = 0
        if page.is_closed():
            return
        await asyncio.sleep(_DONE_POLL_MS / 1000)


def _report(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> None:
    """Log every element that changed, appeared, or disappeared between the snapshots."""
    changed = 0
    for key, now in after.items():
        was = before.get(key)
        if was is None:
            logger.info("NEW      %-34s <%s> %r", key, now["tag"], now["text"])
            logger.info("           class=%s href=%s", now["cls"], now["href"])
            changed += 1
            continue
        deltas = [(f, was[f], now[f]) for f in _TRACKED_FIELDS if was[f] != now[f]]
        if deltas:
            logger.info("CHANGED  %-34s <%s> %r", key, now["tag"], now["text"])
            for field, old, new in deltas:
                logger.info("           %-9s %r → %r", field, old, new)
            changed += 1
    for key, was in before.items():
        if key not in after:
            logger.info("GONE     %-34s <%s> %r", key, was["tag"], was["text"])
            changed += 1
    if changed == 0:
        logger.warning("Nothing changed between the two snapshots.")
    else:
        logger.info("%d element(s) differed.", changed)


async def _write_page(page: Page, path: Any, label: str) -> None:  # noqa: ANN401
    """Persist the page's HTML, without letting a dead context end the run.

    Reached only after the operator has completed the gate by hand, which is the one thing
    that cannot be redone — so a failure here is reported and stepped over, never raised.
    """
    try:
        content = await page.content()
    except Exception:  # noqa: BLE001
        logger.warning("Could not save %s HTML (the page navigated or closed).", label)
        return
    await asyncio.to_thread(path.write_text, content, encoding="utf-8")
    logger.info("Snapshot → %s", path)


def _keep_downloads(context: Any, page: Any, dest_dir: Path) -> list[asyncio.Future]:  # noqa: ANN401
    """Save every download the operator starts, on the gate page or any popup.

    An attached browser's downloads land in a Playwright temp dir that is deleted on
    disconnect, so without this the file unlocked by hand is gone the moment Done is clicked.
    """
    saves: list[asyncio.Future] = []

    # Plain functions: Playwright tags a handler with an attribute, which a bound method
    # cannot carry, so page.on raises at attach time.
    def keep(download: Any) -> None:  # noqa: ANN401
        saves.append(asyncio.ensure_future(_save(download, dest_dir)))

    def watch(new_page: Any) -> None:  # noqa: ANN401
        new_page.on("download", keep)

    page.on("download", keep)
    context.on("page", watch)
    return saves


async def _save(download: Any, dest_dir: Path) -> None:  # noqa: ANN401
    dest = await save_download(download, _free_path(dest_dir / download.suggested_filename))
    logger.info("Saved inspect download → %s", dest)


def _free_path(path: Path) -> Path:
    """`path`, or `name (n).ext` if taken — these files keep the gate's own name, and
    artists reuse names like master.wav."""
    n = 1
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


async def _finish_saves(saves: list[asyncio.Future]) -> None:
    if not saves:
        return
    logger.info("Waiting for %d download(s) to finish saving…", len(saves))
    done, pending = await asyncio.wait(saves, timeout=_SAVE_TIMEOUT_S)
    if pending:
        logger.warning(
            "%d download(s) still transferring after %ss — they are lost when the browser "
            "detaches. Download them again from the gate page.",
            len(pending),
            _SAVE_TIMEOUT_S,
        )
    for task in done:
        if task.exception() is not None:
            logger.warning("A download could not be saved: %s", task.exception())


async def inspect_gate(url: str) -> None:
    """Open a gate page, wait for a manual unlock, and report what the unlock changed."""
    debug_dir = get_debug_dir()
    # The unlock being measured is performed by hand, so this one always needs a window.
    async with attached_browser(headed=True) as context:
        page = await context.new_page()
        saves = _keep_downloads(context, page, DOWNLOAD_DIR or get_log_dir() / "downloads")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            logger.info("Gate page open: %s", page.url)

            before = await _settled_snapshot(page, "before")
            logger.info("Captured %d elements.", len(before))
            await _write_page(page, debug_dir / "inspect-before.html", "before")

            await _wait_for_done(page)
            if page.is_closed():
                # Downloads the operator started are still saved, in the finally below.
                logger.warning("The gate tab was closed before Done; no after-snapshot.")
                return

            # Before the after-snapshot, or our own button lands in the diff as a NEW element.
            try:
                await page.evaluate(_REMOVE_DONE_BUTTON_JS)
            except Exception:  # noqa: BLE001
                logger.warning("Could not remove the Done button; expect it in the diff below.")

            after = await _settled_snapshot(page, "after")
            await _write_page(page, debug_dir / "inspect-after.html", "after")
            logger.info("─" * 60)
            _report(before, after)
            logger.info("─" * 60)
        finally:
            await _finish_saves(saves)
