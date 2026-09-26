"""
tests/test_state_machine.py — Unit tests for the deterministic state machine.

Covers:
- 3-streak trigger (BIG → bet SMALL, SMALL → bet BIG)
- Alternating outcomes never trigger betting
- Win at any step resets to IDLE_OBSERVING
- Loss increments ladder index
- 10 consecutive losses (step 9 lost) → COOLDOWN → IDLE_OBSERVING
- Cooldown observes 1 round then resumes
- Round ID idempotency (duplicate rounds rejected)
- HALT state blocks all processing
"""

import pytest
from core.models import GameOutcome, EngineState, RoundResolution
from core.state_machine import DeterministicStateMachine, STREAK_TRIGGER_THRESHOLD
from core.ladder import BET_LADDER
from tests.conftest import make_resolution, make_streak


class TestStreakDetection:
    """Test that 3 consecutive identical outcomes trigger ACTIVE_BETTING."""

    def test_three_bigs_trigger_small_bet(self, state_machine):
        """3 consecutive BIG outcomes should trigger betting on SMALL."""
        resolutions = make_streak(GameOutcome.BIG, 3)
        
        # First two should stay in IDLE
        for r in resolutions[:2]:
            result = state_machine.on_round_resolved(r)
            assert result.new_state == EngineState.IDLE_OBSERVING
            assert result.bet_order is None

        # Third BIG triggers ACTIVE_BETTING targeting SMALL
        result = state_machine.on_round_resolved(resolutions[2])
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert result.bet_order is not None
        assert result.bet_order.target == GameOutcome.SMALL
        assert result.bet_order.amount == BET_LADDER[0]  # 10
        assert result.bet_order.ladder_index == 0

    def test_three_smalls_trigger_big_bet(self, state_machine):
        """3 consecutive SMALL outcomes should trigger betting on BIG."""
        resolutions = make_streak(GameOutcome.SMALL, 3)

        for r in resolutions[:2]:
            result = state_machine.on_round_resolved(r)
            assert result.new_state == EngineState.IDLE_OBSERVING

        result = state_machine.on_round_resolved(resolutions[2])
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert result.bet_order is not None
        assert result.bet_order.target == GameOutcome.BIG
        assert result.bet_order.amount == BET_LADDER[0]  # 10

    def test_four_consecutive_still_triggers_at_three(self, state_machine):
        """Streak of 4 should trigger at the 3rd round."""
        resolutions = make_streak(GameOutcome.BIG, 4)
        
        result = state_machine.on_round_resolved(resolutions[0])
        assert result.new_state == EngineState.IDLE_OBSERVING
        
        result = state_machine.on_round_resolved(resolutions[1])
        assert result.new_state == EngineState.IDLE_OBSERVING
        
        result = state_machine.on_round_resolved(resolutions[2])
        assert result.new_state == EngineState.ACTIVE_BETTING


class TestAlternatingOutcomes:
    """Test that non-streak patterns don't trigger betting."""

    def test_alternating_never_triggers(self, state_machine):
        """BIG, SMALL, BIG, SMALL... should never trigger active betting."""
        for i in range(20):
            number = 7 if i % 2 == 0 else 2
            r = make_resolution(f"round_{i:04d}", number)
            result = state_machine.on_round_resolved(r)
            assert result.new_state == EngineState.IDLE_OBSERVING
            assert result.bet_order is None

    def test_two_same_then_different_resets(self, state_machine):
        """BIG, BIG, SMALL should reset streak to 1."""
        state_machine.on_round_resolved(make_resolution("001", 7))
        state_machine.on_round_resolved(make_resolution("002", 8))
        result = state_machine.on_round_resolved(make_resolution("003", 2))
        assert result.new_state == EngineState.IDLE_OBSERVING
        assert result.bet_order is None


class TestWinResolution:
    """Test that a win resets the ladder and returns to IDLE_OBSERVING."""

    def test_win_at_step_0(self, state_machine):
        """Win on first bet resets to IDLE."""
        # Trigger active betting with 3 BIGs
        for r in make_streak(GameOutcome.BIG, 3):
            state_machine.on_round_resolved(r)
        
        assert state_machine.state == EngineState.ACTIVE_BETTING
        assert state_machine.cycle.target == GameOutcome.SMALL

        # Win: SMALL outcome
        win = make_resolution("2026092300004", 2)  # SMALL = win
        result = state_machine.on_round_resolved(win)
        
        assert result.new_state == EngineState.IDLE_OBSERVING
        assert result.bet_order is None
        assert state_machine.cycle is None

    @pytest.mark.parametrize("win_step", range(10))
    def test_win_at_each_step(self, state_machine, win_step):
        """Win at any step K (0-9) should reset to IDLE_OBSERVING."""
        # Trigger with 3 BIGs → target SMALL
        for r in make_streak(GameOutcome.BIG, 3):
            state_machine.on_round_resolved(r)

        # Lose 'win_step' rounds (BIG outcomes = loss against SMALL target)
        for i in range(win_step):
            loss = make_resolution(f"loss_{i:04d}", 7)  # BIG = loss
            result = state_machine.on_round_resolved(loss)
            if state_machine.state == EngineState.COOLDOWN:
                # Step 9 was lost → ladder exhausted, can't win anymore
                return
            assert result.new_state == EngineState.ACTIVE_BETTING

        if state_machine.state == EngineState.ACTIVE_BETTING:
            # Win at current step
            assert state_machine.cycle.ladder_index == win_step
            win = make_resolution(f"win_{win_step:04d}", 2)  # SMALL = win
            result = state_machine.on_round_resolved(win)
            assert result.new_state == EngineState.IDLE_OBSERVING
            assert state_machine.cycle is None


class TestLossProgression:
    """Test that losses increment the ladder correctly."""

    def test_single_loss_increments_to_step_1(self, state_machine):
        """First loss should advance ladder from 0 to 1."""
        for r in make_streak(GameOutcome.BIG, 3):
            state_machine.on_round_resolved(r)
        
        # Loss: BIG outcome (target is SMALL)
        loss = make_resolution("2026092300004", 7)
        result = state_machine.on_round_resolved(loss)
        
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert result.bet_order is not None
        assert result.bet_order.ladder_index == 1
        assert result.bet_order.amount == BET_LADDER[1]  # 30
        assert result.bet_order.target == GameOutcome.SMALL  # Target unchanged

    def test_consecutive_losses_follow_ladder(self, state_machine):
        """Each loss should advance to the next ladder step with correct stake."""
        for r in make_streak(GameOutcome.BIG, 3):
            state_machine.on_round_resolved(r)

        # Lose 9 rounds (steps 0 through 8 advance to steps 1 through 9)
        for i in range(9):
            loss = make_resolution(f"loss_{i:04d}", 7)
            result = state_machine.on_round_resolved(loss)
            assert result.new_state == EngineState.ACTIVE_BETTING
            assert result.bet_order.ladder_index == i + 1
            assert result.bet_order.amount == BET_LADDER[i + 1]

    def test_target_remains_fixed_through_losses(self, state_machine):
        """Target should never change during a loss sequence."""
        for r in make_streak(GameOutcome.SMALL, 3):
            state_machine.on_round_resolved(r)
        
        # Target should be BIG
        assert state_machine.cycle.target == GameOutcome.BIG

        for i in range(5):
            loss = make_resolution(f"loss_{i:04d}", 2)  # SMALL = loss
            result = state_machine.on_round_resolved(loss)
            assert result.bet_order.target == GameOutcome.BIG


class TestLadderExhaustion:
    """Test the 10th loss (step 9) triggers Hard Cycle Abort → COOLDOWN."""

    def test_step_9_loss_triggers_cooldown(self, state_machine):
        """Losing at step 9 should transition to COOLDOWN."""
        # Trigger active betting
        for r in make_streak(GameOutcome.BIG, 3):
            state_machine.on_round_resolved(r)

        # Lose 10 rounds (steps 0-9)
        for i in range(10):
            loss = make_resolution(f"loss_{i:04d}", 7)
            result = state_machine.on_round_resolved(loss)

        # After 10th loss (step 9), should be in COOLDOWN
        assert result.new_state == EngineState.COOLDOWN
        assert result.bet_order is None
        assert state_machine.cycle is None


class TestCooldown:
    """Test COOLDOWN state behavior."""

    def test_cooldown_returns_to_idle_after_one_round(self, state_machine):
        """After 1 clean round in COOLDOWN, should return to IDLE_OBSERVING."""
        # Trigger and exhaust ladder
        for r in make_streak(GameOutcome.BIG, 3):
            state_machine.on_round_resolved(r)
        for i in range(10):
            state_machine.on_round_resolved(make_resolution(f"loss_{i:04d}", 7))
        
        assert state_machine.state == EngineState.COOLDOWN

        # Observe one clean round (ID must sort after loss round IDs)
        clean = make_resolution("zz_clean_001", 5)
        result = state_machine.on_round_resolved(clean)
        
        assert result.new_state == EngineState.IDLE_OBSERVING
        assert result.bet_order is None

    def test_streak_starts_fresh_after_cooldown(self, state_machine):
        """After cooldown, streak counter should be fresh."""
        # Trigger and exhaust
        for r in make_streak(GameOutcome.BIG, 3):
            state_machine.on_round_resolved(r)
        for i in range(10):
            state_machine.on_round_resolved(make_resolution(f"loss_{i:04d}", 7))
        
        # Cooldown round (ID must sort after loss rounds)
        state_machine.on_round_resolved(make_resolution("zz_cool_001", 7))
        assert state_machine.state == EngineState.IDLE_OBSERVING

        # Need 2 more BIGs to reach streak of 3 (1 was seeded in cooldown exit)
        state_machine.on_round_resolved(make_resolution("zz_post_001", 8))
        result = state_machine.on_round_resolved(make_resolution("zz_post_002", 6))
        assert result.new_state == EngineState.ACTIVE_BETTING


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


class TestFullCycleIntegration:
    """End-to-end cycle: idle → trigger → bet → win → idle."""

    def test_complete_cycle_trigger_bet_win(self, state_machine):
        """Full cycle: 3 BIGs → bet SMALL → SMALL appears → back to idle."""
        # Phase 1: Build streak (IDs: 2026092300001, 002, 003)
        for r in make_streak(GameOutcome.BIG, 3):
            state_machine.on_round_resolved(r)
        assert state_machine.state == EngineState.ACTIVE_BETTING

        # Phase 2: Win immediately (ID must sort after streak IDs)
        win = make_resolution("2026092300004", 2)  # SMALL
        result = state_machine.on_round_resolved(win)
        assert result.new_state == EngineState.IDLE_OBSERVING

        # Phase 3: Can trigger again with new streak (IDs sort after win)
        for r in make_streak(GameOutcome.SMALL, 3, start_round=100):
            result = state_machine.on_round_resolved(r)
        assert result.new_state == EngineState.ACTIVE_BETTING
        assert state_machine.cycle.target == GameOutcome.BIG

    def test_complete_cycle_with_losses_then_win(self, state_machine):
        """Trigger → lose 3 times → win at step 3."""
        for r in make_streak(GameOutcome.SMALL, 3):
            state_machine.on_round_resolved(r)
        
        # Target is BIG. Lose 3 times with SMALL outcomes.
        for i in range(3):
            loss = make_resolution(f"loss_{i:04d}", 2)  # SMALL = loss
            state_machine.on_round_resolved(loss)
        
        assert state_machine.cycle.ladder_index == 3
        
        # Win at step 3
        win = make_resolution("win_003", 7)  # BIG = win
        result = state_machine.on_round_resolved(win)
        assert result.new_state == EngineState.IDLE_OBSERVING
