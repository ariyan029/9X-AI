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
from unittest.mock import AsyncMock, MagicMock


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


def test_network_interceptor_parse_response():
    from browser.observer import NetworkInterceptor
    from core.models import GameOutcome

    interceptor = NetworkInterceptor()
    payload = {
        "code": 0,
        "data": {
            "gameslist": [
                {"issueNumber": "20260924100051775", "number": "2", "colour": "red"},
                {"issueNumber": "20260924100051774", "number": "4", "colour": "red"},
            ]
        }
    }
    interceptor._parse_response_body(payload)
    resolutions = interceptor.get_resolutions()

    assert len(resolutions) == 2
    assert resolutions[0].round_id == "20260924100051775"
    assert resolutions[0].result_number == 2
    assert resolutions[0].outcome == GameOutcome.SMALL
    assert resolutions[1].round_id == "20260924100051774"
    assert resolutions[1].result_number == 4
    assert resolutions[1].outcome == GameOutcome.SMALL


@pytest.mark.asyncio
async def test_observer_snapshot_merges_network_and_dom():
    from core.models import RoundResolution, GameOutcome

    selectors = AppSelectors()
    observer = DomObserver(selectors)

    # DOM only has older round 1774
    dom_res = [
        RoundResolution(round_id="20260924100051774", result_number=4, outcome=GameOutcome.SMALL),
    ]
    observer.get_latest_history = AsyncMock(return_value=dom_res)
    observer.get_current_round_id = AsyncMock(return_value="20260924100051776")
    observer.get_countdown_seconds = AsyncMock(return_value=20)

    # Network has newest round 1775
    observer.network_interceptor._resolutions["20260924100051775"] = RoundResolution(
        round_id="20260924100051775", result_number=2, outcome=GameOutcome.SMALL
    )

    snapshot = await observer.take_snapshot(page=None)

    assert len(snapshot.history) == 2
    # Verify latest round is 1775 at index 0 (descending order)
    assert snapshot.history[0].round_id == "20260924100051775"
    assert snapshot.history[1].round_id == "20260924100051774"


@pytest.mark.asyncio
async def test_observer_lag_triggers_refresh():
    from core.models import RoundResolution, GameOutcome

    selectors = AppSelectors()
    observer = DomObserver(selectors)

    # Active round is 1776, history only has 1774 (lag = 2)
    dom_res = [
        RoundResolution(round_id="20260924100051774", result_number=4, outcome=GameOutcome.SMALL),
    ]
    observer.get_latest_history = AsyncMock(return_value=dom_res)
    observer.get_current_round_id = AsyncMock(return_value="20260924100051776")
    observer.get_countdown_seconds = AsyncMock(return_value=20)
    observer.trigger_history_refresh = AsyncMock(return_value=True)

    mock_page = MagicMock()
    await observer.take_snapshot(page=mock_page)

    # Verify refresh was triggered
    assert observer.trigger_history_refresh.called


def test_fetch_api_history_sync_mock(monkeypatch):
    import json
    import io
    from browser.observer import fetch_api_history_sync
    from core.models import GameOutcome

    mock_response_data = {
        "code": 0,
        "msg": "Succeed",
        "data": {
            "list": [
                {"issueNumber": "20260924100051999", "number": "7", "colour": "green"},
                {"issueNumber": "20260924100051998", "number": "2", "colour": "red"},
            ]
        }
    }

    class MockHTTPResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps(mock_response_data).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=4: MockHTTPResponse())

    results = fetch_api_history_sync(type_id=30, page_size=2)
    assert len(results) == 2
    assert results[0].round_id == "20260924100051999"
    assert results[0].result_number == 7
    assert results[0].outcome == GameOutcome.BIG
    assert results[1].round_id == "20260924100051998"
    assert results[1].result_number == 2
    assert results[1].outcome == GameOutcome.SMALL



