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


@pytest.mark.asyncio
async def test_runner_desync_guard_delays_bet_and_triggers_refresh(runner):
    from core.models import RoundResolution

    order = BetOrder(round_id="", target=GameOutcome.BIG, amount=1, ladder_index=0)
    runner._pending_order = order
    runner.observer.trigger_history_refresh = AsyncMock(return_value=True)

    # Active round 1776, but history only up to 1774 (lag = 2)
    snapshot = ObserverSnapshot(
        round_id="20260924100051776",
        countdown_seconds=20,
        history=[
            RoundResolution(round_id="20260924100051774", result_number=4, outcome=GameOutcome.SMALL)
        ]
    )

    mock_page = MagicMock()
    await runner._try_execute_bet(page=mock_page, snapshot=snapshot)

    # Bet should NOT be executed yet because previous round outcome is missing
    assert runner._pending_order == order
    assert runner._last_bet_round_id is None
    # Refresh should have been triggered to fetch missing round 1775
    assert runner.observer.trigger_history_refresh.called


@pytest.mark.asyncio
async def test_runner_pending_order_cleared_on_win_or_idle(runner):
    from core.models import RoundResolution

    # Manually seed an existing pending order (e.g. from an earlier round)
    runner._pending_order = BetOrder(round_id="", target=GameOutcome.BIG, amount=15, ladder_index=3)

    # Resolution that results in IDLE (no streak trigger)
    snapshot = ObserverSnapshot(
        round_id="20260924100051800",
        countdown_seconds=20,
        history=[
            RoundResolution(round_id="20260924100051799", result_number=4, outcome=GameOutcome.SMALL)
        ]
    )

    await runner._process_history(snapshot)

    # Verify the old pending order was cleared because this round did not generate a new bet
    assert runner._pending_order is None


@pytest.mark.asyncio
async def test_runner_streak_resolution_timing_preserves_order_until_next_round(runner):
    """
    CRITICAL REGRESSION TEST:
    When a streak of 3 completes at T=1s of round 2270, the bet order targets
    round 2271. The runner must NOT discard the pending order when T=1s on round
    2270, but instead preserve it and execute once round 2271 starts and reaches
    the valid betting window (T in [10s, 25s]).
    """
    from core.models import RoundResolution

    # 1. Streak completes on round 20260924100052270
    snapshot_settlement = ObserverSnapshot(
        round_id="20260924100052270",
        countdown_seconds=1,
        history=[
            RoundResolution(round_id="20260924100052270", result_number=7, outcome=GameOutcome.BIG),
            RoundResolution(round_id="20260924100052269", result_number=9, outcome=GameOutcome.BIG),
            RoundResolution(round_id="20260924100052268", result_number=5, outcome=GameOutcome.BIG),
        ]
    )

    await runner._process_history(snapshot_settlement)

    # State machine must have generated pending bet for upcoming round 2271
    assert runner._pending_order is not None
    assert runner._pending_order.target == GameOutcome.SMALL
    assert runner._pending_order.round_id == "20260924100052271"

    # 2. Main loop attempts to execute at T=1s while DOM still displays round 2270
    await runner._try_execute_bet(page=None, snapshot=snapshot_settlement)

    # MUST NOT BE DISCARDED BY TIMING LOCKOUT!
    assert runner._pending_order is not None
    assert runner._last_bet_round_id is None

    # 3. DOM transitions to target round 2271 at T=29s (before window opens)
    snapshot_round_start = ObserverSnapshot(
        round_id="20260924100052271",
        countdown_seconds=29,
        history=snapshot_settlement.history,
    )
    await runner._try_execute_bet(page=None, snapshot=snapshot_round_start)

    # Still pending, waiting for T <= 25s
    assert runner._pending_order is not None
    assert runner._last_bet_round_id is None

    # 4. Countdown reaches T=25s (valid window)
    snapshot_in_window = ObserverSnapshot(
        round_id="20260924100052271",
        countdown_seconds=25,
        history=snapshot_settlement.history,
    )
    await runner._try_execute_bet(page=None, snapshot=snapshot_in_window)

    # Order executed! Pending order cleared and last_bet_round_id recorded
    assert runner._pending_order is None
    assert runner._last_bet_round_id == "20260924100052271"


@pytest.mark.asyncio
async def test_runner_timing_lockout_only_applies_to_target_round(runner):
    """
    Verify timing lockout (< 10s) discards the order ONLY when active round
    matches the target round.
    """
    order = BetOrder(round_id="20260924100052271", target=GameOutcome.SMALL, amount=1, ladder_index=0)
    runner._pending_order = order

    # Scenario A: Active is still previous round 2270 at T=5s -> MUST NOT discard
    prev_snapshot = ObserverSnapshot(round_id="20260924100052270", countdown_seconds=5)
    await runner._try_execute_bet(page=None, snapshot=prev_snapshot)
    assert runner._pending_order == order

    # Scenario B: Active IS target round 2271 at T=5s (< 10s) -> MUST discard
    target_snapshot = ObserverSnapshot(round_id="20260924100052271", countdown_seconds=5)
    await runner._try_execute_bet(page=None, snapshot=target_snapshot)
    assert runner._pending_order is None


@pytest.mark.asyncio
async def test_runner_stale_order_discarded_if_target_passed(runner):
    """
    If active round has progressed past the target round (e.g. 2272 > 2271),
    the pending order targeting 2271 is discarded as stale.
    """
    order = BetOrder(round_id="20260924100052271", target=GameOutcome.SMALL, amount=1, ladder_index=0)
    runner._pending_order = order

    snapshot = ObserverSnapshot(round_id="20260924100052272", countdown_seconds=20)
    await runner._try_execute_bet(page=None, snapshot=snapshot)

    assert runner._pending_order is None
    assert runner._last_bet_round_id is None



