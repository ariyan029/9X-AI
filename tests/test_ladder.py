"""
tests/test_ladder.py — Unit tests for the 16-step bet progression ladder.

Covers:
- All 16 stake values match specification exactly
- Exhaustion detection at step 15
- Cumulative risk calculation (total: 138,416 units)
- Expected payout (2x multiplier)
- Net profit on win at each step
- Boundary error handling
"""

import pytest
from core.ladder import BetLadder, BET_LADDER, MAX_LADDER_INDEX


# Expected ladder values from PROJECT_SPEC.md §2.3
EXPECTED_LADDER = (1, 3, 7, 15, 30, 35, 75, 150, 350, 750, 1500, 3500, 7000, 15000, 35000, 75000)
EXPECTED_TOTAL_RISK = 138_416


class TestLadderConstants:
    """Test that ladder constants match the specification exactly."""

    def test_ladder_length(self):
        assert len(BET_LADDER) == 16

    def test_max_index(self):
        assert MAX_LADDER_INDEX == 15

    def test_all_values_match_spec(self):
        assert BET_LADDER == EXPECTED_LADDER

    def test_total_risk(self):
        assert sum(BET_LADDER) == EXPECTED_TOTAL_RISK


class TestGetStake:
    """Test stake retrieval for each step."""

    @pytest.mark.parametrize("index, expected_stake", [
        (0, 1),
        (1, 3),
        (2, 7),
        (3, 15),
        (4, 30),
        (5, 35),
        (6, 75),
        (7, 150),
        (8, 350),
        (9, 750),
        (10, 1500),
        (11, 3500),
        (12, 7000),
        (13, 15000),
        (14, 35000),
        (15, 75000),
    ])
    def test_stake_at_each_step(self, index, expected_stake):
        assert BetLadder.get_stake(index) == expected_stake

    def test_negative_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(-1)

    def test_index_16_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(16)

    def test_large_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(100)


class TestIsExhausted:
    """Test ladder exhaustion detection."""

    @pytest.mark.parametrize("index", range(15))
    def test_not_exhausted_below_15(self, index):
        assert BetLadder.is_exhausted(index) is False

    def test_exhausted_at_15(self):
        assert BetLadder.is_exhausted(15) is True

    def test_exhausted_above_15(self):
        assert BetLadder.is_exhausted(16) is True
        assert BetLadder.is_exhausted(100) is True


class TestCumulativeRisk:
    """Test cumulative capital at risk calculations."""

    def test_step_0(self):
        assert BetLadder.get_cumulative_risk(0) == 1

    def test_step_1(self):
        assert BetLadder.get_cumulative_risk(1) == 4  # 1 + 3

    def test_step_2(self):
        assert BetLadder.get_cumulative_risk(2) == 11  # 1 + 3 + 7

    def test_step_3(self):
        assert BetLadder.get_cumulative_risk(3) == 26

    def test_full_ladder_risk(self):
        assert BetLadder.get_cumulative_risk(15) == EXPECTED_TOTAL_RISK

    def test_negative_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_cumulative_risk(-1)

    def test_index_16_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_cumulative_risk(16)


class TestExpectedPayout:
    """Test payout calculation (2x multiplier)."""

    @pytest.mark.parametrize("index", range(16))
    def test_payout_is_double_stake(self, index):
        stake = BetLadder.get_stake(index)
        assert BetLadder.get_expected_payout(index) == stake * 2


class TestNetProfitOnWin:
    """Test net profit at each ladder step (from PROJECT_SPEC table)."""

    # Expected net profits from PROJECT_SPEC.md §2.3 table
    EXPECTED_PROFITS = {
        0: 1,        # 2 - 1
        1: 2,        # 6 - 4
        2: 3,        # 14 - 11
        3: 4,        # 30 - 26
        4: 4,        # 60 - 56
        5: -21,      # 70 - 91 (recovery mitigation)
        6: -16,      # 150 - 166 (recovery mitigation)
        7: -16,      # 300 - 316 (recovery mitigation)
        8: 34,       # 700 - 666
        9: 84,       # 1500 - 1416
        10: 84,      # 3000 - 2916
        11: 584,     # 7000 - 6416
        12: 584,     # 14000 - 13416
        13: 1584,    # 30000 - 28416
        14: 6584,    # 70000 - 63416
        15: 11584,   # 150000 - 138416
    }

    @pytest.mark.parametrize("index", range(16))
    def test_net_profit_matches_spec(self, index):
        expected = self.EXPECTED_PROFITS[index]
        actual = BetLadder.get_net_profit_on_win(index)
        assert actual == expected, (
            f"Step {index}: expected profit {expected}, got {actual}"
        )


class TestTotalLadderRisk:
    """Test total risk calculation."""

    def test_total_risk(self):
        assert BetLadder.get_total_ladder_risk() == EXPECTED_TOTAL_RISK
