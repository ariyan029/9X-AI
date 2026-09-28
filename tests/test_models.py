"""
tests/test_models.py — Unit tests for core data models.

Covers:
- GameOutcome.from_number() mapping (0-4 → SMALL, 5-9 → BIG)
- GameOutcome.opposite property
- RoundResolution validation
- BetOrder validation
- StreakTracker behavior
"""

import pytest
from core.models import (
    GameOutcome,
    EngineState,
    RoundResolution,
    BetOrder,
    CycleContext,
    StreakTracker,
)


class TestGameOutcomeFromNumber:
    """Test number-to-outcome mapping."""

    @pytest.mark.parametrize("number", [0, 1, 2, 3, 4])
    def test_small_range(self, number):
        assert GameOutcome.from_number(number) == GameOutcome.SMALL

    @pytest.mark.parametrize("number", [5, 6, 7, 8, 9])
    def test_big_range(self, number):
        assert GameOutcome.from_number(number) == GameOutcome.BIG

    @pytest.mark.parametrize("number", [-1, 10, 100, -99])
    def test_invalid_numbers_raise(self, number):
        with pytest.raises(ValueError, match="Invalid outcome number"):
            GameOutcome.from_number(number)

    def test_non_integer_raises_type_error(self):
        with pytest.raises(TypeError, match="Expected int"):
            GameOutcome.from_number(3.5)  # type: ignore

    def test_string_raises_type_error(self):
        with pytest.raises(TypeError, match="Expected int"):
            GameOutcome.from_number("5")  # type: ignore


class TestGameOutcomeOpposite:
    """Test the opposite property."""

    def test_big_opposite_is_small(self):
        assert GameOutcome.BIG.opposite == GameOutcome.SMALL

    def test_small_opposite_is_big(self):
        assert GameOutcome.SMALL.opposite == GameOutcome.BIG

    def test_double_opposite_is_identity(self):
        assert GameOutcome.BIG.opposite.opposite == GameOutcome.BIG
        assert GameOutcome.SMALL.opposite.opposite == GameOutcome.SMALL


class TestEngineState:
    """Test EngineState enum values."""

    def test_all_states_exist(self):
        assert EngineState.IDLE_OBSERVING == "IDLE_OBSERVING"
        assert EngineState.ACTIVE_BETTING == "ACTIVE_BETTING"
        assert EngineState.COOLDOWN == "COOLDOWN"
        assert EngineState.HALT == "HALT"

    def test_state_count(self):
        assert len(EngineState) == 5


class TestRoundResolution:
    """Test RoundResolution dataclass validation."""

    def test_valid_small_resolution(self):
        r = RoundResolution(round_id="001", result_number=3, outcome=GameOutcome.SMALL)
        assert r.round_id == "001"
        assert r.result_number == 3
        assert r.outcome == GameOutcome.SMALL

    def test_valid_big_resolution(self):
        r = RoundResolution(round_id="002", result_number=8, outcome=GameOutcome.BIG)
        assert r.result_number == 8
        assert r.outcome == GameOutcome.BIG

    def test_mismatched_outcome_raises(self):
        with pytest.raises(ValueError, match="does not match"):
            RoundResolution(round_id="003", result_number=2, outcome=GameOutcome.BIG)

    def test_number_out_of_range_raises(self):
        with pytest.raises(ValueError):
            RoundResolution(round_id="004", result_number=10, outcome=GameOutcome.BIG)

    def test_frozen(self):
        r = RoundResolution(round_id="005", result_number=5, outcome=GameOutcome.BIG)
        with pytest.raises(AttributeError):
            r.round_id = "modified"  # type: ignore


class TestBetOrder:
    """Test BetOrder dataclass validation."""

    def test_valid_order(self):
        order = BetOrder(round_id="001", target=GameOutcome.BIG, amount=15, ladder_index=3)
        assert order.amount == 15
        assert order.ladder_index == 3

    def test_zero_amount_raises(self):
        with pytest.raises(ValueError, match="positive"):
            BetOrder(round_id="001", target=GameOutcome.BIG, amount=0, ladder_index=0)

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError, match="positive"):
            BetOrder(round_id="001", target=GameOutcome.SMALL, amount=-10, ladder_index=0)

    def test_invalid_ladder_index_raises(self):
        with pytest.raises(ValueError, match="ladder_index"):
            BetOrder(round_id="001", target=GameOutcome.BIG, amount=1, ladder_index=10)

    def test_negative_ladder_index_raises(self):
        with pytest.raises(ValueError, match="ladder_index"):
            BetOrder(round_id="001", target=GameOutcome.BIG, amount=1, ladder_index=-1)


class TestStreakTracker:
    """Test StreakTracker counting logic."""

    def test_initial_state(self):
        tracker = StreakTracker()
        assert tracker.current_type is None
        assert tracker.count == 0

    def test_single_outcome(self):
        tracker = StreakTracker()
        count = tracker.update(GameOutcome.BIG)
        assert count == 1
        assert tracker.current_type == GameOutcome.BIG

    def test_consecutive_same_increments(self):
        tracker = StreakTracker()
        tracker.update(GameOutcome.BIG)
        tracker.update(GameOutcome.BIG)
        count = tracker.update(GameOutcome.BIG)
        assert count == 3

    def test_different_outcome_resets_to_one(self):
        tracker = StreakTracker()
        tracker.update(GameOutcome.BIG)
        tracker.update(GameOutcome.BIG)
        count = tracker.update(GameOutcome.SMALL)
        assert count == 1
        assert tracker.current_type == GameOutcome.SMALL

    def test_alternating_never_exceeds_one(self):
        tracker = StreakTracker()
        for i in range(10):
            outcome = GameOutcome.BIG if i % 2 == 0 else GameOutcome.SMALL
            count = tracker.update(outcome)
            assert count == 1

    def test_reset(self):
        tracker = StreakTracker()
        tracker.update(GameOutcome.BIG)
        tracker.update(GameOutcome.BIG)
        tracker.reset()
        assert tracker.current_type is None
        assert tracker.count == 0


class TestCycleContext:
    """Test CycleContext dataclass and properties."""

    def test_cycle_context_defaults(self):
        ctx = CycleContext(target=GameOutcome.BIG)
        assert ctx.target == GameOutcome.BIG
        assert ctx.ladder_index == 0
        assert ctx.streak_origin == GameOutcome.BIG
        assert ctx.is_exhausted is False

    def test_not_exhausted_at_8(self):
        ctx = CycleContext(target=GameOutcome.SMALL, ladder_index=8)
        assert ctx.is_exhausted is False

    def test_is_exhausted_at_9(self):
        ctx = CycleContext(target=GameOutcome.SMALL, ladder_index=9)
        assert ctx.is_exhausted is True

    def test_is_exhausted_above_9(self):
        ctx = CycleContext(target=GameOutcome.SMALL, ladder_index=10)
        assert ctx.is_exhausted is True
