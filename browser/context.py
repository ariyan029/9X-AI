"""
browser/context.py — Persistent browser context factory with stealth evasion.

Creates a Playwright persistent browser context that preserves cookies,
localStorage, and session tokens across restarts. Integrates playwright-stealth
for anti-bot detection evasion.
"""

import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Playwright

from config.settings import Settings

# Attempt to import stealth; graceful fallback if not available
try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False


class BrowserContextManager:
    """
    Manages the lifecycle of a persistent Playwright browser context.
    
    Features:
    - Persistent user data directory for session continuity
    - Anti-automation flag suppression
    - playwright-stealth integration for fingerprint evasion
    - Realistic viewport, user agent, and locale settings
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None

    async def create_context(self) -> BrowserContext:
        """
        Create and return a persistent browser context.
        
        The context uses a user data directory that preserves
        cookies, localStorage, and other session data across restarts.
        
        Returns:
            Configured BrowserContext with stealth applied.
        """
        # Ensure user data directory exists
        user_data_dir = Path(self.settings.USER_DATA_DIR)
        user_data_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.settings.HEADLESS,
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Kolkata",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process,CalculateNativeWinOcclusion",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-infobars",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )

        # Apply stealth scripts to all pages (current and future)
        if HAS_STEALTH:
            for page in self._context.pages:
                await stealth_async(page)
            self._context.on("page", lambda page: asyncio.ensure_future(stealth_async(page)))

        return self._context

    async def close(self):
        """Gracefully close browser context and Playwright instance."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    @property
    def context(self) -> Optional[BrowserContext]:
        """Access the current browser context (None if not created)."""
        return self._context
