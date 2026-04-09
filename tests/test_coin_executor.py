"""coin_executor 주문 조회 재시도 등 단위 테스트."""
from unittest.mock import MagicMock

from backend.execution.coin_executor import CoinExecutor


def test_fetch_order_detail_polls_until_done():
    ex = CoinExecutor.__new__(CoinExecutor)
    ex.upbit = MagicMock()
    ex.upbit.get_order.side_effect = [
        {"state": "wait", "executed_volume": "0", "avg_price": "0"},
        {"state": "done", "executed_volume": "0.12", "avg_price": "50000"},
    ]

    detail = CoinExecutor._fetch_order_detail(ex, "uuid-test")

    assert detail["state"] == "done"
    assert float(detail["executed_volume"]) == 0.12
    assert ex.upbit.get_order.call_count == 2


def test_fetch_order_detail_cancel_returns_none():
    ex = CoinExecutor.__new__(CoinExecutor)
    ex.upbit = MagicMock()
    ex.upbit.get_order.return_value = {"state": "cancel", "executed_volume": "0"}

    assert CoinExecutor._fetch_order_detail(ex, "uuid-x") is None
