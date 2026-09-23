"""
config/settings.py — Pydantic v2 typed settings for 9X-AI.

Loads configuration from environment variables and .env file.
All timing, path, and safety parameters are centralized here.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables / .env file.
    
    Attributes:
        BASE_URL: Target web application URL.
        HEADLESS: Run browser in headless mode (False for debugging).
        USER_DATA_DIR: Path to persistent Chromium user data directory.
        MIN_TIMING_WINDOW_SEC: Lower bound of betting window (seconds remaining).
        MAX_TIMING_WINDOW_SEC: Upper bound of betting window (seconds remaining).
        POLL_INTERVAL_MS: DOM polling interval in milliseconds.
        STOP_LOSS_BALANCE: Minimum wallet balance before HALT.
        MAX_DESYNC_RETRIES: Max consecutive DOM errors before HALT.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    BASE_URL: str = "https://example-game.com"
    HEADLESS: bool = False
    USER_DATA_DIR: Path = Path("./user_data")
    MIN_TIMING_WINDOW_SEC: int = 10
    MAX_TIMING_WINDOW_SEC: int = 25
    POLL_INTERVAL_MS: int = 250
    STOP_LOSS_BALANCE: float = 0.0
    MAX_DESYNC_RETRIES: int = 20

    @property
    def poll_interval_seconds(self) -> float:
        """Convert poll interval from milliseconds to seconds."""
        return self.POLL_INTERVAL_MS / 1000.0
