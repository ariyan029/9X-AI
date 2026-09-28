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
import json
import time
import hashlib
import asyncio
import urllib.request
from typing import Optional, List, Any
from dataclasses import dataclass, field

from playwright.async_api import Page, Response

from core.models import GameOutcome, RoundResolution
from config.selectors import AppSelectors, SelectorTarget


# Regex for validating round IDs (8-16 digit strings)
ROUND_ID_PATTERN = re.compile(r"^\d{8,16}$")


def fetch_api_history_sync(type_id: int = 30, page_size: int = 10) -> List[RoundResolution]:
    """
    Directly queries real-time CDN and Veergame REST API for round resolutions.
    Bypasses frontend race conditions and DOM scraping latency.
    """
    # Strategy 1: High-speed CDN endpoint (sub-150ms latency, zero auth required)
    try:
        cdn_url = f"https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json?ts={int(time.time() * 1000)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.veergame41.com/",
        }
        req = urllib.request.Request(cdn_url, headers=headers)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", {}).get("list", [])
            resolutions = []
            for item in items[:page_size]:
                issue = str(item.get("issueNumber") or "").strip()
                num_val = item.get("number")
                if issue and num_val is not None and str(num_val).strip().isdigit():
                    num = int(str(num_val).strip())
                    outcome = GameOutcome.from_number(num)
                    resolutions.append(
                        RoundResolution(
                            round_id=issue,
                            result_number=num,
                            outcome=outcome,
                        )
                    )
            if resolutions:
                return resolutions
    except Exception:
        pass

    # Strategy 2: Signed REST API fallback
    try:
        t = {
            'typeId': type_id,
            'pageSize': page_size,
            'pageNo': 1,
            'language': 1,
            'random': '3c3d5e7f8a9b4c2e1d0f5a7b8c9d0e1f',
        }
        n = {k: t[k] for k in sorted(t.keys()) if k not in ['signature', 'timestamp', 'track', 'xosoBettingData']}
        sig_str = json.dumps(n, separators=(',', ':'))
        t['signature'] = hashlib.md5(sig_str.encode('utf-8')).hexdigest().upper()
        t['timestamp'] = int(time.time())

        data = json.dumps(t).encode('utf-8')
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Origin': 'https://www.veergame41.com',
            'Referer': 'https://www.veergame41.com/',
            'Ar-Origin': 'https://www.veergame41.com'
        }
        req = urllib.request.Request(
            'https://api.veergameapi.com/api/webapi/GetNoaverageEmerdList',
            data=data,
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            res_json = json.loads(resp.read().decode('utf-8'))

        items = []
        if isinstance(res_json, dict):
            data_field = res_json.get('data')
            if isinstance(data_field, dict):
                items = data_field.get('list') or data_field.get('gameslist') or []
            elif isinstance(data_field, list):
                items = data_field

        resolutions = []
        for item in items:
            if not isinstance(item, dict):
                continue
            issue = str(item.get("issueNumber") or item.get("issuenumber") or item.get("period") or "").strip()
            num_val = item.get("number")
            if issue and num_val is not None and str(num_val).strip().isdigit():
                num = int(str(num_val).strip())
                outcome = GameOutcome.from_number(num)
                resolutions.append(
                    RoundResolution(
                        round_id=issue,
                        result_number=num,
                        outcome=outcome,
                    )
                )
        return resolutions
    except Exception:
        return []


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
        self._processed_round_ids: set[str] = set()
        self._last_countdown: Optional[int] = None
        self._desync_counter: int = 0
        self._last_refresh_time: float = 0.0
        self._last_api_fetch_time: float = 0.0
        self.network_interceptor = NetworkInterceptor()

    async def attach_network(self, page: Page):
        """Attach network interceptor to listen for live API round resolutions."""
        if page is not None and hasattr(page, "on"):
            await self.network_interceptor.attach(page)

    async def fetch_live_history(self, type_id: int = 30) -> List[RoundResolution]:
        """Fetch live round resolutions asynchronously via direct signed API call."""
        try:
            return await asyncio.to_thread(fetch_api_history_sync, type_id)
        except Exception:
            return []

    async def trigger_history_refresh(self, page: Page) -> bool:
        """
        Trigger an immediate live refresh of game history directly from the signed API.
        Does not disrupt or click DOM elements, ensuring 100% browser rendering stability.
        """
        try:
            loop = asyncio.get_event_loop()
            now = loop.time()
            if now - self._last_refresh_time < 0.5:
                return False
            self._last_refresh_time = now

            type_id = 30
            if page and hasattr(page, "url") and isinstance(page.url, str):
                match = re.search(r"typeId=(\d+)", page.url)
                if match:
                    type_id = int(match.group(1))

            api_results = await self.fetch_live_history(type_id)
            if api_results:
                for r in api_results:
                    self.network_interceptor.record_resolution(r)
                return True
            return False
        except Exception:
            return False

    async def _query_text(
        self, page: Page, selector: SelectorTarget, timeout_ms: int = 500
    ) -> Optional[str]:
        """
        Query a DOM element's text content using CSS (primary) or XPath (fallback).
        
        Optimized with a fast non-blocking path (query_selector) first to avoid
        freezing the high-frequency polling loop during normal execution.
        
        Args:
            page: Playwright page instance.
            selector: SelectorTarget with CSS and optional XPath.
            timeout_ms: Maximum wait time in milliseconds if element is not immediately attached.
            
        Returns:
            Trimmed text content, or None if element not found.
        """
        # Fast non-blocking query (0ms delay)
        try:
            element = await page.query_selector(selector.css)
            if not element and selector.xpath:
                element = await page.query_selector(f"xpath={selector.xpath}")
            if element:
                text = await element.text_content()
                if text and text.strip():
                    return text.strip()
        except Exception:
            pass

        # Brief fallback wait if not immediately attached
        if timeout_ms > 0:
            short_timeout = min(timeout_ms, 300)
            try:
                element = await page.wait_for_selector(
                    selector.css, timeout=short_timeout, state="attached"
                )
                if element:
                    text = await element.text_content()
                    return text.strip() if text else None
            except Exception:
                pass

            if selector.xpath:
                try:
                    element = await page.wait_for_selector(
                        f"xpath={selector.xpath}", timeout=short_timeout, state="attached"
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
        
        Validates that the round ID contains digits (supports 3-24 digit IDs).
        
        Returns:
            Round ID string, or None if not found/invalid.
        """
        text = await self._query_text(page, self.selectors.current_round_id, timeout_ms=300)
        if text:
            match = re.search(r"\d{3,24}", text) or re.search(r"\d+", text)
            if match:
                return match.group(0)
        return None

    async def get_countdown_seconds(self, page: Page) -> Optional[int]:
        """
        Extract the remaining countdown seconds from the DOM.
        
        Handles both mm:ss (e.g., "00:25", "0:25") and plain seconds (e.g., "25").
        
        Returns:
            Integer seconds remaining (0-60), or None if not parseable.
        """
        text = await self._query_text(
            page, self.selectors.countdown_timer_seconds, timeout_ms=300
        )
        if text:
            parts = re.findall(r"\d+", text)
            if len(parts) == 4:
                # Format: 4 individual digits ['0', '0', '1', '8'] -> 00:18
                try:
                    minutes = int(parts[0]) * 10 + int(parts[1])
                    seconds = int(parts[2]) * 10 + int(parts[3])
                    total = minutes * 60 + seconds
                    if 0 <= total <= 60:
                        return total
                except ValueError:
                    pass
            elif len(parts) >= 2:
                # Format: mm:ss (e.g. ['00', '25'] or ['0', '15'])
                try:
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    total = minutes * 60 + seconds
                    if 0 <= total <= 60:
                        return total
                except ValueError:
                    pass
            elif len(parts) == 1:
                # Format: ss (e.g. ['25'])
                try:
                    seconds = int(parts[0])
                    if 0 <= seconds <= 60:
                        return seconds
                except ValueError:
                    pass
        return None

    async def get_latest_history(
        self, page: Page, limit: int = 10
    ) -> List[RoundResolution]:
        """
        Extract the most recent game history from the DOM.
        
        Parses the history table/list rows to build a list of
        RoundResolution objects. Supports extracting outcome from
        result numbers (0-9) or outcome labels (Big/Small).
        
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
                    round_id_match = re.search(r"\d{3,24}", round_id_text.strip()) or re.search(r"\d+", round_id_text.strip())
                    if not round_id_match:
                        continue
                    round_id = round_id_match.group(0)

                    result_number = None
                    outcome = None

                    # Strategy A: Extract from result number element (0-9)
                    if self.selectors.history_row_result_number:
                        number_el = await row.query_selector(
                            self.selectors.history_row_result_number.css
                        )
                        if number_el:
                            number_text = await number_el.text_content()
                            if number_text:
                                number_match = re.search(r"\d", number_text.strip())
                                if number_match:
                                    result_number = int(number_match.group(0))
                                    outcome = GameOutcome.from_number(result_number)

                    # Strategy B: If outcome not derived from number, check outcome column/badge
                    if outcome is None and self.selectors.history_row_result_outcome:
                        outcome_el = await row.query_selector(
                            self.selectors.history_row_result_outcome.css
                        )
                        if outcome_el:
                            outcome_text = await outcome_el.text_content()
                            if outcome_text:
                                text_lower = outcome_text.strip().lower()
                                if "big" in text_lower or text_lower == "b":
                                    outcome = GameOutcome.BIG
                                    result_number = 7
                                elif "small" in text_lower or text_lower == "s":
                                    outcome = GameOutcome.SMALL
                                    result_number = 2

                    if outcome is None:
                        continue

                    results.append(
                        RoundResolution(
                            round_id=round_id,
                            result_number=result_number if result_number is not None else (7 if outcome == GameOutcome.BIG else 2),
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
        Capture a complete game state snapshot from the DOM and network stream.
        
        Combines round ID, countdown, and history into a single
        ObserverSnapshot for processing by the orchestration loop.
        Automatically detects 1-round desyncs and triggers live UI
        refreshes when the DOM history lags behind the active round.
        """
        round_id = await self.get_current_round_id(page)
        countdown = await self.get_countdown_seconds(page)
        # Base history: use resolutions from DOM scraped history and network interceptor
        history = await self.get_latest_history(page)
        merged: dict[str, RoundResolution] = {r.round_id: r for r in history}
        for res in self.network_interceptor.get_resolutions():
            if res.round_id not in merged:
                merged[res.round_id] = res

        type_id = 30
        if page and hasattr(page, "url") and isinstance(page.url, str):
            match = re.search(r"typeId=(\d+)", page.url)
            if match:
                type_id = int(match.group(1))

        # Check if we need to query the signed API for fresh completed rounds:
        # Condition 1: No history loaded yet
        # Condition 2: Active round has advanced and our newest history is behind (lag >= 2)
        need_api_fetch = False
        if not merged:
            need_api_fetch = True
        elif round_id and round_id.isdigit():
            active_num = int(round_id)
            newest_num = max([int(r.round_id) for r in merged.values() if r.round_id.isdigit()] or [0])
            lag = active_num - newest_num
            if lag >= 2:
                need_api_fetch = True

        if need_api_fetch:
            loop = asyncio.get_event_loop()
            now = loop.time()
            if now - self._last_api_fetch_time >= 0.5:
                self._last_api_fetch_time = now
                if page is not None:
                    await self.trigger_history_refresh(page)
                else:
                    api_results = await self.fetch_live_history(type_id)
                    for r in api_results:
                        self.network_interceptor.record_resolution(r)

                for res in self.network_interceptor.get_resolutions():
                    merged[res.round_id] = res

        if merged:
            history = sorted(
                merged.values(),
                key=lambda x: int(x.round_id) if x.round_id.isdigit() else 0,
                reverse=True,
            )[:10]

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
        
        Supports numeric sequence check as well as rolling seen set
        to prevent string lexicographical comparison issues.
        
        Args:
            round_id: The round ID to check.
            
        Returns:
            True if this is a new round that hasn't been processed.
        """
        if not round_id or not round_id.strip():
            return False
            
        clean_id = round_id.strip()
        if clean_id in self._processed_round_ids:
            return False

        if self.last_processed_round_id is None:
            return True

        if clean_id == self.last_processed_round_id:
            return False

        # Numeric comparison if both round IDs are digits (prevents "1000" < "999" string bug)
        if clean_id.isdigit() and self.last_processed_round_id.isdigit():
            return int(clean_id) > int(self.last_processed_round_id)

        # Fallback to string comparison
        return clean_id > self.last_processed_round_id

    def mark_processed(self, round_id: str):
        """Mark a round as processed to prevent reprocessing."""
        clean_id = round_id.strip()
        self.last_processed_round_id = clean_id
        self._processed_round_ids.add(clean_id)
        if len(self._processed_round_ids) > 200:
            self._processed_round_ids = set(list(self._processed_round_ids)[-100:])

    @property
    def desync_count(self) -> int:
        """Number of consecutive identical countdown readings (potential clock freeze)."""
        return self._desync_counter


class NetworkInterceptor:
    """
    CDP network response interceptor for zero-latency game data.
    
    Listens for game API responses (HTTP or WebSocket) and extracts
    round results before they render in the DOM. Used as a primary
    data source where available, with DOM polling as fallback.
    """

    def __init__(self):
        self._resolutions: dict[str, RoundResolution] = {}
        self._listening: bool = False
        self._page: Optional[Page] = None
        self._handler = None

    async def attach(self, page: Page):
        """
        Start intercepting network responses for lottery results.
        
        Args:
            page: Playwright page to intercept responses on.
        """
        if self._listening and self._page == page:
            return

        self._page = page
        self._listening = True

        async def on_response(response: Response):
            if not self._listening:
                return
            try:
                url = response.url
                if response.ok and re.search(r"GetNoaverageEmerdList|EmerdList|GetLastFive|GetGameIssue|GetHistoryIssuePage|WinGo_30S", url, re.I):
                    try:
                        body = await response.json()
                        self._parse_response_body(body)
                    except Exception:
                        pass
            except Exception:
                pass

        self._handler = on_response
        if hasattr(page, "on"):
            page.on("response", on_response)

    def _parse_response_body(self, body: Any):
        """Parse raw API JSON response into structured RoundResolution objects."""
        if not isinstance(body, dict):
            return

        items = []
        data = body.get("data")
        if isinstance(data, dict):
            items = data.get("gameslist") or data.get("list") or []
        elif isinstance(data, list):
            items = data
        elif "list" in body and isinstance(body["list"], list):
            items = body["list"]
        elif "gameslist" in body and isinstance(body["gameslist"], list):
            items = body["gameslist"]

        for item in items:
            if not isinstance(item, dict):
                continue
            issue = str(item.get("issueNumber") or item.get("issuenumber") or item.get("period") or "").strip()
            num_val = item.get("number")
            if issue and num_val is not None and str(num_val).strip().isdigit():
                num = int(str(num_val).strip())
                outcome = GameOutcome.from_number(num)
                self._resolutions[issue] = RoundResolution(
                    round_id=issue,
                    result_number=num,
                    outcome=outcome,
                )

    def record_resolution(self, res: RoundResolution):
        """Record a single resolution into the interceptor cache."""
        if res and res.round_id:
            self._resolutions[res.round_id] = res

    def get_resolutions(self) -> List[RoundResolution]:
        """Return cached network-intercepted results sorted by round ID descending."""
        return sorted(
            self._resolutions.values(),
            key=lambda x: int(x.round_id) if x.round_id.isdigit() else 0,
            reverse=True,
        )

    def detach(self):
        """Stop listening for network responses."""
        self._listening = False
        if self._page and self._handler and hasattr(self._page, "remove_listener"):
            try:
                self._page.remove_listener("response", self._handler)
            except Exception:
                pass
        self._page = None
        self._handler = None
        self._resolutions.clear()
