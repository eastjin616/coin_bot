"""실운영 트레일링 스탑과 백테스터 정합성 테스트"""
import pandas as pd
from unittest.mock import patch

from backtesting.optimize import summarize_walk_forward
from backtesting.simulator import run_backtest


def make_df(closes, rsi_values):
    index = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "close": closes,
            "rsi": rsi_values,
            "ma_fast": closes,
            "ma_slow": closes,
        },
        index=index,
    )


def test_trailing_stop_exits_after_activation_and_pullback():
    df = make_df([100, 95, 110, 104], [50, 30, 50, 50])
    with patch("backtesting.simulator.add_indicators", return_value=df):
        result = run_backtest(
            df,
            rsi_buy=40,
            rsi_sell=90,
            stop_loss=5,
            use_trailing_stop=True,
        )

    sells = [trade for trade in result["trades"] if trade["type"] == "SELL"]
    assert len(sells) == 1
    assert sells[0]["reason"] == "트레일링"


def test_fixed_take_profit_mode_keeps_legacy_behavior():
    df = make_df([100, 95, 110, 104], [50, 30, 50, 50])
    with patch("backtesting.simulator.add_indicators", return_value=df):
        result = run_backtest(
            df,
            rsi_buy=40,
            rsi_sell=90,
            take_profit=10,
            stop_loss=5,
            use_trailing_stop=False,
        )

    sells = [trade for trade in result["trades"] if trade["type"] == "SELL"]
    assert len(sells) == 1
    assert sells[0]["reason"] == "익절"


def test_fee_and_slippage_reduce_performance():
    df = make_df([100, 95, 120, 120], [50, 30, 50, 50])
    with patch("backtesting.simulator.add_indicators", return_value=df):
        no_cost = run_backtest(
            df,
            rsi_buy=40,
            rsi_sell=90,
            stop_loss=5,
            trailing_activation_percent=2.5,
            use_trailing_stop=True,
            fee_rate=0.0,
            slippage_rate=0.0,
        )
        with_cost = run_backtest(
            df,
            rsi_buy=40,
            rsi_sell=90,
            stop_loss=5,
            trailing_activation_percent=2.5,
            use_trailing_stop=True,
            fee_rate=0.0005,
            slippage_rate=0.0005,
        )

    assert with_cost["total_return_pct"] < no_cost["total_return_pct"]


def test_walk_forward_summary_counts_positive_windows():
    summary = summarize_walk_forward([
        {"test_return_pct": 3.0},
        {"test_return_pct": -1.0},
        {"test_return_pct": 2.0},
    ])

    assert summary["windows"] == 3
    assert summary["win_windows"] == 2
    assert summary["avg_test_return_pct"] == 1.33
