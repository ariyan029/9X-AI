"""
tests/test_settings.py — Unit tests for application Settings.

Covers:
- Default settings instantiation
- poll_interval_seconds conversion property
- Environment variable / parameter override
"""

from pathlib import Path
from config.settings import Settings


class TestSettings:
    """Test suite for application Settings."""

    def test_default_settings(self):
        settings = Settings(_env_file=None)
        assert settings.BASE_URL == "https://example-game.com"
        assert settings.HEADLESS is False
        assert settings.MIN_TIMING_WINDOW_SEC == 10
        assert settings.MAX_TIMING_WINDOW_SEC == 25
        assert settings.POLL_INTERVAL_MS == 250
        assert settings.STOP_LOSS_BALANCE == 0.0
        assert settings.MAX_DESYNC_RETRIES == 20

    def test_poll_interval_seconds(self):
        settings = Settings(POLL_INTERVAL_MS=500)
        assert settings.poll_interval_seconds == 0.5

        settings_fast = Settings(POLL_INTERVAL_MS=100)
        assert settings_fast.poll_interval_seconds == 0.1

    def test_custom_overrides(self):
        settings = Settings(
            BASE_URL="https://mygame.test",
            HEADLESS=True,
            USER_DATA_DIR=Path("./custom_user_data"),
            MIN_TIMING_WINDOW_SEC=12,
            MAX_TIMING_WINDOW_SEC=22,
            STOP_LOSS_BALANCE=250.0,
            MAX_DESYNC_RETRIES=5,
        )
        assert settings.BASE_URL == "https://mygame.test"
        assert settings.HEADLESS is True
        assert settings.USER_DATA_DIR == Path("./custom_user_data")
        assert settings.MIN_TIMING_WINDOW_SEC == 12
        assert settings.MAX_TIMING_WINDOW_SEC == 22
        assert settings.STOP_LOSS_BALANCE == 250.0
        assert settings.MAX_DESYNC_RETRIES == 5
