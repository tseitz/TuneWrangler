"""Unit tests for captcha detection helper."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from soundcloud_dl.gate_handlers.base import CaptchaKind, detect_captcha

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_detects_hcaptcha() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto((FIXTURE_DIR / "captcha_hcaptcha.html").as_uri())
        assert await detect_captcha(page) == CaptchaKind.HCAPTCHA
        await browser.close()


@pytest.mark.asyncio
async def test_detects_recaptcha() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto((FIXTURE_DIR / "captcha_recaptcha.html").as_uri())
        assert await detect_captcha(page) == CaptchaKind.RECAPTCHA
        await browser.close()


@pytest.mark.asyncio
async def test_detects_turnstile() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto((FIXTURE_DIR / "captcha_turnstile.html").as_uri())
        assert await detect_captcha(page) == CaptchaKind.TURNSTILE
        await browser.close()


@pytest.mark.asyncio
async def test_no_captcha_returns_none() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto((FIXTURE_DIR / "no_captcha.html").as_uri())
        assert await detect_captcha(page) is None
        await browser.close()
