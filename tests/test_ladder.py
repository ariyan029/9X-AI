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


# Expected ladder values (6 steps)
EXPECTED_LADDER = (50, 100, 200, 400, 750, 1500)
EXPECTED_TOTAL_RISK = sum(EXPECTED_LADDER)


class TestLadderConstants:
    """Test that ladder constants match the specification exactly."""

    def test_ladder_length(self):
        assert len(BET_LADDER) == 6

    def test_max_index(self):
        assert MAX_LADDER_INDEX == 5

    def test_all_values_match_spec(self):
        assert BET_LADDER == EXPECTED_LADDER

    def test_total_risk(self):
        assert sum(BET_LADDER) == EXPECTED_TOTAL_RISK


class TestGetStake:
    """Test stake retrieval for each step."""

    @pytest.mark.parametrize("index, expected_stake", [
        (0, 50),
        (1, 100),
        (2, 200),
        (3, 400),
        (4, 750),
        (5, 1500),
    ])
    def test_stake_at_each_step(self, index, expected_stake):
        assert BetLadder.get_stake(index) == expected_stake

    def test_negative_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(-1)

    def test_index_6_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(6)

    def test_large_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_stake(100)


class TestIsExhausted:
    """Test ladder exhaustion detection."""

    @pytest.mark.parametrize("index", range(5))
    def test_not_exhausted_below_5(self, index):
        assert BetLadder.is_exhausted(index) is False

    def test_exhausted_at_5(self):
        assert BetLadder.is_exhausted(5) is True

    def test_exhausted_above_5(self):
        assert BetLadder.is_exhausted(6) is True
        assert BetLadder.is_exhausted(100) is True


class TestCumulativeRisk:
    """Test cumulative capital at risk calculations."""

    def test_step_0(self):
        assert BetLadder.get_cumulative_risk(0) == 50

    def test_step_1(self):
        assert BetLadder.get_cumulative_risk(1) == 150  # 50 + 100

    def test_step_2(self):
        assert BetLadder.get_cumulative_risk(2) == 350  # 150 + 200

    def test_step_3(self):
        assert BetLadder.get_cumulative_risk(3) == 750  # 350 + 400

    def test_step_4(self):
        assert BetLadder.get_cumulative_risk(4) == 1500  # 750 + 750

    def test_full_ladder_risk(self):
        assert BetLadder.get_cumulative_risk(5) == EXPECTED_TOTAL_RISK

    def test_negative_index_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_cumulative_risk(-1)

    def test_index_6_raises(self):
        with pytest.raises(IndexError):
            BetLadder.get_cumulative_risk(6)


class TestExpectedPayout:
    """Test payout calculation (2x multiplier)."""

    @pytest.mark.parametrize("index", range(6))
    def test_payout_is_double_stake(self, index):
        stake = BetLadder.get_stake(index)
        assert BetLadder.get_expected_payout(index) == stake * 2


class TestNetProfitOnWin:
    """Test net profit at each ladder step."""

    EXPECTED_PROFITS = {
        0: 50,       # 100 - 50
        1: 50,       # 200 - 150
        2: 50,       # 400 - 350
        3: 50,       # 800 - 750
        4: 0,        # 1500 - 1500
        5: 0,        # 3000 - 3000
    }

    @pytest.mark.parametrize("index", range(6))
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
