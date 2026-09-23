"""
config/selectors.py — Abstracted UI selector definitions for 9X-AI.

Decouples DOM element targeting from business logic. Selectors are
defined as dataclasses with primary CSS and fallback XPath strategies,
and can be loaded from a JSON configuration file.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class SelectorTarget:
    """
    Defines a selector with primary CSS and optional XPath fallback.
    
    Attributes:
        css: Primary CSS selector string (may contain comma-separated alternatives).
        xpath: Optional XPath fallback selector.
        description: Human-readable description of the target element.
    """
    css: str
    xpath: Optional[str] = None
    description: str = ""


@dataclass(frozen=True)
class AppSelectors:
    """
    Complete set of UI selectors for the target web application.
    
    Groups all interactive element selectors used by the observer
    and executor subsystems.
    """
    # Round Identification
    current_round_id: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    
    # Timing & Countdown
    countdown_timer_seconds: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    
    # Game History & Results
    history_table_rows: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    history_row_round_id: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    history_row_result_number: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    history_row_result_outcome: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    
    # Interactive Betting Controls
    bet_button_big: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    bet_button_small: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    
    # Amount Input & Chip Multipliers
    amount_input_field: Optional[SelectorTarget] = None
    chip_multiplier_1: Optional[SelectorTarget] = None
    chip_multiplier_5: Optional[SelectorTarget] = None
    chip_multiplier_10: Optional[SelectorTarget] = None
    chip_multiplier_100: Optional[SelectorTarget] = None
    
    # Order Confirmation
    confirm_bet_button: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    cancel_bet_button: Optional[SelectorTarget] = None
    
    # Feedback & Account Status
    wallet_balance_display: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    bet_success_toast: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))
    bet_error_toast: SelectorTarget = field(default_factory=lambda: SelectorTarget(css=""))


def _parse_selector(data: Dict[str, Any]) -> SelectorTarget:
    """Parse a single selector target from a JSON dictionary."""
    return SelectorTarget(
        css=data.get("css", ""),
        xpath=data.get("xpath"),
        description=data.get("description", ""),
    )


def load_selectors_from_json(json_path: Path) -> AppSelectors:
    """
    Load and validate selectors from a JSON configuration file.
    
    Args:
        json_path: Path to the selectors JSON file.
        
    Returns:
        Populated AppSelectors instance.
        
    Raises:
        FileNotFoundError: If the JSON file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        KeyError: If required selector keys are missing.
    """
    if not json_path.exists():
        raise FileNotFoundError(f"Selectors file not found: {json_path}")
    
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Parse required selectors
    required_keys = [
        "current_round_id",
        "countdown_timer_seconds",
        "history_table_rows",
        "history_row_round_id",
        "history_row_result_number",
        "history_row_result_outcome",
        "bet_button_big",
        "bet_button_small",
        "confirm_bet_button",
        "wallet_balance_display",
        "bet_success_toast",
        "bet_error_toast",
    ]
    
    for key in required_keys:
        if key not in raw:
            raise KeyError(f"Required selector '{key}' missing from {json_path}")

    # Parse optional selectors
    optional_fields = {}
    for opt_key in [
        "amount_input_field", "chip_multiplier_1", "chip_multiplier_5",
        "chip_multiplier_10", "chip_multiplier_100", "cancel_bet_button",
    ]:
        if opt_key in raw:
            optional_fields[opt_key] = _parse_selector(raw[opt_key])

    return AppSelectors(
        current_round_id=_parse_selector(raw["current_round_id"]),
        countdown_timer_seconds=_parse_selector(raw["countdown_timer_seconds"]),
        history_table_rows=_parse_selector(raw["history_table_rows"]),
        history_row_round_id=_parse_selector(raw["history_row_round_id"]),
        history_row_result_number=_parse_selector(raw["history_row_result_number"]),
        history_row_result_outcome=_parse_selector(raw["history_row_result_outcome"]),
        bet_button_big=_parse_selector(raw["bet_button_big"]),
        bet_button_small=_parse_selector(raw["bet_button_small"]),
        confirm_bet_button=_parse_selector(raw["confirm_bet_button"]),
        wallet_balance_display=_parse_selector(raw["wallet_balance_display"]),
        bet_success_toast=_parse_selector(raw["bet_success_toast"]),
        bet_error_toast=_parse_selector(raw["bet_error_toast"]),
        **optional_fields,
    )
