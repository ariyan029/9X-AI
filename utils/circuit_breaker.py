"""
utils/circuit_breaker.py — Safety circuit breakers for 9X-AI.

Monitors wallet balance, DOM desync errors, and provides
emergency kill switch functionality. Each breaker can independently
trigger an engine HALT.
"""

import asyncio
from typing import Optional
from pathlib import Path
from datetime import datetime

from loguru import logger


class BalanceCircuitBreaker:
    """
    Monitors wallet balance against minimum threshold and required stakes.
    
    Triggers HALT if:
    - Balance drops below STOP_LOSS_BALANCE
    - Balance is insufficient for the next required stake
    """

    def __init__(self, stop_loss_balance: float = 0.0):
        self.stop_loss_balance = stop_loss_balance

    def can_afford(self, balance: float, required_stake: int) -> bool:
        """
        Check if the current balance can cover the required stake.
        
        Args:
            balance: Current wallet balance.
            required_stake: The next bet amount to place.
            
        Returns:
            True if balance is sufficient and above stop-loss threshold.
        """
        if balance < self.stop_loss_balance:
            logger.critical(
                f"Balance {balance:.2f} is below stop-loss threshold "
                f"{self.stop_loss_balance:.2f}. HALT required."
            )
            return False
        if balance < required_stake:
            logger.critical(
                f"Balance {balance:.2f} is insufficient for stake "
                f"{required_stake}. HALT required."
            )
            return False
        return True

    def check_balance(self, balance: float) -> bool:
        """
        Simple balance threshold check (no stake requirement).
        
        Returns:
            True if balance is above stop-loss threshold.
        """
        return balance >= self.stop_loss_balance


class DesyncCircuitBreaker:
    """
    Monitors consecutive DOM reading failures.
    
    Triggers HALT if errors exceed the maximum retry threshold,
    capturing diagnostic screenshots and DOM snapshots.
    """

    def __init__(self, max_retries: int = 3, log_dir: Path = Path("./logs")):
        self.max_retries = max_retries
        self.log_dir = log_dir
        self._consecutive_errors: int = 0

    def record_error(self, error_message: str = ""):
        """
        Record a DOM desync or read error.
        
        Args:
            error_message: Description of the error encountered.
        """
        self._consecutive_errors += 1
        logger.warning(
            f"DOM desync error #{self._consecutive_errors}/{self.max_retries}: "
            f"{error_message}"
        )

    def record_success(self):
        """Reset the error counter after a successful DOM read."""
        self._consecutive_errors = 0

    def is_tripped(self) -> bool:
        """
        Check if the circuit breaker has been tripped.
        
        Returns:
            True if consecutive errors have reached the threshold.
        """
        return self._consecutive_errors >= self.max_retries

    async def capture_diagnostics(self, page=None):
        """
        Capture diagnostic screenshot and DOM snapshot for debugging.
        
        Args:
            page: Optional Playwright page to capture diagnostics from.
        """
        desync_dir = self.log_dir / "desync"
        desync_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if page is None:
            return

        is_closed = False
        try:
            res = getattr(page, "is_closed", None)
            if callable(res):
                val = res()
                if asyncio.iscoroutine(val):
                    val.close()
                else:
                    is_closed = bool(val)
        except Exception:
            is_closed = True

        if is_closed:
            logger.info("Page is already closed; skipping diagnostic screenshot capture.")
            return

        try:
            screenshot_path = desync_dir / f"screenshot_{timestamp}.png"
            await page.screenshot(path=str(screenshot_path))
            logger.info(f"Diagnostic screenshot saved: {screenshot_path}")

            dom_path = desync_dir / f"dom_snapshot_{timestamp}.html"
            content = await page.content()
            dom_path.write_text(content, encoding="utf-8")
            logger.info(f"DOM snapshot saved: {dom_path}")
        except Exception as e:
            err_str = str(e).lower()
            if "closed" in err_str or "target" in err_str:
                logger.info(f"Browser or page closed during diagnostic capture: {e}")
            else:
                logger.warning(f"Could not capture full diagnostics: {e}")

    @property
    def error_count(self) -> int:
        """Current consecutive error count."""
        return self._consecutive_errors

    def reset(self):
        """Reset the error counter."""
        self._consecutive_errors = 0


class EmergencyKillSwitch:
    """
    Handles operator abort signals (SIGINT/SIGTERM).
    
    Ensures clean shutdown without leaving unconfirmed actions
    or corrupted state.
    """

    def __init__(self):
        self._triggered: bool = False
        self._reason: str = ""

    def trigger(self, reason: str = "Operator abort"):
        """
        Activate the kill switch.
        
        Args:
            reason: Human-readable reason for the emergency stop.
        """
        self._triggered = True
        self._reason = reason
        logger.critical(f"EMERGENCY KILL SWITCH ACTIVATED: {reason}")

    @property
    def is_triggered(self) -> bool:
        """Check if the kill switch has been activated."""
        return self._triggered

    @property
    def reason(self) -> str:
        """Get the reason for the kill switch activation."""
        return self._reason

    def reset(self):
        """Reset the kill switch (for test or manual recovery)."""
        self._triggered = False
        self._reason = ""
