from backend.telegram_bot import _blocked_selection_summary, _format_signal_candle_label, _top_selection_summary


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
