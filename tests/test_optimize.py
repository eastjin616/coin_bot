from backtesting import optimize


def test_optimize_risk_searches_take_profit_axis(monkeypatch):
    monkeypatch.setattr(optimize, "TAKE_PROFIT_RANGE", [0.0, 4.0])
    monkeypatch.setattr(optimize, "TRAILING_ACTIVATION_RANGE", [2.5])
    monkeypatch.setattr(optimize, "STOP_LOSS_RANGE", [5])

    class DummyDf:
        empty = False

    def fake_evaluate_params(_df, params, *, symbol=None):
        return {
            "total_return_pct": params.take_profit,
            "win_rate": 50.0,
            "mdd": -1.0,
            "num_trades": 3,
        }

    monkeypatch.setattr(optimize, "evaluate_params", fake_evaluate_params)

    results = optimize.optimize_risk("KRW-LINK", DummyDf(), base_rsi=(40, 70))

    assert results[0]["take_profit_percent"] == 4.0
    assert results[0]["return_pct"] == 4.0


def test_optimize_full_searches_rsi_and_take_profit_axes_together(monkeypatch):
    monkeypatch.setattr(optimize, "RSI_BUY_RANGE", [30, 40])
    monkeypatch.setattr(optimize, "RSI_SELL_RANGE", [55, 70])
    monkeypatch.setattr(optimize, "TAKE_PROFIT_RANGE", [0.0, 4.0])
    monkeypatch.setattr(optimize, "TRAILING_ACTIVATION_RANGE", [2.5])
    monkeypatch.setattr(optimize, "STOP_LOSS_RANGE", [5])

    class DummyDf:
        empty = False

    def fake_evaluate_params(_df, params, *, symbol=None):
        bonus = 100.0 if (params.rsi_buy, params.rsi_sell, params.take_profit) == (40, 70, 4.0) else 0.0
        return {
            "total_return_pct": bonus + params.take_profit,
            "win_rate": 50.0,
            "mdd": -1.0,
            "num_trades": 3,
        }

    monkeypatch.setattr(optimize, "evaluate_params", fake_evaluate_params)

    result = optimize.optimize_full("KRW-LINK", DummyDf())

    assert result["rsi_buy"] == 40
    assert result["rsi_sell"] == 70
    assert result["take_profit_percent"] == 4.0
