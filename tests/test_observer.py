"""
Unit tests for DomObserver round ID tracking and desync counting.
"""
from browser.observer import DomObserver
from config.selectors import AppSelectors


def test_observer_round_id_numeric_tracking():
    selectors = AppSelectors()
    observer = DomObserver(selectors)

    # Initial state
    assert observer.is_new_round("100") is True
    observer.mark_processed("100")
    assert observer.last_processed_round_id == "100"

    # Same round is not new
    assert observer.is_new_round("100") is False

    # Previous round is not new
    assert observer.is_new_round("99") is False

    # Numeric rollover: "999" -> "1000"
    observer.mark_processed("999")
    assert observer.is_new_round("1000") is True
    observer.mark_processed("1000")
    assert observer.is_new_round("999") is False


def test_observer_duplicate_in_processed_set():
    selectors = AppSelectors()
    observer = DomObserver(selectors)

    observer.mark_processed("round_A")
    assert observer.is_new_round("round_A") is False
    assert observer.is_new_round("  round_A  ") is False


def test_observer_processed_history_cap():
    selectors = AppSelectors()
    observer = DomObserver(selectors)

    for i in range(250):
        observer.mark_processed(str(i))

    # Should have capped to at most 100 elements when exceeding 200
    assert len(observer._processed_round_ids) <= 150
    assert "249" in observer._processed_round_ids
