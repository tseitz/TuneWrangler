"""GateHandler: loads YAML step config and interprets steps presence-first."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import re
import sys
import urllib.parse
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from soundcloud_dl.downloads import (
    discard_if_fragment,
    is_whole_track,
    looks_like_asset,
    looks_like_audio,
    rename_to_track,
    save_bytes,
    save_download,
)
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, detect_captcha
from soundcloud_dl.gate_handlers.oauth_popup import handle_oauth_popup

if TYPE_CHECKING:
    from playwright.async_api import Page, Response

logger = logging.getLogger("soundcloud_dl.gate_handlers.base")


class StepResult(StrEnum):
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"


class StuckGate(RuntimeError):  # noqa: N818
    """Raised when a gate sequence stalls without a known cause. Track is left in manual_review."""

    def __init__(self, gate_name: str, last_step_id: str) -> None:
        super().__init__(
            f"[{gate_name}] Gate stuck after step '{last_step_id}' (no captcha, no progress)"
        )
        self.gate_name = gate_name
        self.last_step_id = last_step_id


class GateStepError(RuntimeError):
    """Raised when a required step cannot find its element."""


class GateHandler:
    """
    Loads a YAML step config and executes steps against a Playwright page.

    Steps are presence-driven: each step queries for its trigger element before
    acting. Optional steps are silently skipped when absent. Steps with depends_on
    are skipped if their parent step was skipped.
    """

    #: Subclasses set this to the path of their YAML config file.
    config_path: Path | None = None

    #: Auto-approving a consent screen is right for a gate asking for the throwaway
    #: per-download connect most of them use, and wrong for one asking for a broad,
    #: non-expiring grant on the account. A handler for the latter sets this False, and the
    #: run stops with the tab open so a person decides. See InfluencePlannerHandler.
    auto_approve_oauth: bool = True

    def __init__(  # noqa: PLR0913
        self,
        *,
        config: dict | None = None,
        template_vars: dict[str, str] | None = None,
        action_delay_min_ms: int = 300,
        action_delay_max_ms: int = 900,
        type_delay_ms: int = 80,
        scroll_before_click: bool = True,
        pause: bool = False,
        download_dir: Path | None = None,
        track_title: str | None = None,
    ) -> None:
        if config is None:
            if self.config_path is None:
                msg = "Either pass config= or set config_path on the subclass."
                raise ValueError(msg)
            with self.config_path.open() as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                msg = f"YAML config at {self.config_path} is empty or not a mapping."
                raise TypeError(msg)

        self.gate_name: str = config["gate"]
        self.steps: list[dict] = config.get("steps", [])
        self.template_vars: dict[str, str] = template_vars or {}
        self.action_delay_min_ms = action_delay_min_ms
        self.action_delay_max_ms = action_delay_max_ms
        self.type_delay_ms = type_delay_ms
        self.scroll_before_click = scroll_before_click
        self.pause = pause
        self.download_dir = download_dir
        self.track_title = track_title
        self.downloaded = False
        self._pause_warned = False

    def _note_saved(self, dest: Path, via: str = "") -> None:
        """Record that a file actually landed on disk.

        Callers ask this, never the step ids in the results dict. A step id is a name, and
        every gate config here has a non-terminal step called something like
        `wait_for_download_ready` — so matching on the name marked tracks done that had no
        file, and a track recorded done is never retried.
        """
        self.downloaded = True
        logger.info("[%s] Saved download%s → %s", self.gate_name, f" {via}" if via else "", dest)

    def resolve_value(self, value: str) -> str:
        """Substitute {{var}} placeholders from template_vars. Raises KeyError if missing."""

        def replace(m: re.Match[str]) -> str:
            key = m.group(1)
            if key not in self.template_vars:
                msg = f"Template var '{{{key}}}' not in template_vars"
                raise KeyError(msg)
            return self.template_vars[key]

        return re.sub(r"\{\{(\w+)\}\}", replace, value)

    async def _pause_prompt(self, message: str) -> None:
        """Block for Enter, unless there is no terminal to read it from."""
        if not self.pause:
            return
        if not sys.stdin.isatty():
            if not self._pause_warned:
                logger.warning(
                    "[%s] --pause ignored: stdin is not a terminal. Run from a real shell "
                    "to step through actions.",
                    self.gate_name,
                )
                self._pause_warned = True
            return
        await asyncio.to_thread(input, message)

    async def _random_delay(self, page: Page) -> None:
        ms = random.randint(self.action_delay_min_ms, self.action_delay_max_ms)  # noqa: S311
        await page.wait_for_timeout(ms)

    async def _find_element(
        self, page: Page, trigger: str, *, allow_hidden: bool = False
    ) -> Any | None:  # noqa: ANN401
        """Try each comma-separated selector; return first VISIBLE match or None.

        Visible elements always win over hidden ones regardless of selector order.
        If allow_hidden=True and no visible match is found, returns the first
        DOM match found (used for force-click steps where the element may be
        in a CSS slide/transform that Playwright considers not-visible).
        """
        selectors = [s.strip() for s in trigger.split(",")]
        hidden_fallback = None
        for selector in selectors:
            el = await page.query_selector(selector)
            if el is None:
                logger.debug("[%s] selector '%s' → not found", self.gate_name, selector)
                continue
            try:
                visible = await el.is_visible()
            except Exception:  # noqa: BLE001
                visible = False
            if visible:
                logger.debug("[%s] selector '%s' → found, visible", self.gate_name, selector)
                return el
            if allow_hidden and hidden_fallback is None:
                logger.debug(
                    "[%s] selector '%s' → found (allow_hidden, hidden fallback)",
                    self.gate_name,
                    selector,
                )
                hidden_fallback = el
            else:
                logger.debug(
                    "[%s] selector '%s' → found but not visible, skipping",
                    self.gate_name,
                    selector,
                )
        if hidden_fallback is not None:
            logger.debug("[%s] no visible element; using hidden fallback", self.gate_name)
            return hidden_fallback
        return None

    async def _execute_step(self, page: Page, step: dict) -> None:  # noqa: C901, PLR0912, PLR0915
        """Execute a single step action against the found element."""
        force = step.get("force", False)
        el = await self._find_element(page, step["trigger"], allow_hidden=force)
        if el is None:
            return  # caller handles required/optional logic

        action = step["action"]
        # skip scroll for force steps — scroll_into_view_if_needed retries for 30s
        # on hidden elements; JS-clicked elements don't need to be in view anyway.
        if self.scroll_before_click and action in ("click", "fill") and not force:
            await el.scroll_into_view_if_needed()

        await self._random_delay(page)

        if action == "click":
            if step.get("download") and self.download_dir is not None:
                # 45s: SC OAuth popup can appear 15-20s after the click; allow ~25s for
                # Hypeddit to process the auth callback and serve the download.
                # On custom-domain gates the click may navigate instead of triggering
                # a download event — fall back to fetching the href directly.
                downloaded = False
                try:
                    async with page.expect_download(timeout=45_000) as download_info:
                        if force:
                            if await el.is_visible():
                                await el.click(force=True)
                            else:
                                await el.evaluate("e => e.click()")
                        else:
                            await el.click()
                    download = await download_info.value
                    if looks_like_asset(download.suggested_filename) or looks_like_asset(
                        download.url
                    ):
                        logger.warning(
                            "[%s] ignoring a download that looks like a page asset: %s",
                            self.gate_name,
                            download.suggested_filename,
                        )
                    else:
                        # Not fatal either way: the href fetch and the response intercept
                        # below are still to come, and one of them is usually what gets
                        # the real file.
                        saved = discard_if_fragment(
                            await save_download(
                                download, self.download_dir / download.suggested_filename
                            ),
                            download.url,
                        )
                        if saved is not None:
                            dest = rename_to_track(saved, self.track_title)
                            self._note_saved(dest)
                            downloaded = True
                except Exception:  # noqa: BLE001, S110
                    pass
                if not downloaded:
                    # Fallback 1: fetch the href directly.
                    # Handles both absolute URLs and relative paths (e.g. /download/6353).
                    href = await el.get_attribute("href")
                    if href and href not in ("", "#", "javascript:void(0)"):
                        if not href.startswith("http"):
                            href = urllib.parse.urljoin(page.url, href)
                        logger.info(
                            "[%s] expect_download timed out; fetching href directly: %s",
                            self.gate_name,
                            href,
                        )
                        try:
                            response = await page.request.get(href)
                            if not response.ok:
                                logger.debug(
                                    "[%s] href fetch HTTP %d — skipping to response intercept",
                                    self.gate_name,
                                    response.status,
                                )
                            elif not looks_like_audio(
                                href,
                                response.headers.get("content-type"),
                                response.headers.get("content-disposition"),
                                response.status,
                            ):
                                logger.debug(
                                    "[%s] href fetch returned %s — not a file, skipping",
                                    self.gate_name,
                                    response.headers.get("content-type"),
                                )
                            else:
                                body = await response.body()
                                if is_whole_track(href, len(body)):
                                    parsed = urllib.parse.urlparse(href)
                                    filename = Path(parsed.path).name or "download"
                                    dest = save_bytes(self.download_dir / filename, body)
                                    dest = rename_to_track(dest, self.track_title)
                                    self._note_saved(dest, "(href fallback)")
                                    downloaded = True
                        except Exception:  # noqa: BLE001
                            logger.debug(
                                "[%s] href fetch failed — falling through to response intercept",
                                self.gate_name,
                                exc_info=True,
                            )
                if not downloaded:
                    # Fallback 2: JS-void href (e.g. Hypeddit white-label) — intercept the
                    # network response that carries the audio file after the button click.
                    captured: list[tuple[str, bytes]] = []

                    async def _capture_audio(response: Response) -> None:
                        if looks_like_audio(
                            response.url,
                            await response.header_value("content-type"),
                            await response.header_value("content-disposition"),
                            response.status,
                        ):
                            try:
                                body = await response.body()
                                # Keep polling rather than settling for this one: the
                                # player's segments arrive throughout, so the first
                                # audio-shaped response is routinely not the track.
                                if is_whole_track(response.url, len(body)):
                                    captured.append((response.url, body))
                            except Exception:  # noqa: BLE001
                                logger.debug(
                                    "[%s] audio body read failed", self.gate_name, exc_info=True
                                )

                    page.on("response", _capture_audio)
                    try:
                        # Re-find element — may be stale after the 45s expect_download wait.
                        el2 = await self._find_element(page, step["trigger"], allow_hidden=force)
                        if el2 is not None:
                            await el2.evaluate("e => e.click()")
                        # Poll up to 20s for an audio response to land.
                        for _ in range(40):
                            if captured:
                                break
                            await page.wait_for_timeout(500)
                    finally:
                        page.remove_listener("response", _capture_audio)

                    if not captured:
                        msg = f"[{self.gate_name}] Download failed: no audio response intercepted"
                        raise GateStepError(msg)

                    dl_url, content = captured[0]
                    parsed = urllib.parse.urlparse(dl_url)
                    filename = Path(parsed.path).name or "download.mp3"
                    if "." not in filename:
                        filename += ".mp3"
                    dest = save_bytes(self.download_dir / filename, content)
                    dest = rename_to_track(dest, self.track_title)
                    self._note_saved(dest, "(response intercept)")
            elif force:
                # For visible elements, use a trusted Playwright click with force=True
                # to bypass z-order pointer-intercept (carousel overlap).
                # For hidden elements (no bounding box), fall back to a JS click —
                # non-trusted but the only way to reach display:none elements.
                if await el.is_visible():
                    await el.click(force=True)
                else:
                    await el.evaluate("e => e.click()")
            else:
                nav_from_click = False
                try:
                    await el.click()
                except Exception as exc:
                    if "not attached to the dom" in str(exc).lower():
                        # Click triggered a page navigation; element detached during
                        # Playwright's intercept-retry window, but the click registered.
                        nav_from_click = True
                        logger.debug(
                            "[%s] '%s' click caused navigation (element detached — ok)",
                            self.gate_name,
                            step["trigger"],
                        )
                    else:
                        raise
                # Wait for any navigation triggered by the click to settle.
                if step.get("await_navigation") or nav_from_click:
                    try:  # noqa: SIM105
                        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
                    except Exception:  # noqa: BLE001, S110
                        pass
            await self._random_delay(page)  # let DOM settle after click (carousel transitions etc.)
        elif action == "fill":
            value = self.resolve_value(step.get("value", ""))
            await el.fill("")  # clear first
            await el.type(value, delay=self.type_delay_ms)
        elif action == "download_from_attribute":
            attr = step.get("attribute", "src")
            url = await el.get_attribute(attr)
            if not url:
                msg = f"[{self.gate_name}] attribute '{attr}' not found or empty on element"
                raise GateStepError(msg)
            if step.get("download") and self.download_dir is not None:
                response = await page.request.get(url)
                if not response.ok:
                    msg = f"[{self.gate_name}] HTTP {response.status} fetching {url}"
                    raise GateStepError(msg)
                parsed = urllib.parse.urlparse(url)
                filename = Path(parsed.path).name or "download.mp3"
                dest = save_bytes(self.download_dir / filename, await response.body())
                dest = rename_to_track(dest, self.track_title)
                self._note_saved(dest, f"(from {attr} attr)")
        elif action == "navigate":
            href = await el.get_attribute("href")
            if href:
                if not href.startswith("http"):
                    href = urllib.parse.urljoin(page.url, href)
                await page.goto(href, wait_until="domcontentloaded", timeout=30_000)
                await self._random_delay(page)
        elif action == "wait":
            timeout_ms = int(step.get("timeout_ms", 5000))
            wait_state = step.get("state", "visible")
            await page.wait_for_selector(step["trigger"], state=wait_state, timeout=timeout_ms)

    async def _dump_inputs(self, page: Page) -> None:
        """Log outerHTML of every input on the page — shown when a step finds nothing."""
        try:
            inputs = await page.evaluate(
                "Array.from(document.querySelectorAll('input')).map(el => el.outerHTML)"
            )
            if inputs:
                logger.debug("[%s] visible inputs on page:", self.gate_name)
                for html in inputs:
                    logger.debug("  %s", html)
            else:
                logger.debug("[%s] no <input> elements found on page", self.gate_name)
        except Exception:  # noqa: BLE001
            logger.debug("[%s] could not dump inputs", self.gate_name, exc_info=True)

    async def _dump_page_elements(self, page: Page) -> None:
        """Log all interactive elements (buttons, links, inputs, textareas) for debugging."""
        try:
            js = (
                "() => { const tags = ['button','a[href]','input','textarea'];"
                " return tags.flatMap(sel => Array.from(document.querySelectorAll(sel))"
                ".map(el => ({ tag: el.tagName.toLowerCase(),"
                " html: el.outerHTML.slice(0,200),"
                " visible: el.offsetParent!==null && getComputedStyle(el).display!=='none',"
                " text: (el.innerText||'').trim().slice(0,80) }))); }"
            )
            elements = await page.evaluate(js)
            logger.debug(
                "[%s] interactive elements on page (%d total):", self.gate_name, len(elements)
            )
            for el in elements:
                vis = "V" if el["visible"] else "H"
                logger.debug("  [%s] <%s> text=%r  html=%s", vis, el["tag"], el["text"], el["html"])
        except Exception:  # noqa: BLE001
            logger.debug("[%s] could not dump page elements", self.gate_name, exc_info=True)

    def on_new_page(self, page: Page) -> None:
        """A page or popup appeared in the context. Subclasses attach listeners here."""

    async def _close_popups(self, popups: list[Page], keep: set[Page]) -> None:
        """Shut every popup this run opened, once the run is over, except those in `keep`.

        Nothing else ever closed one. The context is the default context of a persistent
        real Chrome, so a popup left behind keeps running script against the user's live
        SoundCloud session for the rest of the playlist, and is picked up again by the next
        track's popup handler.

        `keep` holds consent popups we declined to approve. Those are the operator's to act
        on, and closing one makes the message telling them to press Allow a lie. A popup
        serving the file needs no entry here — the tasks are awaited before this runs, so
        its transfer has finished by now.
        """
        for popup in popups:
            if popup in keep or popup.is_closed():
                continue
            with contextlib.suppress(Exception):
                await popup.close()

    async def run(self, page: Page) -> dict[str, StepResult]:
        """
        Walk all steps. Return a dict of step_id → StepResult.

        Raises GateStepError if a required step's element is not found.
        Raises CaptchaEncountered if a captcha appears mid-flow.
        """
        results: dict[str, StepResult] = {}

        # Register popup handler so SoundCloud OAuth dialogs are auto-approved.
        _tasks: list[asyncio.Task] = []

        _popups: list[Page] = []
        _keep_open: set[Page] = set()

        def _on_popup(popup: Page) -> None:
            _popups.append(popup)
            # Ahead of the OAuth handler, and synchronously: that handler closes every popup
            # it does not recognise, and a gate serving its file from window.open() emits the
            # download on this page rather than on the gate's. Suppressed because this runs
            # inside Playwright's event emitter, where a raise would also drop the OAuth
            # approval and the close that follow it.
            with contextlib.suppress(Exception):
                self.on_new_page(popup)
            _tasks.append(
                asyncio.ensure_future(
                    handle_oauth_popup(
                        popup,
                        self.gate_name,
                        approve=self.auto_approve_oauth,
                        on_keep_open=_keep_open.add,
                    )
                )
            )

        page.context.on("page", _on_popup)
        try:
            return await self._run_steps(page, results)
        finally:
            page.context.remove_listener("page", _on_popup)
            # Drained before anything is closed, both because closing a popup out from
            # under an in-flight Allow click cancels it, and because a handler that has
            # not run yet has not had the chance to say "keep this one open".
            if _tasks:
                # asyncio.wait, never wait_for: wait_for cancels what is still pending on
                # timeout, which is the mid-flight OAuth approval this is protecting.
                await asyncio.wait(_tasks, timeout=3)
            await self._close_popups(_popups, _keep_open)

    async def _run_steps(  # noqa: C901
        self, page: Page, results: dict[str, StepResult]
    ) -> dict[str, StepResult]:
        """Inner step loop, separated so run() can wrap it with popup listener cleanup."""
        for step in self.steps:
            step_id: str = step["id"]
            trigger: str = step["trigger"]
            action: str = step["action"]
            is_required: bool = step.get("required", False)
            depends_on: str | None = step.get("depends_on")

            # Captcha check before each step. Real Chrome rarely triggers these,
            # but if one appears we abort cleanly so the orchestrator can mark
            # captcha_pending and move on.
            # Suppress navigation errors: some steps (e.g. Instagram follow) reload
            # the main page, so the context may be destroyed briefly between steps.
            try:
                captcha = await detect_captcha(page)
            except Exception:  # noqa: BLE001
                captcha = None
            if captcha is not None:
                raise CaptchaEncountered(captcha, self.gate_name)

            # Skip if parent step was skipped
            if depends_on and results.get(depends_on) == StepResult.SKIPPED:
                logger.debug(
                    "[%s] Skipping '%s' (depends_on '%s' was skipped)",
                    self.gate_name,
                    step_id,
                    depends_on,
                )
                results[step_id] = StepResult.SKIPPED
                continue

            await self._pause_prompt(
                f"\n[PAUSE] [{self.gate_name}] Next: '{step_id}' ({action}). "
                "Press Enter to run, Ctrl+C to abort: "
            )

            # 'wait' steps use wait_for_selector directly — they don't need _find_element.
            if action == "wait":
                timeout_ms = int(step.get("timeout_ms", 5000))
                wait_state = step.get("state", "visible")
                try:
                    await page.wait_for_selector(trigger, state=wait_state, timeout=timeout_ms)
                    logger.debug("[%s] wait step '%s' satisfied", self.gate_name, step_id)
                    results[step_id] = StepResult.EXECUTED
                except Exception:  # noqa: BLE001
                    if is_required:
                        msg = f"[{self.gate_name}] Required wait step '{step_id}' timed out"
                        raise GateStepError(msg) from None
                    logger.debug(
                        "[%s] wait step '%s' timed out (optional)", self.gate_name, step_id
                    )
                    results[step_id] = StepResult.SKIPPED
                continue

            el = await self._find_element(page, trigger, allow_hidden=step.get("force", False))

            if el is None:
                if logger.isEnabledFor(logging.DEBUG):
                    await self._dump_page_elements(page)
                if is_required:
                    msg = (
                        f"[{self.gate_name}] Required step '{step_id}' could not find "
                        f"trigger element: {trigger}"
                    )
                    raise GateStepError(msg)
                logger.debug(
                    "[%s] Skipping optional step '%s' (no visible element matched)",
                    self.gate_name,
                    step_id,
                )
                results[step_id] = StepResult.SKIPPED
                continue

            logger.info("[%s] Executing step '%s' (%s)", self.gate_name, step_id, step["action"])
            await self._execute_step(page, step)
            results[step_id] = StepResult.EXECUTED

        return results
