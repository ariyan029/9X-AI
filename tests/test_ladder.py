"""
tests/test_ladder.py — Unit tests for the 10-step bet progression ladder.

Covers:
- All 8 stake values match specification exactly
- Exhaustion detection at step 7
- Cumulative risk calculation (total: 6,360 units)
- Expected payout (2x multiplier)
- Net profit on win at each step (all positive)
- Boundary error handling
"""

import pytest
from core.ladder import BetLadder, BET_LADDER, MAX_LADDER_INDEX


# Expected ladder values (8 steps)
EXPECTED_LADDER = (10, 30, 70, 150, 350, 750, 1500, 3500)
EXPECTED_TOTAL_RISK = 6360


class TestLadderConstants:
    """Test that ladder constants match the specification exactly."""

    def test_ladder_length(self):
        assert len(BET_LADDER) == 8

    def test_max_index(self):
        assert MAX_LADDER_INDEX == 7

    def test_all_values_match_spec(self):
        assert BET_LADDER == EXPECTED_LADDER

    def test_total_risk(self):
        assert sum(BET_LADDER) == EXPECTED_TOTAL_RISK


class TestGetStake:
    """Test stake retrieval for each step."""

    @pytest.mark.parametrize("index, expected_stake", [
        (0, 10),
        (1, 30),
        (2, 70),
        (3, 150),
        (4, 350),
        (5, 750),
        (6, 1500),
        (7, 3500),
    ])
    def test_stake_at_each_step(self, index, expected_stake):
        assert BetLadder.get_stake(index) == expected_stake

    def test_negative_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(-1)

    def test_index_8_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(8)

    def test_large_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(100)


class TestIsExhausted:
    """Test ladder exhaustion detection."""

    @pytest.mark.parametrize("index", range(7))
    def test_not_exhausted_below_7(self, index):
        assert BetLadder.is_exhausted(index) is False

    def test_exhausted_at_7(self):
        assert BetLadder.is_exhausted(7) is True

    def test_exhausted_above_7(self):
        assert BetLadder.is_exhausted(8) is True
        assert BetLadder.is_exhausted(100) is True


class TestCumulativeRisk:
    """Test cumulative capital at risk calculations."""

    def test_step_0(self):
        assert BetLadder.get_cumulative_risk(0) == 10

    def test_step_1(self):
        assert BetLadder.get_cumulative_risk(1) == 40  # 10 + 30

    def test_step_2(self):
        assert BetLadder.get_cumulative_risk(2) == 110  # 10 + 30 + 70

    def test_step_3(self):
        assert BetLadder.get_cumulative_risk(3) == 260  # 110 + 150

    def test_step_4(self):
        assert BetLadder.get_cumulative_risk(4) == 610  # 260 + 350

    def test_full_ladder_risk(self):
        assert BetLadder.get_cumulative_risk(7) == EXPECTED_TOTAL_RISK

    def test_negative_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_cumulative_risk(-1)

    def test_index_8_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_cumulative_risk(8)


class TestExpectedPayout:
    """Test payout calculation (2x multiplier)."""

    @pytest.mark.parametrize("index", range(8))
    def test_payout_is_double_stake(self, index):
        stake = BetLadder.get_stake(index)
        assert BetLadder.get_expected_payout(index) == stake * 2


class TestNetProfitOnWin:
    """Test net profit at each ladder step."""

    EXPECTED_PROFITS = {
        0: 10,       # 20 - 10 = 10
        1: 20,       # 60 - 40 = 20
        2: 30,       # 140 - 110 = 30
        3: 40,       # 300 - 260 = 40
        4: 90,       # 700 - 610 = 90
        5: 140,      # 1500 - 1360 = 140
        6: 140,      # 3000 - 2860 = 140
        7: 640,      # 7000 - 6360 = 640
    }

    @pytest.mark.parametrize("index", range(8))
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
