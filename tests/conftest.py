"""
tests/conftest.py — Shared fixtures and mock generators for 9X-AI tests.
"""

import pytest
from core.models import GameOutcome, RoundResolution
from core.state_machine import DeterministicStateMachine


@pytest.fixture
def state_machine():
    """Fresh DeterministicStateMachine instance for each test."""
    return DeterministicStateMachine()


def make_resolution(round_id: str, number: int) -> RoundResolution:
    """
    Helper to create a RoundResolution from a round ID and number.
    
    Automatically derives the correct GameOutcome from the number.
    """
    outcome = GameOutcome.from_number(number)
    return RoundResolution(
        round_id=round_id,
        result_number=number,
        outcome=outcome,
    )


def make_streak(
    outcome: GameOutcome,
    count: int,
    start_round: int = 1,
) -> list[RoundResolution]:
    """
    Generate a sequence of RoundResolutions with the same outcome type.
    
    Args:
        outcome: The desired outcome (BIG or SMALL).
        count: Number of consecutive identical rounds to generate.
        start_round: Starting round number for ID generation.
        
    Returns:
        List of RoundResolution instances.
    """
    # Use a representative number for the outcome
    number = 7 if outcome == GameOutcome.BIG else 2
    return [
        make_resolution(
            round_id=f"2026092300{start_round + i:03d}",
            number=number,
        )
        for i in range(count)
    ]
