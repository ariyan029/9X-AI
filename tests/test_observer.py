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


import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_observer_get_countdown_seconds():
    selectors = AppSelectors()
    observer = DomObserver(selectors)

    # Test mm:ss format
    observer._query_text = AsyncMock(return_value="00:25")
    assert await observer.get_countdown_seconds(None) == 25

    observer._query_text = AsyncMock(return_value="0:09")
    assert await observer.get_countdown_seconds(None) == 9

    observer._query_text = AsyncMock(return_value="00:00")
    assert await observer.get_countdown_seconds(None) == 0

    # Test plain seconds format
    observer._query_text = AsyncMock(return_value="18")
    assert await observer.get_countdown_seconds(None) == 18

    # Test out-of-bounds (> 60s)
    observer._query_text = AsyncMock(return_value="02:15")
    assert await observer.get_countdown_seconds(None) is None


@pytest.mark.asyncio
async def test_observer_get_current_round_id():
    selectors = AppSelectors()
    observer = DomObserver(selectors)

    # Standard long ID
    observer._query_text = AsyncMock(return_value="Issue: 2026092400123")
    assert await observer.get_current_round_id(None) == "2026092400123"

    # Short 4-digit ID
    observer._query_text = AsyncMock(return_value="No. 1001")
    assert await observer.get_current_round_id(None) == "1001"

    # No digits
    observer._query_text = AsyncMock(return_value="Pending...")
    assert await observer.get_current_round_id(None) is None

