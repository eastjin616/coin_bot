from fastapi.testclient import TestClient
from unittest.mock import patch


def test_runtime_status_returns_expected_shape():
    with patch.dict("os.environ", {"DASHBOARD_API_KEY": "", "VERCEL_ORIGIN": "http://localhost:3000"}):
        from backend.config import get_settings
        get_settings.cache_clear()
        from backend.main import app

        with patch("backend.routers.runtime.get_runtime_status") as mock_status:
            mock_status.return_value = {
                "regime": "caution",
                "risk_off": True,
                "signal_basis": "previous_closed_day",
                "suggested_order_size_ratio": 0.1,
                "btc": {"rsi": 40.0, "ma5": 1, "ma20": 2, "current_price": 3, "signal_candle_time": "2026-04-09T09:00:00"},
                "buy_enabled_symbols": ["KRW-BTC", "KRW-LINK"],
                "buy_blocked_symbols": ["KRW-ADA"],
                "selection": [
                    {
                        "symbol": "KRW-LINK",
                        "name": "체인링크",
                        "enabled": True,
                        "base_enabled": True,
                        "live_derated": False,
                        "loss_streak_cooled": False,
                        "reason": "점수 기반 상위 3 선발 #2",
                        "realistic_return_pct": 24.5,
                        "recent_oos_pct": -7.0,
                        "selection_score": 11.9,
                        "live_score_adjustment": 1.2,
                        "effective_selection_score": 13.1,
                        "state_label": "enabled",
                    }
                ],
                "active_watchlist_symbols": ["KRW-BTC", "KRW-LINK"],
                "live_derated_symbols": {"KRW-ADA": "live-derated: bad recent pnl"},
                "loss_streak_cooled_symbols": {"KRW-BCH": "streak-cooled: loss-streak cooldown"},
                "recent_symbol_performance": {"KRW-LINK": {"sell_count": 3, "win_rate": 33.3}},
                "recent_30d": {
                    "realized_pnl_krw": 12345.0,
                    "sell_count": 4,
                    "win_count": 3,
                    "win_rate": 75.0,
                },
            }
            client = TestClient(app)
            response = client.get("/api/runtime/status")

    assert response.status_code == 200
    data = response.json()
    assert data["regime"] == "caution"
    assert data["risk_off"] is True
    assert data["signal_basis"] == "previous_closed_day"
    assert data["buy_enabled_symbols"] == ["KRW-BTC", "KRW-LINK"]
    assert data["selection"][0]["selection_score"] == 11.9
    assert data["selection"][0]["effective_selection_score"] == 13.1
    assert data["selection"][0]["base_enabled"] is True
    assert data["selection"][0]["loss_streak_cooled"] is False
    assert data["selection"][0]["state_label"] == "enabled"
    assert data["live_derated_symbols"]["KRW-ADA"].startswith("live-derated")
    assert data["loss_streak_cooled_symbols"]["KRW-BCH"].startswith("streak-cooled")
    assert data["recent_symbol_performance"]["KRW-LINK"]["sell_count"] == 3
    assert data["recent_30d"]["win_rate"] == 75.0
