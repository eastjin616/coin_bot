"""coin_executor 주문 조회 재시도 등 단위 테스트."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from backend.execution.coin_executor import CoinExecutor, get_current_prices_safe


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


def test_get_current_prices_safe_filters_unsupported_symbols():
    def fake_price(symbol):
        return {"KRW-BCH": 500000.0, "KRW-LINK": 13000.0}[symbol]

    with patch("backend.execution.coin_executor.pyupbit.get_tickers", return_value=["KRW-BCH", "KRW-LINK"]), \
         patch("backend.execution.coin_executor.pyupbit.get_current_price", side_effect=fake_price) as mock_price:
        prices = get_current_prices_safe(["KRW-BCH", "KRW-LINK", "KRW-SAND"])

    assert prices == {"KRW-BCH": 500000.0, "KRW-LINK": 13000.0}
    assert mock_price.call_count == 2
    mock_price.assert_any_call("KRW-BCH")
    mock_price.assert_any_call("KRW-LINK")


def test_get_current_prices_safe_falls_back_to_single_symbol_queries():
    def fake_get_current_price(arg):
        values = {"KRW-BCH": 500000.0, "KRW-LINK": 13000.0}
        if arg == "KRW-BCH":
            raise RuntimeError("Code not found")
        return values[arg]

    with patch("backend.execution.coin_executor.pyupbit.get_tickers", return_value=["KRW-BCH", "KRW-LINK"]), \
         patch("backend.execution.coin_executor.pyupbit.get_current_price", side_effect=fake_get_current_price):
        prices = get_current_prices_safe(["KRW-BCH", "KRW-LINK"])

    assert prices == {"KRW-LINK": 13000.0}


def test_record_buy_fill_inserts_trade_and_upserts_position_in_one_commit():
    ex = CoinExecutor.__new__(CoinExecutor)
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = {"id": 1}
    mock_conn.cursor.return_value = mock_cur

    with patch("backend.execution.coin_executor.get_db", return_value=mock_conn):
        ok = CoinExecutor._record_buy_fill(ex, "KRW-LINK", "uuid-buy-1", 100.0, 50000.0, 0.12)

    assert ok is True
    assert mock_conn.commit.call_count == 1
    executed_sql = [call.args[0] for call in mock_cur.execute.call_args_list]
    assert any("INSERT INTO trades" in sql for sql in executed_sql)
    assert any("INSERT INTO positions" in sql and "ON CONFLICT (market, symbol)" in sql for sql in executed_sql)


def test_record_buy_fill_treats_duplicate_order_uuid_as_idempotent():
    ex = CoinExecutor.__new__(CoinExecutor)
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cur

    with patch("backend.execution.coin_executor.get_db", return_value=mock_conn):
        ok = CoinExecutor._record_buy_fill(ex, "KRW-LINK", "uuid-buy-1", 100.0, 50000.0, 0.12)

    assert ok is True
    assert mock_conn.commit.call_count == 1
    assert len(mock_cur.execute.call_args_list) == 1
    assert "INSERT INTO trades" in mock_cur.execute.call_args_list[0].args[0]


def test_record_sell_fill_inserts_trade_and_deletes_position_in_one_commit():
    ex = CoinExecutor.__new__(CoinExecutor)
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = {"id": 2}
    mock_conn.cursor.return_value = mock_cur

    with patch("backend.execution.coin_executor.get_db", return_value=mock_conn):
        ok = CoinExecutor._record_sell_fill(
            ex,
            "KRW-LINK",
            "uuid-sell-1",
            100.0,
            53000.0,
            0.12,
            pnl_krw=360.0,
            pnl_pct=6.0,
        )

    assert ok is True
    assert mock_conn.commit.call_count == 1
    executed_sql = [call.args[0] for call in mock_cur.execute.call_args_list]
    assert any("INSERT INTO trades" in sql for sql in executed_sql)
    assert any("DELETE FROM positions" in sql for sql in executed_sql)


def test_reconcile_open_order_journal_replays_missing_buy_fill():
    ex = CoinExecutor.__new__(CoinExecutor)
    ex.upbit = MagicMock()
    ex._load_pending_order_journal = MagicMock(return_value=[
        {
            "order_uuid": "uuid-buy-2",
            "symbol": "KRW-LINK",
            "action": "BUY",
            "requested_amount_krw": 50000.0,
            "requested_quantity": None,
            "entry_price_snapshot": None,
        }
    ])
    ex._trade_already_recorded = MagicMock(return_value=False)
    ex._fetch_order_snapshot = MagicMock(return_value={"state": "done", "executed_volume": "0.1", "avg_price": "500000"})
    ex._record_buy_fill = MagicMock(return_value=True)
    ex._record_sell_fill = MagicMock(return_value=True)
    ex._mark_order_journal_status = MagicMock()

    summary = CoinExecutor.reconcile_open_order_journal(ex)

    assert summary["checked"] == 1
    assert summary["completed"] == 1
    ex._record_buy_fill.assert_called_once_with("KRW-LINK", "uuid-buy-2", 100.0, 500000.0, 0.1)
    ex._mark_order_journal_status.assert_any_call("uuid-buy-2", "reconciling")
    ex._mark_order_journal_status.assert_any_call("uuid-buy-2", "completed")


def test_reconcile_open_order_journal_marks_existing_trade_completed():
    ex = CoinExecutor.__new__(CoinExecutor)
    ex.upbit = MagicMock()
    ex._load_pending_order_journal = MagicMock(return_value=[
        {"order_uuid": "uuid-buy-3", "symbol": "KRW-LINK", "action": "BUY"}
    ])
    ex._trade_already_recorded = MagicMock(return_value=True)
    ex._fetch_order_snapshot = MagicMock()
    ex._record_buy_fill = MagicMock()
    ex._mark_order_journal_status = MagicMock()

    summary = CoinExecutor.reconcile_open_order_journal(ex)

    assert summary["checked"] == 1
    assert summary["completed"] == 1
    ex._fetch_order_snapshot.assert_not_called()
    ex._record_buy_fill.assert_not_called()
    ex._mark_order_journal_status.assert_called_once_with("uuid-buy-3", "completed")


def test_fetch_recent_done_orders_normalizes_pyupbit_tuple_payload():
    ex = CoinExecutor.__new__(CoinExecutor)
    ex.upbit = MagicMock()
    ex.upbit.get_order.return_value = ([{"uuid": "u1"}, {"uuid": "u2"}], {"group": "order"})

    rows = CoinExecutor._fetch_recent_done_orders(ex, "KRW-LINK", limit=3)

    assert rows == [{"uuid": "u1"}, {"uuid": "u2"}]
    ex.upbit.get_order.assert_called_once_with("KRW-LINK", state="done", limit=3, contain_req=True)


def test_backfill_recent_done_orders_seeds_missing_uuid_only():
    ex = CoinExecutor.__new__(CoinExecutor)
    ex.upbit = MagicMock()
    ex._fetch_recent_done_orders = MagicMock(return_value=[
        {"uuid": "done-1", "side": "bid", "executed_volume": "0.2", "avg_price": "1000"},
        {"uuid": "done-2", "side": "ask", "executed_volume": "0.1", "avg_price": "1100"},
    ])
    ex._trade_already_recorded = MagicMock(side_effect=[False, True])
    ex._order_journal_exists = MagicMock(return_value=False)
    ex._record_order_submission = MagicMock()
    ex._position_entry_price = MagicMock(return_value=900.0)

    summary = CoinExecutor.backfill_recent_done_orders(ex, ["KRW-LINK"], per_symbol_limit=2)

    assert summary == {"symbols": 1, "orders_seen": 2, "seeded": 1}
    ex._record_order_submission.assert_called_once_with(
        symbol="KRW-LINK",
        action="BUY",
        order_uuid="done-1",
        requested_amount_krw=200.0,
        requested_quantity=None,
        entry_price_snapshot=None,
        order_created_at=None,
    )


def test_reconstruct_entry_price_from_trades_replays_position_state():
    ex = CoinExecutor.__new__(CoinExecutor)
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        {"action": "BUY", "price": 100.0, "quantity": 2.0},
        {"action": "BUY", "price": 130.0, "quantity": 1.0},
        {"action": "SELL", "price": 140.0, "quantity": 1.0},
    ]
    mock_conn.cursor.return_value = mock_cur

    with patch("backend.execution.coin_executor.get_db", return_value=mock_conn):
        entry = CoinExecutor._reconstruct_entry_price_from_trades(ex, "KRW-LINK")

    assert round(entry, 6) == round((100.0 * 2.0 + 130.0 * 1.0) / 3.0, 6)


def test_backfill_recent_done_orders_uses_reconstructed_entry_price_for_sell():
    ex = CoinExecutor.__new__(CoinExecutor)
    ex.upbit = MagicMock()
    created_at = datetime(2026, 4, 10, 9, 0, 0)
    ex._fetch_recent_done_orders = MagicMock(return_value=[
        {"uuid": "done-sell-1", "side": "ask", "executed_volume": "0.1", "avg_price": "1100", "created_at": created_at.isoformat()},
    ])
    ex._trade_already_recorded = MagicMock(return_value=False)
    ex._order_journal_exists = MagicMock(return_value=False)
    ex._record_order_submission = MagicMock()
    ex._position_entry_price = MagicMock(return_value=0.0)
    ex._reconstruct_entry_price_from_trades = MagicMock(return_value=900.0)

    summary = CoinExecutor.backfill_recent_done_orders(ex, ["KRW-LINK"], per_symbol_limit=2)

    assert summary == {"symbols": 1, "orders_seen": 1, "seeded": 1}
    ex._reconstruct_entry_price_from_trades.assert_called_once_with("KRW-LINK", created_at)
    ex._record_order_submission.assert_called_once_with(
        symbol="KRW-LINK",
        action="SELL",
        order_uuid="done-sell-1",
        requested_amount_krw=None,
        requested_quantity=0.1,
        entry_price_snapshot=900.0,
        order_created_at=created_at,
    )
