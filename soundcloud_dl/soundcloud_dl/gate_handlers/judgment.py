"""JudgmentGateHandler: a TypeSafe `Choice` call decides the next element instead of YAML steps.

Pilot only (`--jev`). Subclasses GateHandler and overrides only `_run_steps`, so `run()`
still wraps the loop with OAuth popup handling and this handler still raises the same
CaptchaEncountered/StuckGate/GateStepError exceptions main.py already dispatches on.
"""

from __future__ import annotations

import contextlib
import logging
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Any

from typesafe_sdk import AsyncTypeSafeClient, Choice

from soundcloud_dl.downloads import looks_like_audio, rename_to_track, save_bytes
from soundcloud_dl.gate_handlers.base import GateHandler, StepResult, StuckGate
from soundcloud_dl.gate_handlers.captcha import CaptchaEncountered, detect_captcha
from soundcloud_dl.gate_handlers.dom_snapshot import find_element_by_key, snapshot_elements
from soundcloud_dl.gate_handlers.unlock import (
    find_download_target,
    is_download_element,
    is_unlocked_href,
    unlock_reached,
)

if TYPE_CHECKING:
    from playwright.async_api import Page, Response

    from soundcloud_dl.run_artifacts import RunRecorder

logger = logging.getLogger("soundcloud_dl.gate_handlers.judgment")

_MAX_ITERATIONS = 15
_ALREADY_UNLOCKED = "already_unlocked"

# Hypeddit only flips an action's class once it has confirmed that action against the
# SoundCloud API, which takes a few seconds each. 20s matches hypeddit.yaml's
# wait_for_download_ready timeout; the poll exits early on any change.
_SETTLE_POLL_MS = 500
_SETTLE_POLL_ATTEMPTS = 40

# Only covers the client-side render of the gate widget, not a user action. 15s.
_READY_POLL_ATTEMPTS = 30

# The gate is only declared stuck after several turns that moved nothing. One unchanged
# turn is normal — an OAuth popup can still be resolving in another window.
_MAX_IDLE_TURNS = 3

# Domain knowledge ported from hypeddit.yaml's comments (lines 200-327): the download
# button is usually visible from the start but stays locked — class contains "disable" or
# "disabled", href stays "javascript:void(0)" — until required actions are completed first.
_DEFAULT_GOAL = (
    "Unlock and reach the free download link for this track on this gate page. The "
    "download button is often visible immediately but is locked — its class contains "
    "'disable' or 'disabled', or its href is still 'javascript:void(0)' — until required "
    "actions are completed first. Those actions are commonly: connecting, following, "
    "reposting, or commenting on SoundCloud; following on Instagram or Spotify; or "
    "submitting an email. On many gates these show up as elements with a data-step of "
    "'follow', 'like', 'comment', or 'repost' whose class contains 'undone' until done "
    "and 'done' once completed. Do not pick the download button while it still looks "
    "locked by class or href — pick an incomplete ('undone') required action instead, and "
    "only choose the download button (or already_unlocked) once none remain."
)

# Matches template_vars keys used by main.py's handler construction (email/name/comment)
# against an input's name/placeholder attributes.
_FIELD_HINTS: dict[str, tuple[str, ...]] = {
    "email": ("email",),
    "name": ("name", "fullname", "full_name", "firstname"),
    "comment": ("comment", "message", "note"),
}


class JudgmentGateHandler(GateHandler):
    """Replaces the "which element next" decision with a TypeSafe Choice judgment call."""

    def __init__(
        self,
        *,
        goal: str = _DEFAULT_GOAL,
        recorder: RunRecorder | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        kwargs.setdefault("config", {"gate": "hypeddit_jev", "steps": []})
        super().__init__(**kwargs)
        self.goal = goal
        self.recorder = recorder
        # Constructed lazily so importing this module never requires TYPESAFE_API_KEY.
        self._client: AsyncTypeSafeClient | None = None

    def _get_client(self) -> AsyncTypeSafeClient:
        if self._client is None:
            self._client = AsyncTypeSafeClient()
        return self._client

    async def _snapshot(self, page: Page) -> dict[str, dict[str, Any]]:
        # First occurrence wins, matching find_element_by_key's preference, so a colliding
        # key never describes one element and click another.
        snapshot: dict[str, dict[str, Any]] = {}
        for el in await snapshot_elements(page):
            if el["visible"] and el["key"] not in snapshot:
                snapshot[el["key"]] = el
        return snapshot

    async def _find_element_by_key(self, page: Page, key: str) -> Any | None:  # noqa: ANN401
        return await find_element_by_key(page, key)

    def _match_template_field(self, el: dict[str, Any]) -> str | None:
        """Return the template_vars key matching this input's name/placeholder, if any."""
        haystack = f"{el.get('name', '')} {el.get('placeholder', '')}".lower()
        for var_key, hints in _FIELD_HINTS.items():
            if var_key not in self.template_vars:
                continue
            if any(hint in haystack for hint in hints):
                return var_key
        return None

    async def _ask_choice(self, page: Page, snapshot: dict[str, dict[str, Any]]) -> str:
        criteria: dict[str, str | None] = {
            key: f"<{el['tag']}> text={el['text']!r} class={el['cls']!r} href={el['href']!r}"
            for key, el in snapshot.items()
        }
        criteria[_ALREADY_UNLOCKED] = (
            "The real free-download link/button is already enabled and ready to click; "
            "no further element needs interaction."
        )
        client = self._get_client()
        response = await client.system_one(
            state={
                "goal": self.goal,
                "page_url": page.url,
                "elements": list(snapshot.values()),
            },
            questions={
                "next_action": Choice(
                    instructions=(
                        "Given the goal and the visible interactive elements on this gate "
                        "page, which element should be interacted with next to make "
                        "progress, or is the real download link/button already enabled?"
                    ),
                    criteria=criteria,
                )
            },
        )
        answer = response.choices["next_action"]
        logger.info(
            "[%s] jev choice=%r confidence=%.2f", self.gate_name, answer.choice, answer.confidence
        )
        return answer.choice

    async def _maybe_pause(self, action: str, target: dict[str, Any]) -> None:
        await self._pause_prompt(
            f"\n[PAUSE] [{self.gate_name}] Next: {action} on {target['key']!r} "
            f"(<{target['tag']}> text={target['text']!r} class={target['cls']!r}). "
            "Press Enter to run, Ctrl+C to abort: "
        )

    async def _click_with_force_fallback(
        self,
        page: Page,
        el: Any,  # noqa: ANN401
        key: str,
    ) -> None:
        """Force-click first; on failure, re-find the element and dispatch a JS click on it.

        force=True skips Playwright's actionability wait, which otherwise burns the full
        30s default whenever Hypeddit's carousel overlays a button mid-transition — the
        reason every data-step in hypeddit.yaml is marked force: true. The click stays
        trusted, which matters: the carousel checks event.isTrusted, so the JS-dispatched
        fallback below may not register at all and is a last resort, not an equal path.
        """
        try:
            await el.click(force=True, timeout=5_000)
        except Exception:
            logger.debug(
                "[%s] force click on %r failed; retrying with a JS-dispatched click",
                self.gate_name,
                key,
                exc_info=True,
            )
            el_retry = await self._find_element_by_key(page, key)
            if el_retry is None:
                raise
            await el_retry.evaluate("e => e.click()")

    async def _wait_for_gate_ready(self, page: Page) -> None:
        """Hold until the gate widget has rendered, or the DOM stops changing.

        Hypeddit builds the action carousel client-side, so a snapshot taken right after
        domcontentloaded offers the model only page furniture. It then picks the least-bad
        of a menu that never contained the right answer.
        """
        previous: dict[str, dict[str, Any]] | None = None
        for _ in range(_READY_POLL_ATTEMPTS):
            try:
                snapshot = await self._snapshot(page)
            except Exception:  # noqa: BLE001
                logger.debug("[%s] snapshot failed while waiting", self.gate_name, exc_info=True)
                await page.wait_for_timeout(_SETTLE_POLL_MS)
                continue
            if any(el["step"] for el in snapshot.values()) or unlock_reached(snapshot):
                return
            if snapshot == previous:
                logger.info("[%s] no gate actions found; DOM settled", self.gate_name)
                return
            previous = snapshot
            await page.wait_for_timeout(_SETTLE_POLL_MS)

    async def _settle(
        self, page: Page, before: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Poll until the page reacts to the last action, the gate unlocks, or time runs out."""
        snapshot = before
        for _ in range(_SETTLE_POLL_ATTEMPTS):
            await page.wait_for_timeout(_SETTLE_POLL_MS)

            # A Cloudflare wall appearing mid-wait replaces the page, which an
            # element-only comparison would read as change-therefore-progress.
            try:
                captcha = await detect_captcha(page)
            except Exception:  # noqa: BLE001
                captcha = None
            if captcha is not None:
                raise CaptchaEncountered(captcha, self.gate_name)

            try:
                snapshot = await self._snapshot(page)
            except Exception:  # noqa: BLE001
                # "Execution context was destroyed" — a click navigated. Expected; retry.
                logger.debug("[%s] snapshot failed mid-settle", self.gate_name, exc_info=True)
                continue

            if snapshot != before or unlock_reached(snapshot):
                return snapshot
        return snapshot

    async def _click_and_capture_download(  # noqa: C901, PLR0912, PLR0915
        self, page: Page, key: str
    ) -> bool:
        """Trimmed copy of base.py's download-capture logic (native event → href → intercept)."""
        el = await self._find_element_by_key(page, key)
        if el is None:
            return False
        if self.scroll_before_click:
            await el.scroll_into_view_if_needed()
        await self._random_delay(page)

        if self.download_dir is None:
            await self._click_with_force_fallback(page, el, key)
            return False

        downloaded = False
        try:
            async with page.expect_download(timeout=45_000) as download_info:
                await self._click_with_force_fallback(page, el, key)
            download = await download_info.value
            dest = self.download_dir / download.suggested_filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            await download.save_as(str(dest))
            dest = rename_to_track(dest, self.track_title)
            logger.info("[%s] Saved download → %s", self.gate_name, dest)
            downloaded = True
        except Exception:  # noqa: BLE001
            logger.debug("[%s] expect_download did not fire", self.gate_name, exc_info=True)

        if not downloaded:
            href = await el.get_attribute("href")
            if href and is_unlocked_href(href):
                if not href.startswith("http"):
                    href = urllib.parse.urljoin(page.url, href)
                logger.info(
                    "[%s] expect_download timed out; fetching href directly: %s",
                    self.gate_name,
                    href,
                )
                try:
                    response = await page.request.get(href)
                    if response.ok and looks_like_audio(
                        href,
                        response.headers.get("content-type"),
                        response.headers.get("content-disposition"),
                    ):
                        parsed = urllib.parse.urlparse(href)
                        filename = Path(parsed.path).name or "download"
                        dest = save_bytes(self.download_dir / filename, await response.body())
                        dest = rename_to_track(dest, self.track_title)
                        logger.info(
                            "[%s] Saved download (href fallback) → %s", self.gate_name, dest
                        )
                        downloaded = True
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "[%s] href fetch failed — falling through to response intercept",
                        self.gate_name,
                        exc_info=True,
                    )

        if not downloaded:
            captured: list[tuple[str, bytes]] = []

            async def _capture_audio(response: Response) -> None:
                if looks_like_audio(
                    response.url,
                    await response.header_value("content-type"),
                    await response.header_value("content-disposition"),
                ):
                    try:
                        body = await response.body()
                        captured.append((response.url, body))
                    except Exception:  # noqa: BLE001
                        logger.debug("[%s] audio body read failed", self.gate_name, exc_info=True)

            page.on("response", _capture_audio)
            try:
                el2 = await self._find_element_by_key(page, key)
                if el2 is not None:
                    await el2.evaluate("e => e.click()")
                for _ in range(40):
                    if captured:
                        break
                    await page.wait_for_timeout(500)
            finally:
                page.remove_listener("response", _capture_audio)

            if captured:
                dl_url, content = captured[0]
                parsed = urllib.parse.urlparse(dl_url)
                filename = Path(parsed.path).name or "download.mp3"
                if "." not in filename:
                    filename += ".mp3"
                dest = save_bytes(self.download_dir / filename, content)
                dest = rename_to_track(dest, self.track_title)
                logger.info("[%s] Saved download (response intercept) → %s", self.gate_name, dest)
                downloaded = True

        return downloaded

    def _action_kind(self, target: dict[str, Any], *, unlocked: bool) -> str:
        # Identity and an absent disable class are not enough on their own: hypeddit serves
        # #downloadProcess with no disable class while the gate is still shut, and routing
        # there costs a 45s expect_download plus a 20s response poll for nothing.
        if is_download_element(target) and (unlocked or is_unlocked_href(target["href"])):
            return "download"
        if (
            target["tag"] in ("input", "textarea")
            and self._match_template_field(target) is not None
        ):
            return "fill"
        return "click"

    def _resolve_target(
        self,
        choice: str,
        snapshot: dict[str, dict[str, Any]],
        results: dict[str, StepResult],
        i: int,
    ) -> dict[str, Any] | None:
        """Turn the model's choice into a snapshot element, or record why it could not be."""
        if choice == _ALREADY_UNLOCKED:
            target = find_download_target(snapshot)
            if target is None:
                logger.warning(
                    "[%s] model claimed already_unlocked but no download element matched; "
                    "continuing",
                    self.gate_name,
                )
                results[f"el_{i}_claimed_unlocked"] = StepResult.SKIPPED
            return target

        target = snapshot.get(choice)
        if target is None:
            logger.warning(
                "[%s] model chose unknown element key %r; continuing", self.gate_name, choice
            )
            results[f"el_{i}_unknown_choice"] = StepResult.SKIPPED
        return target

    async def _act(self, page: Page, kind: str, target: dict[str, Any]) -> tuple[StepResult, bool]:
        """Perform the chosen action. Returns (step result, downloaded)."""
        if kind == "download":
            downloaded = await self._click_and_capture_download(page, target["key"])
            return (StepResult.EXECUTED if downloaded else StepResult.SKIPPED, downloaded)

        el = await self._find_element_by_key(page, target["key"])
        if el is None:
            return (StepResult.SKIPPED, False)

        if kind == "fill":
            var_key = self._match_template_field(target)
            await el.fill("")
            await el.type(self.resolve_value("{{" + str(var_key) + "}}"), delay=self.type_delay_ms)
            return (StepResult.EXECUTED, False)

        if self.scroll_before_click:
            await el.scroll_into_view_if_needed()
        await self._random_delay(page)
        await self._click_with_force_fallback(page, el, target["key"])
        return (StepResult.EXECUTED, False)

    async def _log_turn(self, page: Page, i: int, snapshot: dict[str, dict[str, Any]]) -> None:
        logger.info(
            "[%s] turn %d: %d elements offered; gate actions=%s",
            self.gate_name,
            i,
            len(snapshot),
            {k: el["cls"].split()[-1] for k, el in snapshot.items() if el["step"]} or "NONE",
        )
        if self.recorder is not None:
            await self.recorder.screenshot(page, f"turn-{i:02d}-before")

    async def _run_steps(  # noqa: C901
        self, page: Page, results: dict[str, StepResult]
    ) -> dict[str, StepResult]:
        idle_turns = 0
        unlock_download_tried = False
        await self._wait_for_gate_ready(page)

        for i in range(1, _MAX_ITERATIONS + 1):
            # A closed OAuth popup doesn't reliably return focus to this tab, and each
            # iteration's AI round-trip takes far longer than the YAML flow's ~1s between
            # clicks — long enough for Chrome to throttle a backgrounded tab's timers and
            # stall a CSS carousel transition mid-flight. Re-focus before every snapshot.
            with contextlib.suppress(Exception):
                await page.bring_to_front()

            try:
                captcha = await detect_captcha(page)
            except Exception:  # noqa: BLE001
                captcha = None
            if captcha is not None:
                raise CaptchaEncountered(captcha, self.gate_name)

            snapshot = await self._snapshot(page)
            await self._log_turn(page, i, snapshot)

            unlocked = unlock_reached(snapshot)
            target = find_download_target(snapshot) if unlocked else None
            if target is not None and not unlock_download_tried:
                unlock_download_tried = True
                logger.info(
                    "[%s] turn %d: gate unlocked — download on %r", self.gate_name, i, target["key"]
                )
                await self._maybe_pause("download", target)
                result, downloaded = await self._act(page, "download", target)
                results[f"el_{i}_download"] = result
                if downloaded:
                    return results
                continue

            choice = await self._ask_choice(page, snapshot)
            target = self._resolve_target(choice, snapshot, results, i)
            if target is None:
                idle_turns += 1
                if idle_turns >= _MAX_IDLE_TURNS:
                    raise StuckGate(self.gate_name, last_step_id=f"jev_iter_{i}_no_progress")
                continue

            kind = self._action_kind(target, unlocked=unlocked)
            await self._maybe_pause(kind, target)

            try:
                result, downloaded = await self._act(page, kind, target)
                results[f"el_{i}_{kind}"] = result
                if downloaded:
                    return results
            except Exception:  # noqa: BLE001
                # A single bad judgment (e.g. picking an element hidden behind a carousel
                # overlay) shouldn't be fatal — log it and let the next iteration's choice
                # recover, same as the YAML engine treating one step's failure as skippable.
                logger.warning(
                    "[%s] action on %r failed; continuing",
                    self.gate_name,
                    target["key"],
                    exc_info=True,
                )
                results[f"el_{i}_action_failed"] = StepResult.SKIPPED

            settled = await self._settle(page, snapshot)
            changed = settled != snapshot
            logger.info(
                "[%s] turn %d: %s on %r → changed=%s unlocked=%s",
                self.gate_name,
                i,
                kind,
                target["key"],
                changed,
                unlock_reached(settled),
            )
            if self.recorder is not None:
                await self.recorder.screenshot(page, f"turn-{i:02d}-after")

            idle_turns = 0 if changed else idle_turns + 1
            if idle_turns >= _MAX_IDLE_TURNS:
                raise StuckGate(self.gate_name, last_step_id=f"jev_iter_{i}_no_progress")

        raise StuckGate(self.gate_name, last_step_id=f"jev_cap_{_MAX_ITERATIONS}")
