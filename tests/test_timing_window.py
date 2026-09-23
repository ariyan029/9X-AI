"""
tests/test_timing_window.py — Unit tests for the timing gatekeeper.

Covers:
- T in [10, 25] → accepted (within betting window)
- T < 10 → rejected (lockout danger zone)
- T > 25 → rejected (too early, round not settled)
- Edge cases at boundaries (9, 10, 25, 26)
"""

import pytest


from browser.executor import TimingGatekeeper


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

    # === Dynamic configuration ===
    def test_configure_custom_boundaries(self):
        """Verify that TimingGatekeeper.configure updates boundaries."""
        orig_min = TimingGatekeeper.MIN_SECONDS
        orig_max = TimingGatekeeper.MAX_SECONDS
        try:
            TimingGatekeeper.configure(5, 20)
            assert TimingGatekeeper.is_within_window(5) is True
            assert TimingGatekeeper.is_within_window(20) is True
            assert TimingGatekeeper.is_within_window(4) is False
            assert TimingGatekeeper.is_within_window(21) is False
        finally:
            TimingGatekeeper.configure(orig_min, orig_max)
