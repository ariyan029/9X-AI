"""
Unit tests for OrchestratorRunner execution logic, double-bet prevention,
and timing window lockout handling.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from config.settings import Settings
from config.selectors import AppSelectors
from core.models import BetOrder, GameOutcome, EngineState
from browser.observer import ObserverSnapshot
from engine.runner import OrchestratorRunner


@pytest.fixture
def runner():
    settings = Settings(
        BASE_URL="http://localhost:8000",
        STOP_LOSS_BALANCE=100.0,
    )
    selectors = AppSelectors()
    return OrchestratorRunner(settings=settings, selectors=selectors, dry_run=True)


@pytest.mark.asyncio
async def test_runner_double_bet_prevention(runner):
    order = BetOrder(round_id="", target=GameOutcome.BIG, amount=1, ladder_index=0)
    runner._pending_order = order
    runner.executor.get_wallet_balance = AsyncMock(return_value=1000.0)

    # First attempt: Round 101, T=20s (valid window)
    snapshot = ObserverSnapshot(round_id="101", countdown_seconds=20)
    await runner._try_execute_bet(page=None, snapshot=snapshot)

    assert runner._pending_order is None
    assert runner._last_bet_round_id == "101"

    # Second attempt on same round (duplicate)
    duplicate_order = BetOrder(round_id="", target=GameOutcome.BIG, amount=1, ladder_index=0)
    runner._pending_order = duplicate_order
    await runner._try_execute_bet(page=None, snapshot=snapshot)

    # Must be suppressed and pending order cleared
    assert runner._pending_order is None


@pytest.mark.asyncio
async def test_runner_timing_lockout_clears_pending_order(runner):
    order = BetOrder(round_id="", target=GameOutcome.SMALL, amount=1, ladder_index=0)
    runner._pending_order = order

    # Countdown at 5s (< MIN_SECONDS 10s)
    snapshot = ObserverSnapshot(round_id="102", countdown_seconds=5)
    await runner._try_execute_bet(page=None, snapshot=snapshot)

    # Order must be discarded to prevent leaking into next round
    assert runner._pending_order is None


@pytest.mark.asyncio
async def test_runner_dry_run_low_balance_does_not_halt(runner):
    order = BetOrder(round_id="", target=GameOutcome.BIG, amount=500, ladder_index=5)
    runner._pending_order = order
    runner.executor.get_wallet_balance = AsyncMock(return_value=10.0)  # Low balance

    snapshot = ObserverSnapshot(round_id="103", countdown_seconds=20)
    await runner._try_execute_bet(page=None, snapshot=snapshot)

    # In dry-run mode, engine should NOT halt
    assert runner.state_machine.state != EngineState.HALT
    assert runner._pending_order is None
