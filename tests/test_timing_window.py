"""
tests/test_timing_window.py — Unit tests for the timing gatekeeper.

Covers:
- T in [10, 25] → accepted (within betting window)
- T < 10 → rejected (lockout danger zone)
- T > 25 → rejected (too early, round not settled)
- Edge cases at boundaries (9, 10, 25, 26)
"""

import pytest


class TimingGatekeeper:
    """
    Timing window validator.
    
    Ensures bet execution only occurs when the countdown is
    between MIN_SECONDS and MAX_SECONDS (inclusive).
    """
    MIN_SECONDS: int = 10
    MAX_SECONDS: int = 25

    @classmethod
    def is_within_window(cls, remaining_seconds: int) -> bool:
        """
        Check if the countdown is within the safe betting window.
        
        Args:
            remaining_seconds: Current countdown value.
            
        Returns:
            True if MIN_SECONDS <= remaining_seconds <= MAX_SECONDS.
        """
        return cls.MIN_SECONDS <= remaining_seconds <= cls.MAX_SECONDS


class TestTimingGatekeeper:
    """Test the timing window boundaries."""

    # === Accepted window [10, 25] ===
    @pytest.mark.parametrize("seconds", [10, 11, 15, 20, 24, 25])
    def test_within_window_accepted(self, seconds):
        assert TimingGatekeeper.is_within_window(seconds) is True

    # === Rejected: too late (lockout zone) ===
    @pytest.mark.parametrize("seconds", [0, 1, 5, 9])
    def test_below_window_rejected(self, seconds):
        assert TimingGatekeeper.is_within_window(seconds) is False

    # === Rejected: too early ===
    @pytest.mark.parametrize("seconds", [26, 27, 30, 60])
    def test_above_window_rejected(self, seconds):
        assert TimingGatekeeper.is_within_window(seconds) is False

    # === Critical edge cases ===
    def test_edge_case_9_rejected(self):
        """T=9 is below the window — lockout zone."""
        assert TimingGatekeeper.is_within_window(9) is False

    def test_edge_case_10_accepted(self):
        """T=10 is the lower boundary — should be accepted."""
        assert TimingGatekeeper.is_within_window(10) is True

    def test_edge_case_25_accepted(self):
        """T=25 is the upper boundary — should be accepted."""
        assert TimingGatekeeper.is_within_window(25) is True

    def test_edge_case_26_rejected(self):
        """T=26 is above the window — should be rejected."""
        assert TimingGatekeeper.is_within_window(26) is False

    # === Negative values ===
    def test_negative_seconds_rejected(self):
        assert TimingGatekeeper.is_within_window(-1) is False
        assert TimingGatekeeper.is_within_window(-10) is False
