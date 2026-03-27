import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    with patch.dict("os.environ", {"DASHBOARD_API_KEY": "", "VERCEL_ORIGIN": "http://localhost:3000"}):
        from backend.config import get_settings
        get_settings.cache_clear()
        from backend.main import app
        yield TestClient(app)


def test_portfolio_returns_structure(client):
    with patch("backend.routers.portfolio.CoinExecutor") as MockExec:
        mock = MockExec.return_value
        mock.get_balance_krw.return_value = 100000.0
        with patch("backend.routers.portfolio.pyupbit.Upbit") as MockUpbit:
            mock_upbit_instance = MagicMock()
            MockUpbit.return_value = mock_upbit_instance
            mock_upbit_instance.get_balances.return_value = []
            resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert "krw_balance" in data
    assert "holdings" in data
    assert "total_value" in data


def test_portfolio_calculates_total_value(client):
    with patch("backend.routers.portfolio.CoinExecutor") as MockExec:
        mock = MockExec.return_value
        mock.get_balance_krw.return_value = 50000.0
        with patch("backend.routers.portfolio.pyupbit.Upbit") as MockUpbit:
            mock_upbit_instance = MagicMock()
            MockUpbit.return_value = mock_upbit_instance
            mock_upbit_instance.get_balances.return_value = [
                {"currency": "BTC", "balance": "0.001", "avg_buy_price": "80000000"}
            ]
            with patch("backend.routers.portfolio.pyupbit.get_current_price") as mock_price:
                mock_price.return_value = {"KRW-BTC": 90000000}
                resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    # total_value = krw_balance(50000) + BTC eval(0.001 * 90000000 = 90000) = 140000
    assert abs(data["total_value"] - 140000.0) < 1000
