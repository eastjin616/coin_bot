import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.telegram_bot import (
    _blocked_selection_summary,
    _command_help_text,
    _format_signal_candle_label,
    _list_handler,
    _performance_handler,
    _performance_report_text,
    _start_handler,
    _stateboard_summary,
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
