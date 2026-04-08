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
                "suggested_order_size_ratio": 0.1,
                "btc": {"rsi": 40.0, "ma5": 1, "ma20": 2, "current_price": 3},
                "buy_enabled_symbols": ["KRW-BTC", "KRW-LINK"],
                "buy_blocked_symbols": ["KRW-ADA"],
                "selection": [],
                "active_watchlist_symbols": ["KRW-BTC", "KRW-LINK"],
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
    assert data["buy_enabled_symbols"] == ["KRW-BTC", "KRW-LINK"]
    assert data["recent_30d"]["win_rate"] == 75.0
