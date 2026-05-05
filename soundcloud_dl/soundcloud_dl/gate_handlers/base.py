"""Base GateHandler: loads YAML step config and interprets steps presence-first."""

from __future__ import annotations

import asyncio
import logging
import random
import re
import urllib.parse
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from playwright.async_api import Page, Response

logger = logging.getLogger("soundcloud_dl.gate_handlers.base")


class StepResult(StrEnum):
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"


class CaptchaKind(StrEnum):
    HCAPTCHA = "hcaptcha"
    RECAPTCHA = "recaptcha"
    TURNSTILE = "turnstile"
    CLOUDFLARE_INTERSTITIAL = "cloudflare_interstitial"


class CaptchaEncountered(RuntimeError):  # noqa: N818
    """Raised when a captcha is detected mid-flow. Track is left in captcha_pending state."""

    def __init__(self, kind: CaptchaKind, gate_name: str) -> None:
        super().__init__(f"[{gate_name}] Captcha encountered: {kind}")
        self.kind = kind
        self.gate_name = gate_name


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


_CAPTCHA_SELECTORS: tuple[tuple[CaptchaKind, str], ...] = (
    (CaptchaKind.HCAPTCHA, 'iframe[src*="hcaptcha.com"]'),
    (CaptchaKind.RECAPTCHA, 'iframe[src*="recaptcha"]'),
    (CaptchaKind.TURNSTILE, '.cf-turnstile, iframe[src*="challenges.cloudflare.com"]'),
)

_CLOUDFLARE_TEXT_PATTERNS = (
    "verify you are human",
    "checking your browser",
)

# reCAPTCHA v3 background iframes have near-zero size; only iframes at least this
# many pixels on each side are treated as a real, user-blocking challenge.
_RECAPTCHA_VISIBLE_MIN_PX = 50


async def detect_captcha(page: Page) -> CaptchaKind | None:
    """
    Return the first matching captcha kind on the page, or None.

    Checks each known captcha vendor's selector. As a fallback, scans visible body
    text for Cloudflare-style interstitial language.

    reCAPTCHA v3 (invisible) embeds a hidden iframe that is always present on many
    sites as background fraud detection — we skip it unless the iframe has a meaningful
    bounding box (>50px), which indicates a blocking challenge. hCaptcha and Turnstile
    widgets are always interactive so presence alone is enough for those.
    """
    for kind, selector in _CAPTCHA_SELECTORS:
        el = await page.query_selector(selector)
        if el is None:
            continue
        if kind == CaptchaKind.RECAPTCHA:
            # reCAPTCHA v3 iframes are invisible (tiny/zero size). Only flag when
            # the iframe is large enough to be a user-facing challenge.
            try:
                bbox = await el.bounding_box()
            except Exception:  # noqa: BLE001
                logger.debug("reCAPTCHA bounding_box() failed; treating as invisible")
                continue
            if (
                bbox is None
                or bbox["width"] < _RECAPTCHA_VISIBLE_MIN_PX
                or bbox["height"] < _RECAPTCHA_VISIBLE_MIN_PX
            ):
                continue
        return kind
    try:
        body_text = (await page.inner_text("body", timeout=500)).lower()
    except Exception:  # noqa: BLE001
        return None
    if any(p in body_text for p in _CLOUDFLARE_TEXT_PATTERNS):
        return CaptchaKind.CLOUDFLARE_INTERSTITIAL
    return None


class GateHandler:
    """
    Loads a YAML step config and executes steps against a Playwright page.

    Steps are presence-driven: each step queries for its trigger element before
    acting. Optional steps are silently skipped when absent. Steps with depends_on
    are skipped if their parent step was skipped.
    """

    #: Subclasses set this to the path of their YAML config file.
    config_path: Path | None = None

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

    def resolve_value(self, value: str) -> str:
        """Substitute {{var}} placeholders from template_vars. Raises KeyError if missing."""

        def replace(m: re.Match[str]) -> str:
            key = m.group(1)
            if key not in self.template_vars:
                msg = f"Template var '{{{key}}}' not in template_vars"
                raise KeyError(msg)
            return self.template_vars[key]

        return re.sub(r"\{\{(\w+)\}\}", replace, value)

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
                    dest = self.download_dir / download.suggested_filename
                    await download.save_as(str(dest))
                    if self.track_title:
                        ext = Path(dest).suffix
                        renamed = dest.parent / f"{self.track_title}{ext}"
                        dest.rename(renamed)
                        dest = renamed
                    logger.info("[%s] Saved download → %s", self.gate_name, dest)
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
                            else:
                                ct = (response.headers.get("content-type") or "").lower()
                                cd = (response.headers.get("content-disposition") or "").lower()
                                is_file = (
                                    "audio" in ct
                                    or "octet-stream" in ct
                                    or "force-download" in ct
                                    or "attachment" in cd
                                )
                                if not is_file:
                                    logger.debug(
                                        "[%s] href fetch returned %s — not a file, skipping",
                                        self.gate_name,
                                        ct,
                                    )
                                else:
                                    parsed = urllib.parse.urlparse(href)
                                    filename = Path(parsed.path).name or "download"
                                    content = await response.body()
                                    dest = self.download_dir / filename
                                    dest.write_bytes(content)
                                    if self.track_title:
                                        ext = Path(dest).suffix
                                        renamed = dest.parent / f"{self.track_title}{ext}"
                                        dest.rename(renamed)
                                        dest = renamed
                                    logger.info(
                                        "[%s] Saved download (href fallback) → %s",
                                        self.gate_name,
                                        dest,
                                    )
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
                        ct = (await response.header_value("content-type") or "").lower()
                        cd = (await response.header_value("content-disposition") or "").lower()
                        url_lower = response.url.lower()
                        is_audio = (
                            "audio" in ct
                            or "octet-stream" in ct
                            or "force-download" in ct
                            or "attachment" in cd
                            or any(
                                url_lower.endswith(ext)
                                for ext in (".mp3", ".wav", ".flac", ".aiff", ".aac", ".ogg")
                            )
                        )
                        if is_audio:
                            try:
                                body = await response.body()
                                captured.append((response.url, body))
                            except Exception:  # noqa: BLE001, S110
                                pass

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
                    dest = self.download_dir / filename
                    dest.write_bytes(content)
                    if self.track_title:
                        ext = Path(dest).suffix
                        renamed = dest.parent / f"{self.track_title}{ext}"
                        dest.rename(renamed)
                        dest = renamed
                    logger.info(
                        "[%s] Saved download (response intercept) → %s", self.gate_name, dest
                    )
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
                content = await response.body()
                dest = self.download_dir / filename
                dest.write_bytes(content)
                if self.track_title:
                    ext = Path(dest).suffix
                    renamed = dest.parent / f"{self.track_title}{ext}"
                    dest.rename(renamed)
                    dest = renamed
                logger.info("[%s] Saved download (from %s attr) → %s", self.gate_name, attr, dest)
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

    async def _handle_oauth_popup(self, popup: Page) -> None:  # noqa: C901, PLR0912, PLR0915
        """Auto-approve SoundCloud/Spotify OAuth popups; close ToneDen URL-visit popups."""
        try:
            # Use "load" — SoundCloud's auth page is a React SPA; Spotify's is similar.
            await popup.wait_for_load_state("load", timeout=15_000)
            url = popup.url
            is_sc = "soundcloud.com" in url
            is_sp = "accounts.spotify.com" in url
            is_toneden_visit = "toneden.io/auth/custom-url-visit" in url
            is_instagram = "instagram.com" in url
            if not is_sc and not is_sp and not is_toneden_visit and not is_instagram:
                return

            # Instagram follow and ToneDen URL-visit popups just need to be closed
            # after they load — no OAuth interaction required.
            if is_instagram:
                logger.debug("[%s] Instagram follow popup: %s", self.gate_name, url)
                try:
                    await popup.wait_for_timeout(1_000)
                    if not popup.is_closed():
                        await popup.close()
                except Exception:  # noqa: BLE001
                    pass  # popup already closed itself
                return

            # ToneDen's Instagram (and other URL-visit) steps open a popup that just
            # records the visit — no OAuth flow needed, just close it after it loads.
            if is_toneden_visit:
                logger.debug("[%s] ToneDen URL-visit popup: %s", self.gate_name, url)
                await popup.wait_for_timeout(1_500)
                if not popup.is_closed():
                    await popup.close()
                return

            vendor = "SoundCloud" if is_sc else "Spotify"
            logger.debug("[%s] %s OAuth popup: %s", self.gate_name, vendor, url)

            if is_sc:
                _allow_selector = (
                    "button:has-text('Allow'), button:has-text('Authorize'), "
                    "button:has-text('Connect'), input[type='submit'], button[type='submit']"
                )
            else:
                # Spotify's consent screen uses data-testid="auth-accept" or text "Agree"/"Allow".
                _allow_selector = (
                    "button[data-testid='auth-accept'], "
                    "button:has-text('Agree'), button:has-text('Allow'), "
                    "button:has-text('Accept'), button:has-text('Authorize')"
                )

            try:
                await popup.wait_for_selector(_allow_selector, state="visible", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass  # fall through to query_selector; will log if still missing

            allow = await popup.query_selector(_allow_selector)
            if allow is not None:
                logger.info("[%s] %s OAuth popup: clicking Allow", self.gate_name, vendor)
                await popup.wait_for_timeout(500)
                await allow.click()
                logger.info("[%s] %s OAuth popup: clicked Allow", self.gate_name, vendor)
                # Wait for the popup to redirect back to the gate host or close itself.
                # ToneDen redirects to toneden.io/auth/spotify/callback then closes;
                # Hypeddit redirects back to hypeddit.com. Either way the popup is done.
                try:
                    await popup.wait_for_url("*hypeddit.com*|*toneden.io*", timeout=8_000)
                    await popup.wait_for_timeout(500)
                except Exception:  # noqa: BLE001
                    pass  # popup closed itself or redirected elsewhere — both OK
            else:
                try:
                    btns = await popup.evaluate(
                        "Array.from(document.querySelectorAll('button,input[type=submit],a'))"
                        ".filter(el => el.offsetParent !== null)"
                        ".map(el => el.outerHTML.slice(0, 200))"
                    )
                    logger.debug(
                        "[%s] %s OAuth popup: Allow button not found. Visible elements: %s",
                        self.gate_name,
                        vendor,
                        btns,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "[%s] %s OAuth popup: Allow button not found (could not dump)",
                        self.gate_name,
                        vendor,
                    )
        except Exception:  # noqa: BLE001
            logger.debug("[%s] OAuth popup handler error", self.gate_name, exc_info=True)
        finally:
            if not popup.is_closed():
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

        def _on_popup(popup: Page) -> None:
            _tasks.append(asyncio.ensure_future(self._handle_oauth_popup(popup)))

        page.context.on("page", _on_popup)
        try:
            return await self._run_steps(page, results)
        finally:
            page.context.remove_listener("page", _on_popup)

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

            # Pause mode: wait for user to press Enter before each step.
            if self.pause:
                await asyncio.to_thread(
                    input,
                    f"\n[PAUSE] [{self.gate_name}] Next: '{step_id}' ({action}). "
                    "Press Enter to run, Ctrl+C to abort: ",
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
