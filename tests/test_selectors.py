"""
tests/test_selectors.py — Unit tests for selector configuration and schema loader.

Covers:
- _parse_selector with CSS, XPath, and description
- load_selectors_from_json with real config/selectors.json
- load_selectors_from_json error cases:
  - FileNotFoundError on missing file
  - json.JSONDecodeError on invalid JSON syntax
  - KeyError when required selector keys are missing
- Optional selector handling (chip multipliers, input field)
"""

import json
import pytest
from pathlib import Path
from config.selectors import (
    SelectorTarget,
    AppSelectors,
    _parse_selector,
    load_selectors_from_json,
)


class TestParseSelector:
    """Test _parse_selector helper function."""

    def test_parse_full_selector(self):
        data = {
            "css": "button.submit",
            "xpath": "//button[@type='submit']",
            "description": "Submit button",
        }
        target = _parse_selector(data)
        assert target.css == "button.submit"
        assert target.xpath == "//button[@type='submit']"
        assert target.description == "Submit button"

    def test_parse_minimal_selector(self):
        data = {"css": "div.timer"}
        target = _parse_selector(data)
        assert target.css == "div.timer"
        assert target.xpath is None
        assert target.description == ""


class TestLoadSelectorsFromJson:
    """Test load_selectors_from_json loader."""

    def test_load_real_project_selectors(self):
        """Verify the actual config/selectors.json file loads and validates cleanly."""
        path = Path("config/selectors.json")
        selectors = load_selectors_from_json(path)
        assert isinstance(selectors, AppSelectors)
        assert selectors.current_round_id.css != ""
        assert selectors.countdown_timer_seconds.css != ""
        assert selectors.bet_button_big.css != ""
        assert selectors.bet_button_small.css != ""
        assert selectors.confirm_bet_button.css != ""

    def test_missing_file_raises_file_not_found(self, tmp_path):
        missing_path = tmp_path / "non_existent_selectors.json"
        with pytest.raises(FileNotFoundError, match="not found"):
            load_selectors_from_json(missing_path)

    def test_invalid_json_raises_decode_error(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{ unclosed json: ", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_selectors_from_json(bad_json)

    def test_missing_required_key_raises_key_error(self, tmp_path):
        incomplete_json = tmp_path / "incomplete.json"
        data = {
            "current_round_id": {"css": ".round"},
            # Missing remaining required keys
        }
        incomplete_json.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(KeyError, match="Required selector"):
            load_selectors_from_json(incomplete_json)

    def test_load_with_all_optional_keys(self, tmp_path):
        full_json = tmp_path / "full.json"
        data = {
            "current_round_id": {"css": ".round"},
            "countdown_timer_seconds": {"css": ".timer"},
            "history_table_rows": {"css": ".rows"},
            "history_row_round_id": {"css": ".r-id"},
            "history_row_result_number": {"css": ".r-num"},
            "history_row_result_outcome": {"css": ".r-out"},
            "bet_button_big": {"css": ".btn-big"},
            "bet_button_small": {"css": ".btn-small"},
            "confirm_bet_button": {"css": ".btn-confirm"},
            "wallet_balance_display": {"css": ".balance"},
            "bet_success_toast": {"css": ".toast-ok"},
            "bet_error_toast": {"css": ".toast-err"},
            "amount_input_field": {"css": ".input-amount"},
            "chip_multiplier_1": {"css": ".chip-1"},
            "chip_multiplier_5": {"css": ".chip-5"},
            "chip_multiplier_10": {"css": ".chip-10"},
            "chip_multiplier_100": {"css": ".chip-100"},
            "cancel_bet_button": {"css": ".btn-cancel"},
        }
        full_json.write_text(json.dumps(data), encoding="utf-8")
        selectors = load_selectors_from_json(full_json)
        assert selectors.amount_input_field is not None
        assert selectors.amount_input_field.css == ".input-amount"
        assert selectors.chip_multiplier_1 is not None
        assert selectors.chip_multiplier_5 is not None
        assert selectors.chip_multiplier_10 is not None
        assert selectors.chip_multiplier_100 is not None
        assert selectors.cancel_bet_button is not None
