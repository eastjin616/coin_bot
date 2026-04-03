import pandas as pd
from backtesting.indicators import add_indicators


def run_backtest(
    df: pd.DataFrame,
    rsi_buy: float = 40.0,
    rsi_sell: float = 60.0,
    ma_fast: int = 5,
    ma_slow: int = 20,
    order_amount: int = 10000,
    take_profit: float = 10.0,
    stop_loss: float = 5.0,
) -> dict:
    """
    RSI + MA 크로스 전략 백테스팅.
    반환: {total_return_pct, win_rate, mdd, num_trades, final_value, trades}
    미청산 포지션은 마지막 봉 종가로 청산 가정.
    """
    df = add_indicators(df, ma_fast=ma_fast, ma_slow=ma_slow)
    cash = 100000.0
    position = 0.0
    entry_price = 0.0
    trades = []
    peak_value = cash
    min_drawdown = 0.0

    def update_mdd(cur_cash: float, cur_pos: float, cur_price: float):
        nonlocal peak_value, min_drawdown
        value = cur_cash + cur_pos * cur_price
        if value > peak_value:
            peak_value = value
        dd = (value - peak_value) / peak_value * 100
        if dd < min_drawdown:
            min_drawdown = dd

    for ts, row in df.iterrows():
        price = row["close"]
        rsi = row["rsi"]
        golden = row["ma_fast"] > row["ma_slow"]
        death = row["ma_fast"] < row["ma_slow"]

        # 익절/손절
        if position > 0 and entry_price > 0:
            change_pct = (price - entry_price) / entry_price * 100
            if change_pct >= take_profit or change_pct <= -stop_loss:
                cash += position * price
                trades.append({
                    "type": "SELL", "price": price, "ts": ts,
                    "reason": "익절" if change_pct >= take_profit else "손절",
                    "pnl_pct": change_pct,
                })
                position = 0.0
                entry_price = 0.0
                update_mdd(cash, position, price)
                continue

        # 매수
        if position == 0 and rsi < rsi_buy and golden and cash >= order_amount:
            qty = order_amount / price
            cash -= order_amount
            position += qty
            entry_price = price
            trades.append({"type": "BUY", "price": price, "ts": ts, "reason": "RSI+MA"})

        # 매도
        elif position > 0 and (rsi > rsi_sell or death):
            pnl_pct = (price - entry_price) / entry_price * 100
            cash += position * price
            trades.append({
                "type": "SELL", "price": price, "ts": ts,
                "reason": "RSI/MA", "pnl_pct": pnl_pct,
            })
            position = 0.0
            entry_price = 0.0

        update_mdd(cash, position, price)

    final_value = cash + position * df["close"].iloc[-1]
    total_return = (final_value - 100000) / 100000 * 100

    sell_trades = [t for t in trades if t["type"] == "SELL" and "pnl_pct" in t]
    win_rate = (
        len([t for t in sell_trades if t["pnl_pct"] > 0]) / len(sell_trades) * 100
        if sell_trades else 0
    )

    return {
        "total_return_pct": total_return,
        "win_rate": win_rate,
        "mdd": min_drawdown,
        "num_trades": len(sell_trades),
        "final_value": final_value,
        "trades": trades,
    }
