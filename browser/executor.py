"""
browser/executor.py — Humanized action execution engine & timing gatekeeper.

Handles all interaction with the target web application:
- Timing window validation (10s ≤ T ≤ 25s)
- Humanized mouse movements and click delays
- Target selection (Big/Small button clicks)
- Stake amount entry (input field or chip multipliers)
- Bet confirmation and result verification
"""

import asyncio
import random
from typing import Optional

from playwright.async_api import Page, ElementHandle

from core.models import GameOutcome, BetOrder
from config.selectors import AppSelectors, SelectorTarget
from config.settings import Settings


class TimingGatekeeper:
    """
    Strict timing window validator for bet execution.
    
    Ensures bets are only placed when the countdown is within
    the safe window [MIN_SECONDS, MAX_SECONDS]. Prevents late
    submissions that could be locked out by the game server.
    """
    MIN_SECONDS: int = 10
    MAX_SECONDS: int = 25

    @classmethod
    def is_within_window(cls, remaining_seconds: int) -> bool:
        """
        Check if the countdown is within the safe betting window.
        
        Args:
            remaining_seconds: Current countdown value (0-30).
            
        Returns:
            True if MIN_SECONDS <= remaining_seconds <= MAX_SECONDS.
        """
        return cls.MIN_SECONDS <= remaining_seconds <= cls.MAX_SECONDS

    @classmethod
    def configure(cls, min_sec: int, max_sec: int):
        """
        Override default timing boundaries from settings.
        
        Args:
            min_sec: Lower bound (seconds remaining).
            max_sec: Upper bound (seconds remaining).
        """
        cls.MIN_SECONDS = min_sec
        cls.MAX_SECONDS = max_sec


class ActionExecutor:
    """
    Humanized browser interaction engine.
    
    Executes bet orders with natural-looking mouse movements,
    randomized delays, and confirmation verification. Designed
    to avoid triggering heuristic bot detection filters.
    """

    def __init__(self, selectors: AppSelectors, settings: Settings):
        self.selectors = selectors
        self.settings = settings

    async def _human_delay(self, min_ms: int = 80, max_ms: int = 220):
        """
        Introduce a randomized human-like delay.
        
        Args:
            min_ms: Minimum delay in milliseconds.
            max_ms: Maximum delay in milliseconds.
        """
        delay = random.randint(min_ms, max_ms) / 1000.0
        await asyncio.sleep(delay)

    async def _human_click(self, page: Page, selector: SelectorTarget):
        """
        Click an element with humanized mouse movement and timing.
        
        Uses multi-step mouse movement to simulate natural cursor
        trajectory, with random micro-pauses.
        
        Args:
            page: Playwright page instance.
            selector: Target element selector.
            
        Raises:
            TimeoutError: If element is not found within timeout.
        """
        element = None
        # Check candidates to find a currently visible instance (avoids hidden modal popups)
        try:
            candidates = await page.query_selector_all(selector.css)
            for cand in candidates:
                if await cand.is_visible():
                    element = cand
                    break
        except Exception:
            pass

        if element is None:
            try:
                element = await page.wait_for_selector(
                    f"{selector.css} >> visible=true", timeout=2500
                )
            except Exception:
                pass

        if element is None:
            try:
                element = await page.wait_for_selector(
                    selector.css, timeout=3000, state="visible"
                )
            except Exception:
                pass

        if element is None and selector.xpath:
            try:
                element = await page.wait_for_selector(
                    f"xpath={selector.xpath}", timeout=2000, state="visible"
                )
            except Exception:
                pass

        if element is None:
            raise TimeoutError(
                f"Element not found: {selector.description or selector.css}"
            )

        # Click without scrolling — scroll_into_view causes the page to jump
        # and can dismiss bet popups ("floating" behavior).
        await self._human_delay(40, 100)
        try:
            await element.click(force=True)
        except Exception:
            # Last resort: use JavaScript click to avoid any scroll side-effects
            await element.evaluate("el => el.click()")
        await self._human_delay(40, 100)

    async def _is_popup_visible(self, page: Page) -> bool:
        """Check if the bet popup is currently visible in the DOM."""
        try:
            # Query all potential popup containers and check visibility.
            # Vant.js pre-renders .van-popup--bottom in the DOM with display:none,
            # so we MUST verify is_visible() — the CSS match alone is not enough.
            candidates = await page.query_selector_all(
                ".Betting__Popup, "
                "div[class*='Betting__Popup'], "
                ".van-popup--bottom"
            )
            for popup in candidates:
                if await popup.is_visible():
                    return True
        except Exception:
            pass
        return False

    async def _dismiss_stale_popup(self, page: Page):
        """
        Dismiss any leftover popup overlay before starting a new bet flow.
        
        Clicks the overlay backdrop and/or presses Escape to close stale popups
        that may block new bet placement.
        """
        try:
            overlay = await page.query_selector(
                ".van-overlay[style*='display'], .van-popup__overlay"
            )
            if overlay and await overlay.is_visible():
                await overlay.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # Also press Escape if popup is still visible after overlay click
        try:
            if await self._is_popup_visible(page):
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
        except Exception:
            pass

    async def select_target(self, page: Page, target: GameOutcome):
        """
        Click the Big or Small betting button.
        
        Args:
            page: Playwright page instance.
            target: Which outcome to bet on.
        """
        selector = (
            self.selectors.bet_button_big
            if target == GameOutcome.BIG
            else self.selectors.bet_button_small
        )
        await self._human_click(page, selector)

    async def _select_target_and_verify_popup(
        self, page: Page, target: GameOutcome, max_retries: int = 3
    ) -> bool:
        """
        Click the Big/Small button and verify the bet popup actually opens.
        
        Retries up to max_retries times if the popup doesn't appear.
        
        Args:
            page: Playwright page instance.
            target: Which outcome to bet on.
            max_retries: Maximum retry attempts.
            
        Returns:
            True if popup opened successfully.
        """
        for attempt in range(max_retries):
            try:
                await self.select_target(page, target)
                # Wait for popup to animate in
                await asyncio.sleep(0.8)

                if await self._is_popup_visible(page):
                    return True

                # Popup didn't open — wait a bit more and re-check
                await asyncio.sleep(0.5)
                if await self._is_popup_visible(page):
                    return True

                from loguru import logger
                logger.warning(
                    f"Bet popup did not open after clicking {target.value} "
                    f"(attempt {attempt + 1}/{max_retries}). Retrying..."
                )
                # Small backoff before retry
                await asyncio.sleep(0.3)
            except Exception as e:
                from loguru import logger
                logger.debug(f"select_target attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(0.3)

        return False

    async def set_amount(self, page: Page, amount: int):
        """
        Enter the bet amount via input field or chip multiplier buttons.
        
        Attempts direct input first. If no input field is available,
        falls back to chip multiplier button combinations.
        
        Args:
            page: Playwright page instance.
            amount: Stake amount in units.
        """
        if self.selectors.amount_input_field:
            try:
                # Find visible input element
                element = None
                candidates = await page.query_selector_all(self.selectors.amount_input_field.css)
                for cand in candidates:
                    if await cand.is_visible():
                        element = cand
                        break

                if element is None:
                    element = await page.wait_for_selector(
                        f"{self.selectors.amount_input_field.css} >> visible=true",
                        timeout=2000,
                    )

                if element:
                    await element.click()
                    await self._human_delay(30, 80)
                    # Triple-click to select all existing text, then type over it
                    await element.evaluate("el => el.select && el.select()")
                    await self._human_delay(20, 50)
                    await element.fill(str(amount))
                    await self._human_delay(30, 80)
                    await element.dispatch_event("input")
                    await element.dispatch_event("change")
                    await self._human_delay(30, 80)
                    return
            except Exception:
                pass

        # Fallback: use chip multiplier buttons
        await self._set_amount_via_chips(page, amount)

    async def _set_amount_via_chips(self, page: Page, amount: int):
        """
        Set bet amount using chip multiplier buttons.
        
        Decomposes the amount into combinations of available
        chip denominations (100, 10, 5, 1) and clicks accordingly.
        """
        chip_map = [
            (100, self.selectors.chip_multiplier_100),
            (10, self.selectors.chip_multiplier_10),
            (5, self.selectors.chip_multiplier_5),
            (1, self.selectors.chip_multiplier_1),
        ]

        remaining = amount
        for denomination, selector in chip_map:
            if selector is None:
                continue
            while remaining >= denomination:
                try:
                    await self._human_click(page, selector)
                    remaining -= denomination
                except Exception:
                    break

            if remaining == 0:
                break

    async def confirm_bet(self, page: Page):
        """
        Click the bet confirmation/submit button.
        
        First verifies the popup is still visible before attempting to
        find the confirm button. This prevents long timeout waits when
        the popup has been dismissed.
        """
        # Fast check: is the popup still visible?
        if not await self._is_popup_visible(page):
            raise TimeoutError(
                "Bet popup dismissed before confirm could be clicked"
            )

        try:
            # Try to click without scrolling to prevent jitter in fixed popups
            locator = page.locator(self.selectors.confirm_bet_button.css).locator("visible=true").first
            await locator.click(timeout=3000)
            await self._human_delay(40, 100)
        except RuntimeError:
            # Bet rejection — do NOT swallow, propagate immediately
            raise
        except Exception:
            # Timeout or element stale — fallback to human_click
            await self._human_click(page, self.selectors.confirm_bet_button)

    async def verify_confirmation(
        self, page: Page, timeout_ms: int = 3000
    ) -> bool:
        """
        Verify that the bet was accepted by the game server.
        
        Checks for success toast notification or wallet balance
        deduction within the specified timeout.
        
        Args:
            page: Playwright page instance.
            timeout_ms: Maximum wait time for confirmation.
            
        Returns:
            True if bet was confirmed, False if error or timeout.
        """
        try:
            # Check for success toast
            success = await page.wait_for_selector(
                self.selectors.bet_success_toast.css,
                timeout=timeout_ms,
                state="visible",
            )
            if success:
                return True
        except Exception:
            pass

        # Check for error toast
        try:
            error = await page.wait_for_selector(
                self.selectors.bet_error_toast.css,
                timeout=500,
                state="visible",
            )
            if error:
                error_text = await error.text_content()
                raise RuntimeError(f"Bet rejected: {error_text}")
        except TimeoutError:
            pass  # No error toast either

        return False

    async def get_wallet_balance(self, page: Page) -> Optional[float]:
        """
        Extract the current wallet balance from the DOM.
        
        Returns:
            Balance as float, or None if not parseable.
        """
        try:
            element = await page.wait_for_selector(
                self.selectors.wallet_balance_display.css,
                timeout=2000,
                state="attached",
            )
            if element:
                text = await element.text_content()
                if text:
                    # Extract numeric value (handles commas and currency symbols)
                    import re
                    clean = re.sub(r"[^\d.]", "", text.strip())
                    if clean:
                        val = float(clean)
                        if val == 0.0:
                            try:
                                refresh_btn = await page.query_selector(
                                    ".Wallet__C-balance-l2, .Wallet__C .van-icon, [class*='reload']"
                                )
                                if refresh_btn:
                                    await refresh_btn.click()
                                    await asyncio.sleep(0.8)
                                    updated_text = await element.text_content()
                                    if updated_text:
                                        clean_updated = re.sub(r"[^\d.]", "", updated_text.strip())
                                        if clean_updated:
                                            return float(clean_updated)
                            except Exception:
                                pass
                        return val
        except Exception:
            pass
        return None

    async def execute_bet_order(
        self, page: Page, order: BetOrder
    ) -> bool:
        """
        Execute a complete bet order: select target, set amount, confirm.
        
        Includes retry logic: if the popup dismisses or the confirm button
        can't be found, dismisses any stale popup and retries the full flow
        up to 2 times.
        
        Args:
            page: Playwright page instance.
            order: The bet order directive from the state machine.
            
        Returns:
            True if bet was confirmed successfully.
            
        Raises:
            RuntimeError: If bet is rejected by the game server.
            TimeoutError: If elements are not found after all retries.
        """
        from loguru import logger
        max_attempts = 2

        for attempt in range(max_attempts):
            try:
                # Step 0: Dismiss any stale popup from a previous failed attempt
                await self._dismiss_stale_popup(page)
                await asyncio.sleep(0.2)

                # Step 1: Select target and verify popup opens
                popup_opened = await self._select_target_and_verify_popup(
                    page, order.target, max_retries=3
                )
                if not popup_opened:
                    raise TimeoutError(
                        f"Bet popup failed to open after clicking {order.target.value}"
                    )

                # Step 2: Enter stake amount
                await self.set_amount(page, order.amount)

                # Allow reactivity to settle after input
                await asyncio.sleep(0.3)

                # Step 3: Confirm bet
                await self.confirm_bet(page)

                # Step 4: Verify confirmation
                return await self.verify_confirmation(page)

            except TimeoutError as e:
                if attempt < max_attempts - 1:
                    logger.warning(
                        f"Bet attempt {attempt + 1} failed: {e}. "
                        f"Dismissing popup and retrying..."
                    )
                    await self._dismiss_stale_popup(page)
                    await asyncio.sleep(0.5)
                else:
                    raise

        return False

