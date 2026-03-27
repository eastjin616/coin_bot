from unittest.mock import patch, MagicMock

def test_get_portfolio_tool_returns_string():
    from backend.ai.agent_tools import get_portfolio_tool
    with patch("backend.ai.agent_tools.CoinExecutor") as MockExec:
        mock = MockExec.return_value
        mock.get_balance_krw.return_value = 100000.0
        with patch("backend.ai.agent_tools.pyupbit.Upbit") as MockUpbit:
            mock_upbit = MockUpbit.return_value
            mock_upbit.get_balances.return_value = []
            result = get_portfolio_tool.invoke("")
    assert isinstance(result, str)
    assert "100000" in result or "잔고" in result

def test_get_trade_history_tool_returns_string():
    from backend.ai.agent_tools import get_trade_history_tool
    with patch("backend.ai.agent_tools.get_db_conn") as mock_conn_fn:
        mock_conn = MagicMock()
        mock_conn_fn.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cur.fetchall.return_value = []
        result = get_trade_history_tool.invoke("7")
    assert isinstance(result, str)

def test_get_market_signal_tool_returns_string():
    from backend.ai.agent_tools import get_market_signal_tool
    with patch("backend.ai.agent_tools.pyupbit.get_current_price") as mock_price:
        mock_price.return_value = 90000000
        with patch("backend.ai.agent_tools.get_db_conn") as mock_conn_fn:
            mock_conn = MagicMock()
            mock_conn_fn.return_value = mock_conn
            mock_cur = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            mock_cur.fetchone.return_value = None
            result = get_market_signal_tool.invoke("KRW-BTC")
    assert isinstance(result, str)
    assert "BTC" in result or "90000000" in result
