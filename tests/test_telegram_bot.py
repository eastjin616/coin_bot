import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.telegram_bot import (
    _MANUAL_HOLDING_DISCLAIMER,
    _all_coin_rows,
    _blocked_selection_summary,
    _command_help_text,
    _dca_summary_lines,
    _format_signal_candle_label,
    _holding_line,
    _list_handler,
    _load_exchange_only_holdings,
    _load_manual_holdings_from_db,
    _performance_handler,
    _performance_report_text,
    _start_handler,
    _stateboard_summary,
    _status_handler,
    _top_selection_summary,
    _watchlist_add_handler,
    _watchlist_remove_handler,
)


def test_format_signal_candle_label_includes_timestamp():
    label = _format_signal_candle_label("2026-04-09T09:00:00")
    assert "확정 일봉 기준" in label
    assert "04-09 09:00" in label


def test_format_signal_candle_label_handles_missing_value():
    assert _format_signal_candle_label(None) == "확정 일봉 기준"


def test_top_selection_summary_renders_enabled_scores():
    summary = _top_selection_summary([
        {"symbol": "KRW-LINK", "enabled": True, "selection_score": 11.9, "effective_selection_score": 13.1},
        {"symbol": "KRW-BCH", "enabled": True, "selection_score": 17.8, "effective_selection_score": 17.8},
        {"symbol": "KRW-ADA", "enabled": False, "selection_score": 8.2},
    ])
    assert "BCH +17.8" in summary
    assert "LINK +13.1" in summary


def test_blocked_selection_summary_prioritizes_live_derated_symbols():
    summary = _blocked_selection_summary([
        {"symbol": "KRW-TRX", "enabled": False, "live_derated": False, "effective_selection_score": 7.3},
        {"symbol": "KRW-LINK", "enabled": False, "live_derated": True, "effective_selection_score": 13.1},
        {"symbol": "KRW-SOL", "enabled": False, "live_derated": False, "effective_selection_score": 4.0},
    ])
    assert summary == "제외 요약: LINK (live), TRX (score), SOL (score)"


def test_stateboard_summary_renders_symbol_states():
    summary = _stateboard_summary([
        {"symbol": "KRW-BCH", "state_label": "enabled", "effective_selection_score": 17.8},
        {"symbol": "KRW-LINK", "state_label": "live-derated", "effective_selection_score": 13.1},
        {"symbol": "KRW-TRX", "state_label": "score-blocked", "effective_selection_score": 7.3},
    ])
    assert summary == "상태판: BCH=enabled, LINK=live-derated, TRX=score-blocked"


def _fake_update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message)


def _fake_context(*args):
    return SimpleNamespace(args=list(args))


def test_watchlist_remove_marks_symbol_disabled():
    update = _fake_update()
    context = _fake_context("sand")

    with patch("backend.telegram_bot._is_allowed_chat", return_value=True), \
         patch("backend.telegram_bot.set_symbol_manual_override") as mock_set, \
         patch("backend.telegram_bot._held_coin_symbols", return_value=set()):
        asyncio.run(_watchlist_remove_handler(update, context))

    mock_set.assert_called_once_with("KRW-SAND", "disabled", actor="telegram")
    assert "신규매수 제외 완료" in update.message.reply_text.await_args.args[0]


def test_watchlist_add_marks_symbol_enabled():
    update = _fake_update()
    context = _fake_context("ADA")

    with patch("backend.telegram_bot._is_allowed_chat", return_value=True), \
         patch("backend.telegram_bot.set_symbol_manual_override") as mock_set:
        asyncio.run(_watchlist_add_handler(update, context))

    mock_set.assert_called_once_with("KRW-ADA", "enabled", actor="telegram")
    assert "신규매수 허용 완료" in update.message.reply_text.await_args.args[0]


def test_start_handler_mentions_watchlist_commands():
    update = _fake_update()
    context = _fake_context()

    asyncio.run(_start_handler(update, context))

    text = update.message.reply_text.await_args.args[0]
    assert "/performance" in text
    assert "/watchlist" in text
    assert "/watchlist_remove BTC" in text
    assert "/watchlist_add BTC" in text
    assert "/list" in text


def test_list_handler_returns_help_text_for_allowed_chat():
    update = _fake_update()
    context = _fake_context()

    with patch("backend.telegram_bot._is_allowed_chat", return_value=True):
        asyncio.run(_list_handler(update, context))

    assert update.message.reply_text.await_args.args[0] == _command_help_text()


def test_performance_report_text_renders_multi_window_summary():
    with patch(
        "backend.telegram_bot.runtime_managed_window_performance",
        return_value=[
            {
                "days": 7,
                "label": "runtime-managed",
                "realized_pnl_krw": 12345.0,
                "win_rate": 66.7,
                "avg_pnl_pct": 4.2,
                "sell_count": 3,
                "buy_count": 2,
                "top_winner": {
                    "symbol": "KRW-BCH",
                    "realized_pnl_krw": 10000.0,
                    "win_rate": 100.0,
                    "avg_pnl_pct": 10.0,
                    "sell_count": 1,
                },
                "top_loser": {
                    "symbol": "KRW-LINK",
                    "realized_pnl_krw": -5000.0,
                    "win_rate": 0.0,
                    "avg_pnl_pct": -8.0,
                    "sell_count": 2,
                },
            }
        ],
    ), patch(
        "backend.telegram_bot.base_enabled_window_performance",
        return_value=[
            {
                "days": 7,
                "label": "base-enabled",
                "realized_pnl_krw": 6789.0,
                "win_rate": 50.0,
                "avg_pnl_pct": 1.1,
                "sell_count": 2,
                "buy_count": 1,
                "top_winner": {
                    "symbol": "KRW-ADA",
                    "realized_pnl_krw": 7000.0,
                    "win_rate": 100.0,
                    "avg_pnl_pct": 5.0,
                    "sell_count": 1,
                },
                "top_loser": {
                    "symbol": "KRW-BCH",
                    "realized_pnl_krw": -211.0,
                    "win_rate": 0.0,
                    "avg_pnl_pct": -0.5,
                    "sell_count": 1,
                },
            }
        ],
    ):
        text = _performance_report_text([7])

    assert "기준 1: runtime_params 등록 종목 전체" in text
    assert "기준 2: 현재 base-enabled 코어" in text
    assert "7일: 실현손익 +12,345원" in text
    assert "최고: BCH +10,000원" in text
    assert "최저: LINK -5,000원" in text
    assert "7일: 실현손익 +6,789원" in text
    assert "최고: ADA +7,000원" in text


def test_performance_handler_returns_report_for_allowed_chat():
    update = _fake_update()
    context = _fake_context()

    with patch("backend.telegram_bot._is_allowed_chat", return_value=True), \
         patch("backend.telegram_bot._performance_report_text", return_value="perf report"):
        asyncio.run(_performance_handler(update, context))

    assert update.message.reply_text.await_args.args[0] == "perf report"


def test_status_handler_includes_exchange_only_manual_holding():
    update = _fake_update()
    context = _fake_context()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchall.return_value = []

    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_conn
    mock_db.__exit__.return_value = None

    runtime_status = {
        "regime": "risk_on",
        "btc": {"signal_candle_time": "2026-04-18T09:00:00"},
        "suggested_order_size_ratio": 0.2,
        "buy_enabled_symbols": ["KRW-BCH"],
        "selection": [
            {"symbol": "KRW-BCH", "enabled": True, "state_label": "enabled", "effective_selection_score": 10.8},
        ],
        "live_derated_symbols": {},
        "loss_streak_cooled_symbols": {},
        "recent_30d": {"realized_pnl_krw": 0.0, "win_rate": 0.0, "sell_count": 0},
    }

    executor = MagicMock()
    executor.get_balance_krw.return_value = 1.0

    with patch("backend.telegram_bot._is_allowed_chat", return_value=True), \
         patch("backend.telegram_bot.get_db", return_value=mock_db), \
         patch("backend.telegram_bot._load_manual_holdings_from_db", return_value=(True, [{
             "symbol": "KRW-ETH",
             "entry_price": 3_000_000.0,
             "quantity": 0.123456,
             "source": "manual",
         }])), \
         patch("backend.telegram_bot.get_runtime_status", return_value=runtime_status), \
         patch("backend.execution.coin_executor.CoinExecutor", return_value=executor), \
         patch("backend.ai.chart_generator.get_coin_signal_indicators", return_value={"rsi": 55.0}), \
         patch("pyupbit.get_current_price", return_value=3_300_000.0):
        asyncio.run(_status_handler(update, context))

    final_text = update.message.reply_text.await_args_list[-1].args[0]
    assert "ETH (수동보유)" in final_text
    assert "📭 보유 중인 코인 없음" not in final_text
    assert "자동매매 포지션에는 미편입" in final_text


# ── 신규 테스트 ──────────────────────────────────────────────────────────────


def test_holding_line_manual_source_label():
    line, _, _ = _holding_line("KRW-ETH", 3_000_000.0, 1.0, 3_300_000.0, source="manual")
    assert "(수동보유)" in line
    assert "ETH" in line


def test_holding_line_pnl_calculation():
    line, invested, current_val = _holding_line(
        "KRW-BCH", 500_000.0, 2.0, 550_000.0, source="position"
    )
    assert "+10.0%" in line
    assert invested == 1_000_000.0
    assert current_val == 1_100_000.0


def test_holding_line_zero_entry_price_falls_back_to_eval():
    line, invested, current_val = _holding_line("KRW-ETH", 0.0, 1.0, 3_000_000.0)
    assert "👀" in line
    assert invested == 0.0
    assert current_val == 3_000_000.0


def test_load_manual_holdings_from_db_returns_rows_excluding_tracked():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchall.return_value = [
        {"symbol": "KRW-ETH", "quantity": 1.0, "avg_buy_price": 3_000_000.0},
        {"symbol": "KRW-BTC", "quantity": 0.01, "avg_buy_price": 90_000_000.0},
    ]
    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_conn
    mock_db.__exit__.return_value = None

    with patch("backend.telegram_bot.get_db", return_value=mock_db):
        ok, rows = _load_manual_holdings_from_db({"KRW-BTC"})

    assert ok is True
    assert len(rows) == 1
    assert rows[0]["symbol"] == "KRW-ETH"
    assert rows[0]["source"] == "manual"


def test_load_manual_holdings_from_db_returns_false_on_exception():
    with patch("backend.telegram_bot.get_db", side_effect=RuntimeError("DB down")):
        ok, rows = _load_manual_holdings_from_db(set())

    assert ok is False
    assert rows == []


def test_load_exchange_only_holdings_falls_back_to_api_on_db_failure():
    executor = MagicMock()
    executor.get_all_coin_holdings_snapshot.return_value = (
        True,
        [{"symbol": "KRW-ETH", "quantity": 1.0, "avg_buy_price": 3_000_000.0, "current_price": 3_300_000.0}],
    )

    with patch("backend.telegram_bot._load_manual_holdings_from_db", return_value=(False, [])):
        ok, rows = _load_exchange_only_holdings(executor, set())

    assert ok is True
    assert len(rows) == 1
    assert rows[0]["symbol"] == "KRW-ETH"
    assert rows[0]["source"] == "manual"


def test_all_coin_rows_db_exception_returns_empty_positions():
    executor = MagicMock()

    with patch("backend.telegram_bot._load_coin_position_rows", side_effect=RuntimeError("DB error")), \
         patch("backend.telegram_bot._load_exchange_only_holdings", return_value=(True, [])):
        rows, holdings_ok = _all_coin_rows(executor)

    assert rows == []
    assert holdings_ok is True


def test_dca_summary_lines_returns_empty_when_disabled():
    with patch("backend.telegram_bot.get_settings") as mock_settings:
        mock_settings.return_value.dca_enabled = False
        lines = _dca_summary_lines()
    assert lines == []


def test_dca_summary_lines_renders_positions_when_enabled():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchall.return_value = [
        {"symbol": "KRW-BCH", "dca_count": 1, "last_buy_rsi": 38.0},
        {"symbol": "KRW-ADA", "dca_count": 0, "last_buy_rsi": None},
    ]
    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_conn
    mock_db.__exit__.return_value = None

    with patch("backend.telegram_bot.get_settings") as mock_settings, \
         patch("backend.telegram_bot.get_db", return_value=mock_db):
        mock_settings.return_value.dca_enabled = True
        mock_settings.return_value.max_dca_count = 2
        mock_settings.return_value.dca_step_rsi = 5.0
        lines = _dca_summary_lines()

    assert any("BCH" in l for l in lines)
    assert any("33.0" in l for l in lines)  # 38.0 - 5.0
    assert any("ADA" in l for l in lines)
