"""
tests/test_state_machine.py — Unit tests for the deterministic state machine.

Covers:
- IDLE_OBSERVING waiting for 2-streak
- Betting starts after 2 consecutive outcomes
- Ladder progression on loss
- Cooldown on win
- HALT on ladder exhaustion
- Idempotency
"""

import pytest
from core.models import GameOutcome, EngineState
from core.state_machine import DeterministicStateMachine
from core.ladder import BET_LADDER
from tests.conftest import make_resolution


class TestStreakAlgorithm:
    """Test the streak-based betting logic and ladder progression."""

    def test_waits_for_streak(self, state_machine):
        """Bot should remain IDLE until streak reaches 2."""
        r1 = state_machine.on_round_resolved(make_resolution("001", 7)) # Big
        assert r1.new_state == EngineState.IDLE_OBSERVING
        
        r2 = state_machine.on_round_resolved(make_resolution("002", 8)) # Big
        assert r2.new_state == EngineState.ACTIVE_BETTING
        assert r2.bet_order is not None
        assert r2.bet_order.target == GameOutcome.SMALL
        assert r2.bet_order.ladder_index == 0
        assert r2.bet_order.amount == BET_LADDER[0]

    def test_win_returns_to_idle(self, state_machine):
        """Win should immediately return to IDLE_OBSERVING and start new streak."""
        state_machine.on_round_resolved(make_resolution("001", 7))
        state_machine.on_round_resolved(make_resolution("002", 8)) # Targets SMALL
        
        # Round 3: Win (Small)
        r3 = state_machine.on_round_resolved(make_resolution("003", 2))
        assert r3.new_state == EngineState.IDLE_OBSERVING
        assert r3.bet_order is None

        # Streak should be 1 Small now. Add 1 more Small to trigger next bet!
        r4 = state_machine.on_round_resolved(make_resolution("004", 3)) # Small (streak = 2)
        assert r4.new_state == EngineState.ACTIVE_BETTING
        assert r4.bet_order.target == GameOutcome.BIG
        assert r4.bet_order.ladder_index == 0

    def test_loss_escalates_ladder(self, state_machine):
        """Loss should increment ladder index."""
        state_machine.on_round_resolved(make_resolution("001", 7))
        state_machine.on_round_resolved(make_resolution("002", 8)) # Targets SMALL (index 0)

        # Round 3: Loss (Big)
        r3 = state_machine.on_round_resolved(make_resolution("003", 7))
        assert r3.new_state == EngineState.ACTIVE_BETTING
        assert r3.bet_order is not None
        assert r3.bet_order.target == GameOutcome.SMALL
        assert r3.bet_order.ladder_index == 1
        assert r3.bet_order.amount == BET_LADDER[1]

    def test_ladder_exhaustion_returns_to_idle(self, state_machine):
        """Losing all steps returns to IDLE_OBSERVING."""
        # Force a streak to start betting SMALL
        state_machine.on_round_resolved(make_resolution("001", 7))
        state_machine.on_round_resolved(make_resolution("002", 8)) # Targets SMALL (step 0)

        # 6 losses (step 0 through 5)
        for step in range(6):
            round_str = str(3 + step).zfill(3)
            res = state_machine.on_round_resolved(make_resolution(round_str, 7)) # BIG (Loss)
            
            if step < 5:
                assert res.new_state == EngineState.ACTIVE_BETTING
                assert res.bet_order.ladder_index == step + 1
            else:
                assert res.new_state == EngineState.IDLE_OBSERVING
                assert state_machine.streak.count == 1  # Streak reset to 1 Big


class TestIdempotency:
    """Test that duplicate or stale round IDs are rejected."""

    def test_duplicate_round_id_ignored(self, state_machine):
        r = make_resolution("round_001", 7)
        state_machine.on_round_resolved(r)
        
        result = state_machine.on_round_resolved(r)
        assert "Duplicate" in result.message or "ignored" in result.message.lower()

    def test_stale_round_id_ignored(self, state_machine):
        state_machine.on_round_resolved(make_resolution("round_002", 7))
        result = state_machine.on_round_resolved(make_resolution("round_001", 2))
        assert "Duplicate" in result.message or "ignored" in result.message.lower()


class TestHaltState:
    """Test HALT state blocks all processing."""

    def test_halt_rejects_processing(self, state_machine):
        state_machine.trigger_halt("Test halt")
        assert state_machine.state == EngineState.HALT

        result = state_machine.on_round_resolved(make_resolution("round_001", 7))
        assert result.new_state == EngineState.HALT
        assert result.bet_order is None

    def test_reset_clears_halt(self, state_machine):
        state_machine.trigger_halt("Test halt")
        state_machine.reset()
        assert state_machine.state == EngineState.IDLE_OBSERVING
