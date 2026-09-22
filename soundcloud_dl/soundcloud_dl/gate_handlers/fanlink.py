"""FanLink gate handler — clicks FREE DOWNLOAD, catches the new tab, navigates there."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page

from soundcloud_dl.gate_handlers.base import GateHandler, GateStepError, StepResult

_FREE_DL_SELECTOR = (
    "a:has(img.link-option-row-img[alt*='Free Download' i]), "
    "a:has(img.link-option-row-img[alt*='Free DL' i]), "
    "a:has-text('FREE DOWNLOAD'), "
    "a:has-text('Free Download')"
)


class FanLinkHandler(GateHandler):
    """The whole flow is run() below, so there is no step list and no YAML to load.

    config_path pointed at a fanlink.yaml that has never existed, and the base class opens
    it in __init__ — so every fanlink track died on FileNotFoundError before the gate was
    even fetched. Supplying the config inline is what JevHandler does for the same reason.
    """

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        kwargs.setdefault("config", {"gate": "fanlink", "steps": []})
        super().__init__(**kwargs)

    async def run(self, page: Page) -> dict[str, StepResult]:
        """
        Click FREE DOWNLOAD on the fanlink.tv landing page, then land on the real gate.

        Three cases after clicking:
        1. New tab opens (target=_blank) → grab its URL, close it, navigate current page there.
        2. Current page navigates in-tab → page.url already has the real gate URL.
        3. Neither → fall back to the href captured before the click.
        """
        el = await page.query_selector(_FREE_DL_SELECTOR)
        if el is None:
            msg = "No FREE DOWNLOAD link found on fanlink page"
            raise GateStepError(msg)

        # Capture href before clicking — el becomes stale if the page navigates.
        href_before = await el.get_attribute("href") or ""
        original_url = page.url

        # Broad catch covers expect_page timeout + Playwright click navigation errors
        # — both fall through to the in-tab nav / href fallback paths below.
        try:
            async with page.context.expect_page(timeout=10_000) as new_page_info:
                await el.click()
            new_page = await new_page_info.value
            await new_page.wait_for_load_state("domcontentloaded", timeout=15_000)
            real_url = new_page.url
            await new_page.close()
            await page.goto(real_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:  # noqa: BLE001
            current_url = page.url
            if current_url != original_url:
                # Click navigated the current tab — already on the real gate.
                pass
            elif href_before.startswith("http"):
                await page.goto(href_before, wait_until="domcontentloaded", timeout=30_000)
            else:
                msg = "Could not navigate from fanlink FREE DOWNLOAD link"
                raise GateStepError(msg) from None

        return {"click_free_download": StepResult.EXECUTED}
