"""
core/models.py — Pure typed data models for the 9X-AI engine.

All models are immutable (frozen dataclasses) or enums.
Zero I/O dependencies — suitable for 100% isolated unit testing.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List


class GameOutcome(str, Enum):
    """Represents the two possible game outcomes: Big (5-9) or Small (0-4)."""
    BIG = "Big"
    SMALL = "Small"

    @classmethod
    def from_number(cls, number: int) -> "GameOutcome":
        """
        Maps a result number (0-9) to its corresponding outcome.
        
        Args:
            number: The game result number (0-9).
            
        Returns:
            GameOutcome.SMALL for 0-4, GameOutcome.BIG for 5-9.
            
        Raises:
            ValueError: If number is not in range [0, 9].
        """
        if not isinstance(number, int):
            raise TypeError(f"Expected int, got {type(number).__name__}")
        if 0 <= number <= 4:
            return cls.SMALL
        elif 5 <= number <= 9:
            return cls.BIG
        raise ValueError(f"Invalid outcome number: {number}. Must be 0-9.")

    @property
    def opposite(self) -> "GameOutcome":
        """Returns the opposite outcome (BIG ↔ SMALL)."""
        return GameOutcome.SMALL if self == GameOutcome.BIG else GameOutcome.BIG


class EngineState(str, Enum):
    """
    Represents the four states of the deterministic finite state machine.
    
    IDLE_OBSERVING  — Passively monitoring rounds, computing streaks.
    ACTIVE_BETTING  — Actively placing bets along the ladder progression.
    COOLDOWN        — Safety buffer after ladder exhaustion (observe 1 round).
    HALT            — Emergency stop. Requires manual operator intervention.
    """
    IDLE_OBSERVING = "IDLE_OBSERVING"
    ACTIVE_BETTING = "ACTIVE_BETTING"
    COOLDOWN = "COOLDOWN"
    HALT = "HALT"


@dataclass(frozen=True)
class RoundResolution:
    """
    Immutable record of a completed round's result.
    
    Attributes:
        round_id: Unique identifier for the round (e.g., "20260923001").
        result_number: The drawn number (0-9).
        outcome: Derived GameOutcome (BIG or SMALL).
    """
    round_id: str
    result_number: int
    outcome: GameOutcome

    def __post_init__(self):
        if not (0 <= self.result_number <= 9):
            raise ValueError(
                f"result_number must be 0-9, got {self.result_number}"
            )
        expected = GameOutcome.from_number(self.result_number)
        if self.outcome != expected:
            raise ValueError(
                f"outcome {self.outcome} does not match result_number "
                f"{self.result_number} (expected {expected})"
            )


@dataclass(frozen=True)
class BetOrder:
    """
    Immutable bet execution directive produced by the state machine.
    
    Attributes:
        round_id: The round this bet targets.
        target: The outcome to bet on (BIG or SMALL).
        amount: The stake amount in units.
        ladder_index: Current position on the 15-step ladder (0-14).
    """
    round_id: str
    target: GameOutcome
    amount: int
    ladder_index: int

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError(f"Bet amount must be positive, got {self.amount}")
        if not (0 <= self.ladder_index <= 14):
            raise ValueError(
                f"ladder_index must be 0-14, got {self.ladder_index}"
            )


@dataclass
class CycleContext:
    """
    Mutable context for the current active betting cycle.
    
    Tracks the target, ladder position, and origin streak type
    for the duration of an ACTIVE_BETTING cycle.
    """
    target: GameOutcome
    ladder_index: int = 0
    streak_origin: GameOutcome = GameOutcome.BIG  # What triggered the cycle
    cycle_start_round_id: str = ""

    @property
    def is_exhausted(self) -> bool:
        """Returns True if ladder has reached the final step (index 14)."""
        return self.ladder_index >= 14


@dataclass
class StreakTracker:
    """
    Tracks consecutive identical outcomes to detect streak triggers.
    
    The streak is broken whenever a different outcome appears.
    """
    current_type: Optional[GameOutcome] = None
    count: int = 0

    def update(self, outcome: GameOutcome) -> int:
        """
        Update streak tracker with a new outcome.
        
        Args:
            outcome: The latest round outcome.
            
        Returns:
            The current streak length after the update.
        """
        if outcome == self.current_type:
            self.count += 1
        else:
            self.current_type = outcome
            self.count = 1
        return self.count

    def reset(self):
        """Reset the streak tracker."""
        self.current_type = None
        self.count = 0
