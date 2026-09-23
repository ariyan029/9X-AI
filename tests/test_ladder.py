"""
tests/test_ladder.py — Unit tests for the 15-step bet progression ladder.

Covers:
- All 15 stake values match specification exactly
- Exhaustion detection at step 14
- Cumulative risk calculation (total: 138,886 units)
- Expected payout (2x multiplier)
- Net profit on win at each step (all positive)
- Boundary error handling
"""

import pytest
from core.ladder import BetLadder, BET_LADDER, MAX_LADDER_INDEX


# Expected ladder values (15 steps)
EXPECTED_LADDER = (1, 3, 7, 15, 35, 75, 150, 350, 750, 1500, 3500, 7500, 15000, 35000, 75000)
EXPECTED_TOTAL_RISK = 138_886


class TestLadderConstants:
    """Test that ladder constants match the specification exactly."""

    def test_ladder_length(self):
        assert len(BET_LADDER) == 15

    def test_max_index(self):
        assert MAX_LADDER_INDEX == 14

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
        (4, 35),
        (5, 75),
        (6, 150),
        (7, 350),
        (8, 750),
        (9, 1500),
        (10, 3500),
        (11, 7500),
        (12, 15000),
        (13, 35000),
        (14, 75000),
    ])
    def test_stake_at_each_step(self, index, expected_stake):
        assert BetLadder.get_stake(index) == expected_stake

    def test_negative_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(-1)

    def test_index_15_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(15)

    def test_large_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(100)


class TestIsExhausted:
    """Test ladder exhaustion detection."""

    @pytest.mark.parametrize("index", range(14))
    def test_not_exhausted_below_14(self, index):
        assert BetLadder.is_exhausted(index) is False

    def test_exhausted_at_14(self):
        assert BetLadder.is_exhausted(14) is True

    def test_exhausted_above_14(self):
        assert BetLadder.is_exhausted(15) is True
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
        assert BetLadder.get_cumulative_risk(3) == 26  # 1 + 3 + 7 + 15

    def test_step_4(self):
        assert BetLadder.get_cumulative_risk(4) == 61  # 26 + 35

    def test_full_ladder_risk(self):
        assert BetLadder.get_cumulative_risk(14) == EXPECTED_TOTAL_RISK

    def test_negative_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_cumulative_risk(-1)

    def test_index_15_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_cumulative_risk(15)


class TestExpectedPayout:
    """Test payout calculation (2x multiplier)."""

    @pytest.mark.parametrize("index", range(15))
    def test_payout_is_double_stake(self, index):
        stake = BetLadder.get_stake(index)
        assert BetLadder.get_expected_payout(index) == stake * 2


class TestNetProfitOnWin:
    """Test net profit at each ladder step."""

    EXPECTED_PROFITS = {
        0: 1,        # 2 - 1 = 1
        1: 2,        # 6 - 4 = 2
        2: 3,        # 14 - 11 = 3
        3: 4,        # 30 - 26 = 4
        4: 9,        # 70 - 61 = 9
        5: 14,       # 150 - 136 = 14
        6: 14,       # 300 - 286 = 14
        7: 64,       # 700 - 636 = 64
        8: 114,      # 1500 - 1386 = 114
        9: 114,      # 3000 - 2886 = 114
        10: 614,     # 7000 - 6386 = 614
        11: 1114,    # 15000 - 13886 = 1114
        12: 1114,    # 30000 - 28886 = 1114
        13: 6114,    # 70000 - 63886 = 6114
        14: 11114,   # 150000 - 138886 = 11114
    }

    @pytest.mark.parametrize("index", range(15))
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
