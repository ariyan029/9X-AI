"""
browser/observer.py — DOM and network ingestion pipeline.

Extracts three critical variables from the target web application:
1. Current Round ID
2. Remaining Countdown Seconds  
3. Latest History (completed round results)

Uses a hybrid strategy: primary DOM polling with optional CDP
network interception fallback. Implements round deduplication
and clock desync detection.
"""

import re
import asyncio
from typing import Optional, List
from dataclasses import dataclass, field

from playwright.async_api import Page, Response

from core.models import GameOutcome, RoundResolution
from config.selectors import AppSelectors, SelectorTarget


# Regex for validating round IDs (8-16 digit strings)
ROUND_ID_PATTERN = re.compile(r"^\d{8,16}$")


@dataclass
class ObserverSnapshot:
    """
    Point-in-time snapshot of the game state from the DOM.
    
    Attributes:
        round_id: Current active round identifier.
        countdown_seconds: Remaining seconds in countdown (0-30).
        history: List of recent completed round results.
    """
    round_id: Optional[str] = None
    countdown_seconds: Optional[int] = None
    history: List[RoundResolution] = field(default_factory=list)


class DomObserver:
    """
    Asynchronous DOM scraper and data ingestion pipeline.
    
    Polls the target web application's DOM to extract round state,
    countdown timers, and outcome history. Implements deduplication
    to prevent processing stale or duplicate rounds.
    """

    def __init__(self, selectors: AppSelectors):
        self.selectors = selectors
        self.last_processed_round_id: Optional[str] = None
        self._last_countdown: Optional[int] = None
        self._desync_counter: int = 0

    async def _query_text(
        self, page: Page, selector: SelectorTarget, timeout_ms: int = 2000
    ) -> Optional[str]:
        """
        Query a DOM element's text content using CSS (primary) or XPath (fallback).
        
        Args:
            page: Playwright page instance.
            selector: SelectorTarget with CSS and optional XPath.
            timeout_ms: Maximum wait time in milliseconds.
            
        Returns:
            Trimmed text content, or None if element not found.
        """
        try:
            # Try CSS first
            element = await page.wait_for_selector(
                selector.css, timeout=timeout_ms, state="attached"
            )
            if element:
                text = await element.text_content()
                return text.strip() if text else None
        except Exception:
            pass

        # Fallback to XPath
        if selector.xpath:
            try:
                element = await page.wait_for_selector(
                    f"xpath={selector.xpath}", timeout=timeout_ms, state="attached"
                )
                if element:
                    text = await element.text_content()
                    return text.strip() if text else None
            except Exception:
                pass

        return None

    async def get_current_round_id(self, page: Page) -> Optional[str]:
        """
        Extract the current active round ID from the DOM.
        
        Validates that the round ID matches the expected digit pattern.
        
        Returns:
            Round ID string, or None if not found/invalid.
        """
        text = await self._query_text(page, self.selectors.current_round_id)
        if text:
            # Extract digit sequence from the text
            match = re.search(r"\d{8,16}", text)
            if match:
                return match.group(0)
        return None

    async def get_countdown_seconds(self, page: Page) -> Optional[int]:
        """
        Extract the remaining countdown seconds from the DOM.
        
        Returns:
            Integer seconds remaining (0-30), or None if not parseable.
        """
        text = await self._query_text(
            page, self.selectors.countdown_timer_seconds, timeout_ms=1000
        )
        if text:
            match = re.search(r"\d+", text)
            if match:
                seconds = int(match.group(0))
                if 0 <= seconds <= 30:
                    return seconds
        return None

    async def get_latest_history(
        self, page: Page, limit: int = 10
    ) -> List[RoundResolution]:
        """
        Extract the most recent game history from the DOM.
        
        Parses the history table/list rows to build a list of
        RoundResolution objects.
        
        Args:
            page: Playwright page instance.
            limit: Maximum number of history entries to return.
            
        Returns:
            List of RoundResolution (most recent first), or empty list.
        """
        results: List[RoundResolution] = []

        try:
            rows = await page.query_selector_all(self.selectors.history_table_rows.css)
            if not rows and self.selectors.history_table_rows.xpath:
                rows = await page.query_selector_all(
                    f"xpath={self.selectors.history_table_rows.xpath}"
                )

            for row in rows[:limit]:
                try:
                    # Extract round ID
                    round_id_el = await row.query_selector(
                        self.selectors.history_row_round_id.css
                    )
                    round_id_text = (
                        await round_id_el.text_content() if round_id_el else None
                    )
                    if not round_id_text:
                        continue
                    round_id_match = re.search(r"\d{8,16}", round_id_text.strip())
                    if not round_id_match:
                        continue
                    round_id = round_id_match.group(0)

                    # Extract result number
                    number_el = await row.query_selector(
                        self.selectors.history_row_result_number.css
                    )
                    number_text = (
                        await number_el.text_content() if number_el else None
                    )
                    if not number_text:
                        continue
                    number_match = re.search(r"\d", number_text.strip())
                    if not number_match:
                        continue
                    result_number = int(number_match.group(0))

                    # Derive outcome from number
                    outcome = GameOutcome.from_number(result_number)

                    results.append(
                        RoundResolution(
                            round_id=round_id,
                            result_number=result_number,
                            outcome=outcome,
                        )
                    )
                except (ValueError, AttributeError):
                    continue

        except Exception:
            pass

        return results

    async def take_snapshot(self, page: Page) -> ObserverSnapshot:
        """
        Capture a complete game state snapshot from the DOM.
        
        Combines round ID, countdown, and history into a single
        ObserverSnapshot for processing by the orchestration loop.
        """
        round_id = await self.get_current_round_id(page)
        countdown = await self.get_countdown_seconds(page)
        history = await self.get_latest_history(page)

        # Clock desync detection
        if countdown is not None:
            if self._last_countdown is not None and countdown == self._last_countdown:
                self._desync_counter += 1
            else:
                self._desync_counter = 0
            self._last_countdown = countdown

        return ObserverSnapshot(
            round_id=round_id,
            countdown_seconds=countdown,
            history=history,
        )

    def is_new_round(self, round_id: Optional[str]) -> bool:
        """
        Check if the given round ID represents a new, unprocessed round.
        
        Args:
            round_id: The round ID to check.
            
        Returns:
            True if this is a new round that hasn't been processed.
        """
        if round_id is None:
            return False
        if self.last_processed_round_id is None:
            return True
        return round_id > self.last_processed_round_id

    def mark_processed(self, round_id: str):
        """Mark a round as processed to prevent reprocessing."""
        self.last_processed_round_id = round_id

    @property
    def desync_count(self) -> int:
        """Number of consecutive identical countdown readings (potential clock freeze)."""
        return self._desync_counter


class NetworkInterceptor:
    """
    CDP network response interceptor for zero-latency game data.
    
    Listens for game API responses (WebSocket or HTTP) and extracts
    round results before they render in the DOM. Used as a primary
    data source where available, with DOM polling as fallback.
    """

    def __init__(self):
        self._latest_results: List[dict] = []
        self._listening: bool = False

    async def attach(self, page: Page, url_pattern: str = "**/api/game/**"):
        """
        Start intercepting network responses matching the URL pattern.
        
        Args:
            page: Playwright page to intercept responses on.
            url_pattern: Glob pattern for game API endpoints.
        """
        self._listening = True

        async def on_response(response: Response):
            if not self._listening:
                return
            try:
                if response.ok and re.search(r"game|result|round|bet", response.url):
                    body = await response.json()
                    if isinstance(body, dict):
                        self._latest_results.append(body)
                        # Keep only last 20 results
                        if len(self._latest_results) > 20:
                            self._latest_results = self._latest_results[-20:]
            except Exception:
                pass

        page.on("response", on_response)

    def get_latest_results(self) -> List[dict]:
        """Return cached network-intercepted results."""
        return list(self._latest_results)

    def detach(self):
        """Stop listening for network responses."""
        self._listening = False
        self._latest_results.clear()
