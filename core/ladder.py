"""
core/ladder.py — Immutable 10-step bet progression ladder.

The ladder defines the exact stake for each step in a risk progression
ensuring positive net profit at all steps. All values are fixed constants.
"""

from typing import Tuple

# The immutable 7-step progression ladder (indices 0-6)
BET_LADDER: Tuple[int, ...] = (
    10, 30, 70, 150, 350, 750, 1500
)

# Maximum valid ladder index
MAX_LADDER_INDEX: int = len(BET_LADDER) - 1


class BetLadder:
    """
    Manager for the 10-step fixed bet progression ladder.
    
    Provides stake lookups, exhaustion checks, cumulative risk
    calculations, and net profit projections. All methods are
    pure functions operating on the immutable BET_LADDER constant.
    """

    @staticmethod
    def get_stake(index: int) -> int:
        """
        Get the bet stake for a given ladder index.
        
        Args:
            index: Ladder step (0-9).
            
        Returns:
            The stake amount in units.
            
        Raises:
            IndexError: If index is out of range [0, 9].
        """
        if not (0 <= index <= MAX_LADDER_INDEX):
            raise IndexError(
                f"Ladder index must be 0-{MAX_LADDER_INDEX}, got {index}"
            )
        return BET_LADDER[index]

    @staticmethod
    def is_exhausted(index: int) -> bool:
        """
        Check whether the ladder is at its final step.
        
        Args:
            index: Current ladder index.
            
        Returns:
            True if index >= MAX_LADDER_INDEX (step 9).
        """
        return index >= MAX_LADDER_INDEX

    @staticmethod
    def get_cumulative_risk(up_to_index: int) -> int:
        """
        Calculate the total capital at risk from step 0 through up_to_index.
        
        Args:
            up_to_index: The highest ladder step to include (inclusive).
            
        Returns:
            Sum of all stakes from step 0 to up_to_index.
            
        Raises:
            IndexError: If up_to_index is out of range [0, 9].
        """
        if not (0 <= up_to_index <= MAX_LADDER_INDEX):
            raise IndexError(
                f"Ladder index must be 0-{MAX_LADDER_INDEX}, got {up_to_index}"
            )
        return sum(BET_LADDER[: up_to_index + 1])

    @staticmethod
    def get_expected_payout(index: int) -> int:
        """
        Calculate the expected payout on a win at the given step (2x multiplier).
        
        Args:
            index: Ladder step (0-9).
            
        Returns:
            Payout amount (stake * 2).
        """
        return BetLadder.get_stake(index) * 2

    @staticmethod
    def get_net_profit_on_win(index: int) -> int:
        """
        Calculate net profit if a win occurs at the given ladder step.
        
        Net profit = payout at step - cumulative capital invested through step.
        
        Args:
            index: Ladder step where the win occurs (0-9).
            
        Returns:
            Net profit on win at this step.
        """
        payout = BetLadder.get_expected_payout(index)
        cumulative_risk = BetLadder.get_cumulative_risk(index)
        return payout - cumulative_risk

    @staticmethod
    def get_total_ladder_risk() -> int:
        """
        Calculate the total capital at risk if all 10 steps are lost.
        
        Returns:
            Total sum of all ladder stakes (28,860 units).
        """
        return sum(BET_LADDER)
