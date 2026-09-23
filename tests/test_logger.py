"""
tests/test_logger.py — Unit tests for structured logging configuration.

Covers:
- setup_logger creating log directories and file handlers
- log_round_event logging without raising exceptions
"""

from pathlib import Path
from utils.logger import setup_logger, log_round_event


class TestLogger:
    """Test suite for logger utilities."""

    def test_setup_logger_creates_directory(self, tmp_path):
        log_dir = tmp_path / "test_logs"
        setup_logger(log_dir=log_dir)
        assert log_dir.exists()

    def test_log_round_event_runs_cleanly(self, tmp_path):
        log_dir = tmp_path / "test_logs_event"
        setup_logger(log_dir=log_dir)

        # Ensure calling log_round_event executes cleanly with various payloads
        log_round_event(
            round_id="20260923001",
            state="ACTIVE_BETTING",
            target="Big",
            ladder_index=0,
            stake=1,
            outcome="Small",
            pnl=-1,
            message="Loss on step 0",
        )

        log_round_event(
            round_id="20260923002",
            state="IDLE_OBSERVING",
            message="Passively observing",
        )
