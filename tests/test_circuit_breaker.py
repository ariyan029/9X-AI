"""
tests/test_circuit_breaker.py — Unit tests for safety circuit breakers.

Covers:
- BalanceCircuitBreaker:
  - Normal affordability check (balance >= stake)
  - Insufficient balance for stake (balance < stake)
  - Stop-loss threshold violation (balance < stop_loss_balance)
  - check_balance helper
- DesyncCircuitBreaker:
  - Error incrementing and threshold tripping
  - Success resets consecutive error count
  - Manual reset
  - capture_diagnostics with None page and mock page
- EmergencyKillSwitch:
  - Default untriggered state
  - Triggering with custom reason
  - Manual reset
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from utils.circuit_breaker import (
    BalanceCircuitBreaker,
    DesyncCircuitBreaker,
    EmergencyKillSwitch,
)


class TestBalanceCircuitBreaker:
    """Test suite for BalanceCircuitBreaker."""

    def test_sufficient_balance(self):
        breaker = BalanceCircuitBreaker(stop_loss_balance=100.0)
        assert breaker.can_afford(balance=500.0, required_stake=50) is True

    def test_balance_below_stop_loss(self):
        breaker = BalanceCircuitBreaker(stop_loss_balance=100.0)
        # Even though 80 > 10, it's below stop_loss_balance of 100
        assert breaker.can_afford(balance=80.0, required_stake=10) is False

    def test_balance_insufficient_for_stake(self):
        breaker = BalanceCircuitBreaker(stop_loss_balance=0.0)
        assert breaker.can_afford(balance=20.0, required_stake=50) is False

    def test_exact_balance_boundary(self):
        breaker = BalanceCircuitBreaker(stop_loss_balance=50.0)
        assert breaker.can_afford(balance=50.0, required_stake=50) is True

    def test_check_balance(self):
        breaker = BalanceCircuitBreaker(stop_loss_balance=50.0)
        assert breaker.check_balance(50.0) is True
        assert breaker.check_balance(100.0) is True
        assert breaker.check_balance(49.9) is False


class TestDesyncCircuitBreaker:
    """Test suite for DesyncCircuitBreaker."""

    def test_initial_state_not_tripped(self, tmp_path):
        breaker = DesyncCircuitBreaker(max_retries=3, log_dir=tmp_path)
        assert breaker.is_tripped() is False
        assert breaker.error_count == 0

    def test_trips_at_max_retries(self, tmp_path):
        breaker = DesyncCircuitBreaker(max_retries=3, log_dir=tmp_path)
        breaker.record_error("read failure 1")
        assert breaker.error_count == 1
        assert breaker.is_tripped() is False

        breaker.record_error("read failure 2")
        assert breaker.error_count == 2
        assert breaker.is_tripped() is False

        breaker.record_error("read failure 3")
        assert breaker.error_count == 3
        assert breaker.is_tripped() is True

    def test_success_resets_error_count(self, tmp_path):
        breaker = DesyncCircuitBreaker(max_retries=3, log_dir=tmp_path)
        breaker.record_error("fail 1")
        breaker.record_error("fail 2")
        assert breaker.error_count == 2

        breaker.record_success()
        assert breaker.error_count == 0
        assert breaker.is_tripped() is False

    def test_manual_reset(self, tmp_path):
        breaker = DesyncCircuitBreaker(max_retries=2, log_dir=tmp_path)
        breaker.record_error("fail 1")
        breaker.record_error("fail 2")
        assert breaker.is_tripped() is True

        breaker.reset()
        assert breaker.error_count == 0
        assert breaker.is_tripped() is False

    @pytest.mark.asyncio
    async def test_capture_diagnostics_without_page(self, tmp_path):
        breaker = DesyncCircuitBreaker(max_retries=3, log_dir=tmp_path)
        # Should execute cleanly without raising
        await breaker.capture_diagnostics(page=None)
        assert (tmp_path / "desync").exists()

    @pytest.mark.asyncio
    async def test_capture_diagnostics_with_mock_page(self, tmp_path):
        breaker = DesyncCircuitBreaker(max_retries=3, log_dir=tmp_path)
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.screenshot = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Mock DOM</body></html>")

        await breaker.capture_diagnostics(page=mock_page)

        mock_page.screenshot.assert_awaited_once()
        mock_page.content.assert_awaited_once()
        assert (tmp_path / "desync").exists()

    @pytest.mark.asyncio
    async def test_capture_diagnostics_handles_page_exception(self, tmp_path):
        breaker = DesyncCircuitBreaker(max_retries=3, log_dir=tmp_path)
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.screenshot = AsyncMock(side_effect=RuntimeError("Browser disconnected"))

        # Should catch exception internally and not crash
        await breaker.capture_diagnostics(page=mock_page)

    @pytest.mark.asyncio
    async def test_capture_diagnostics_when_page_closed(self, tmp_path):
        breaker = DesyncCircuitBreaker(max_retries=3, log_dir=tmp_path)
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=True)
        mock_page.screenshot = AsyncMock()

        # Should skip screenshot when page is closed
        await breaker.capture_diagnostics(page=mock_page)
        mock_page.screenshot.assert_not_called()


class TestEmergencyKillSwitch:
    """Test suite for EmergencyKillSwitch."""

    def test_initial_state(self):
        switch = EmergencyKillSwitch()
        assert switch.is_triggered is False
        assert switch.reason == ""

    def test_trigger_default_reason(self):
        switch = EmergencyKillSwitch()
        switch.trigger()
        assert switch.is_triggered is True
        assert switch.reason == "Operator abort"

    def test_trigger_custom_reason(self):
        switch = EmergencyKillSwitch()
        switch.trigger("SIGTERM received from OS")
        assert switch.is_triggered is True
        assert switch.reason == "SIGTERM received from OS"

    def test_reset(self):
        switch = EmergencyKillSwitch()
        switch.trigger("Crash")
        assert switch.is_triggered is True

        switch.reset()
        assert switch.is_triggered is False
        assert switch.reason == ""
