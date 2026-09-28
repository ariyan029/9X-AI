"""
tests/test_state_machine.py — Unit tests for the deterministic state machine with the alternating algorithm.

Covers:
- Bet on the first round instantly.
- Alternating outcomes result in continuous betting.
- 2 identical outcomes (loss) transitions to IDLE_OBSERVING (waiting).
- Waiting continues during streaks.
- Betting resumes instantly when a streak breaks.
- Round ID idempotency (duplicate rounds rejected).
- HALT state blocks all processing.
"""

import pytest
from core.models import GameOutcome, EngineState, RoundResolution
from core.state_machine import DeterministicStateMachine
from core.ladder import BET_LADDER
from tests.conftest import make_resolution


class TestAlternatingAlgorithm:
    """Test the alternating betting logic (bet opposite of current, stop on loss/streak)."""

    def test_first_round_bets_instantly(self, state_machine):
        """On the very first round, the bot should bet on the opposite outcome instantly."""
        result = state_machine.on_round_resolved(make_resolution("001", 7))  # 7 = BIG
        
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert result.bet_order is not None
        assert result.bet_order.target == GameOutcome.SMALL
        assert result.bet_order.ladder_index == 0
        assert result.bet_order.amount == BET_LADDER[0]

    def test_alternating_outcomes_keep_betting(self, state_machine):
        """B -> S -> B -> S should result in continuous wins and continuous betting."""
        # Round 1: BIG
        result = state_machine.on_round_resolved(make_resolution("001", 7))
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert result.bet_order.target == GameOutcome.SMALL

        # Round 2: SMALL (Win) -> Must wait
        result = state_machine.on_round_resolved(make_resolution("002", 2))
        assert result.new_state == EngineState.WAITING_AFTER_BET
        assert result.bet_order is None

        # Round 3: BIG -> Streak broken relative to Round 2 (B != S) -> bet
        result = state_machine.on_round_resolved(make_resolution("003", 8))
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert result.bet_order.target == GameOutcome.SMALL

    def test_loss_triggers_wait_state(self, state_machine):
        """S -> S is a loss on the second round. Bot should wait."""
        # Round 1: SMALL
        result = state_machine.on_round_resolved(make_resolution("001", 2))
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert result.bet_order.target == GameOutcome.BIG

        # Round 2: SMALL (Loss) -> Wait one round
        result = state_machine.on_round_resolved(make_resolution("002", 3))
        assert result.new_state == EngineState.WAITING_AFTER_BET
        assert result.bet_order is None

    def test_wait_continues_during_streak(self, state_machine):
        """S -> S -> S -> S should stay in IDLE_OBSERVING after the first loss."""
        state_machine.on_round_resolved(make_resolution("001", 2))
        state_machine.on_round_resolved(make_resolution("002", 3))
        
        # Round 3: SMALL
        result = state_machine.on_round_resolved(make_resolution("003", 1))
        assert result.new_state == EngineState.IDLE_OBSERVING
        assert result.bet_order is None

        # Round 4: SMALL
        result = state_machine.on_round_resolved(make_resolution("004", 4))
        assert result.new_state == EngineState.IDLE_OBSERVING
        assert result.bet_order is None

    def test_streak_break_resumes_betting(self, state_machine):
        """S -> S -> B should resume betting (target SMALL) after B."""
        state_machine.on_round_resolved(make_resolution("001", 2))  # Bet B -> ACTIVE_BETTING
        state_machine.on_round_resolved(make_resolution("002", 3))  # Loss -> WAITING_AFTER_BET
        state_machine.on_round_resolved(make_resolution("003", 4))  # S == S -> IDLE_OBSERVING
        
        # Streak breaks with BIG
        result = state_machine.on_round_resolved(make_resolution("004", 8)) # B != S -> ACTIVE_BETTING
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert result.bet_order is not None
        assert result.bet_order.target == GameOutcome.SMALL


class TestIdempotency:
    """Test that duplicate or stale round IDs are rejected."""

    def test_duplicate_round_id_ignored(self, state_machine):
        r = make_resolution("round_001", 7)
        state_machine.on_round_resolved(r)
        
        # Same round ID again
        result = state_machine.on_round_resolved(r)
        assert "Duplicate" in result.message or "ignored" in result.message.lower()

    def test_stale_round_id_ignored(self, state_machine):
        state_machine.on_round_resolved(make_resolution("round_002", 7))
        
        # Older round ID
        result = state_machine.on_round_resolved(make_resolution("round_001", 2))
        assert "Duplicate" in result.message or "ignored" in result.message.lower()

    def test_numeric_round_id_rollover_not_stale(self, state_machine):
        # String "1000" < "999" lexicographically, but numerically 1000 > 999
        state_machine.on_round_resolved(make_resolution("999", 7))
        result = state_machine.on_round_resolved(make_resolution("1000", 2))
        assert "ignored" not in result.message.lower()
        assert state_machine.last_processed_round_id == "1000"


class TestHaltState:
    """Test HALT state blocks all processing."""

    def test_halt_rejects_processing(self, state_machine):
        state_machine.trigger_halt("Test halt")
        assert state_machine.state == EngineState.HALT

        result = state_machine.on_round_resolved(make_resolution("round_001", 7))
        assert result.new_state == EngineState.HALT
        assert result.bet_order is None
        assert "HALT" in result.message

    def test_reset_clears_halt(self, state_machine):
        state_machine.trigger_halt("Test halt")
        state_machine.reset()
        assert state_machine.state == EngineState.IDLE_OBSERVING
