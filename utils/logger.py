"""
utils/logger.py — Structured logging with Loguru for 9X-AI.

Configures console and file logging with round-level tracing,
PnL tracking, and rotating audit log files.
"""

import sys
from pathlib import Path
from loguru import logger


def setup_logger(
    log_dir: Path = Path("./logs"),
    console_level: str = "INFO",
    file_level: str = "DEBUG",
) -> None:
    """
    Configure Loguru for 9X-AI structured logging.
    
    Sets up:
    - Colored console output at INFO level
    - Rotating JSON file logs at DEBUG level
    - Audit trail files with date-based rotation
    
    Args:
        log_dir: Directory for log files (created if missing).
        console_level: Minimum log level for console output.
        file_level: Minimum log level for file output.
    """
    # Ensure log directory exists
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Console handler with color
    logger.add(
        sys.stderr,
        level=console_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler with rotation
    logger.add(
        str(log_dir / "audit_{time:YYYY-MM-DD}.log"),
        level=file_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",  # Rotate at midnight
        retention="30 days",
        compression="gz",
        serialize=False,
    )

    # JSON structured log for machine parsing
    logger.add(
        str(log_dir / "structured_{time:YYYY-MM-DD}.jsonl"),
        level=file_level,
        serialize=True,
        rotation="00:00",
        retention="30 days",
        compression="gz",
    )


def log_round_event(
    round_id: str,
    state: str,
    target: str = "",
    ladder_index: int = -1,
    stake: int = 0,
    outcome: str = "",
    pnl: int = 0,
    message: str = "",
):
    """
    Log a structured round event with all relevant context.
    
    Args:
        round_id: Current round identifier.
        state: Current engine state name.
        target: Active bet target ("Big"/"Small" or empty).
        ladder_index: Current ladder position (-1 if N/A).
        stake: Current bet amount (0 if N/A).
        outcome: Round outcome ("Big"/"Small" or empty).
        pnl: Profit/loss for this event (0 if N/A).
        message: Additional context message.
    """
    logger.info(
        "[{round_id}] [{state}] Target={target} Ladder={ladder_index} "
        "Stake={stake} Outcome={outcome} PnL={pnl:+d} | {message}",
        round_id=round_id,
        state=state,
        target=target or "—",
        ladder_index=ladder_index,
        stake=stake,
        outcome=outcome or "—",
        pnl=pnl,
        message=message,
    )
