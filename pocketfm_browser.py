"""
Pocket FM browser-session helper.

This does NOT use Pocket FM OTP API. It uses a real Chromium browser profile.
Login once manually with:

    python pocketfm_browser.py --login

Then the Telegram bot can reuse the saved profile to open episode pages and capture
.m3u8 requests from Network traffic.

Use only for content your account is authorized to access.
"""

import argparse
import asyncio
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

WEB = "https://pocketfm.com"
PROFILE_DIR = os.environ.get("POCKETFM_PROFILE_DIR", "pocketfm_profile")
HEADLESS = os.environ.get("POCKETFM_HEADLESS", "true").lower() in ("1", "true", "yes")

M3U8_RE = re.compile(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*")
CLOUDFRONT_RE = re.compile(r"https://[a-z0-9.-]*cloudfront\.net/[^\s\"'<>]+", re.I)


def normalize_episode_url(url_or_slug: str) -> str:
    text = url_or_slug.strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    slug = text.strip("/")
    return f"{WEB}/episode/{slug}"


def _clean_url(url: str) -> str:
    return url.replace("\\/", "/").rstrip("\"' ,;\\")


def _find_m3u8(text: str) -> Optional[str]:
    if not text:
        return None
    text = text.replace("\\/", "/")
    hit = M3U8_RE.search(text)
    if hit:
        return _clean_url(hit.group(0))
    # Some responses first expose a CloudFront URL without a strict .m3u8 regex match.
    hit = CLOUDFRONT_RE.search(text)
    if hit and ".m3u8" in hit.group(0):
        return _clean_url(hit.group(0))
    return None


async def manual_login() -> None:
    """Open browser visibly so user can log in once and save session cookies."""
    profile = Path(PROFILE_DIR)
    profile.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await context.new_page()
        await page.goto(f"{WEB}/login", wait_until="domcontentloaded", timeout=60000)
        print("\nLogin in the opened browser window.")
        print("After login is complete, close the browser window or press Ctrl+C here.\n")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        await context.close()


async def capture_episode_m3u8(url_or_slug: str, timeout_ms: int = 45000) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Open an episode page using saved browser profile and capture an .m3u8 URL.
    Returns: (m3u8_url, title, status)
    """
    profile = Path(PROFILE_DIR)
    if not profile.exists():
        return None, "", f"Profile not found: {PROFILE_DIR}. Run `python pocketfm_browser.py --login` first."

    target_url = normalize_episode_url(url_or_slug)
    found: Optional[str] = None
    seen = set()

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=HEADLESS,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        page = await context.new_page()

        async def inspect_response(response):
            nonlocal found
            if found:
                return
            url = response.url
            if url in seen:
                return
            seen.add(url)

            if ".m3u8" in url:
                found = _clean_url(url)
                return

            # Avoid reading large irrelevant binaries.
            ct = (response.headers.get("content-type") or "").lower()
            useful = any(x in url.lower() for x in ("episode", "content", "stream", "playlist", "m3u8", "cloudfront"))
            if not useful and not any(x in ct for x in ("json", "text", "javascript")):
                return
            try:
                body = await response.text()
            except Exception:
                return
            hit = _find_m3u8(body)
            if hit:
                found = hit

        page.on("response", lambda response: asyncio.create_task(inspect_response(response)))

        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeoutError:
            await context.close()
            return None, "", "Episode page load timed out."

        # Try to press common play buttons because media URLs often appear only after playback starts.
        for selector in [
            "button:has-text('Play')",
            "text=Play",
            "[aria-label*='Play']",
            "button[class*='play']",
            "div[class*='play']",
        ]:
            if found:
                break
            try:
                loc = page.locator(selector).first
                if await loc.count():
                    await loc.click(timeout=3000)
                    await page.wait_for_timeout(2500)
            except Exception:
                pass

        # Also inspect final HTML/source after hydration.
        deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000)
        while not found and asyncio.get_event_loop().time() < deadline:
            try:
                html = await page.content()
                hit = _find_m3u8(html)
                if hit:
                    found = hit
                    break
            except Exception:
                pass
            await page.wait_for_timeout(1000)

        title = ""
        try:
            title = await page.title()
        except Exception:
            pass

        await context.close()

    if found:
        return found, title, "OK"
    return None, title, "No .m3u8 captured. Make sure the saved browser profile is logged in and the episode can play in that account."


async def _cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true", help="Open Chromium for manual login and save session.")
    parser.add_argument("--episode", help="Episode URL or slug to capture .m3u8 from.")
    args = parser.parse_args()

    if args.login:
        await manual_login()
    elif args.episode:
        stream, title, status = await capture_episode_m3u8(args.episode)
        print("TITLE:", title)
        print("STATUS:", status)
        print("M3U8:", stream or "")
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(_cli())
