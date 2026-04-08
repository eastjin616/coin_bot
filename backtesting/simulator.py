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
    trailing_activation_percent: float | None = None,
    use_trailing_stop: bool = False,
    fee_rate: float = 0.0005,
    slippage_rate: float = 0.0005,
) -> dict:
    """
    RSI 전략 백테스팅.
    반환: {total_return_pct, win_rate, mdd, num_trades, final_value, trades}
    미청산 포지션은 마지막 봉 종가로 청산 가정.
    """
    df = add_indicators(df, ma_fast=ma_fast, ma_slow=ma_slow)
    if df.empty:
        return {
            "total_return_pct": 0.0,
            "win_rate": 0.0,
            "mdd": 0.0,
            "num_trades": 0,
            "final_value": 100000.0,
            "trades": [],
        }

    cash = 100000.0
    position = 0.0
    entry_price = 0.0
    highest_price = 0.0
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
        death = row["ma_fast"] < row["ma_slow"]
        trailing_activation = trailing_activation_percent if trailing_activation_percent is not None else stop_loss / 2

        # 손절 / 트레일링 스탑 / 고정 익절
        if position > 0 and entry_price > 0:
            if price > highest_price:
                highest_price = price

            sell_price = price * (1 - slippage_rate)
            net_sell_price = sell_price * (1 - fee_rate)
            change_pct = (net_sell_price - entry_price) / entry_price * 100
            activation_threshold = entry_price * (1 + trailing_activation / 100)
            trailing_trigger = highest_price * (1 - stop_loss / 100) if highest_price > 0 else 0.0

            stop_reason = None
            if change_pct <= -stop_loss:
                stop_reason = "손절"
            elif use_trailing_stop and highest_price >= activation_threshold and price <= trailing_trigger:
                stop_reason = "트레일링"
            elif not use_trailing_stop and change_pct >= take_profit:
                stop_reason = "익절"

            if stop_reason:
                cash += position * net_sell_price
                trades.append({
                    "type": "SELL", "price": net_sell_price, "ts": ts,
                    "reason": stop_reason,
                    "pnl_pct": change_pct,
                })
                position = 0.0
                entry_price = 0.0
                highest_price = 0.0
                update_mdd(cash, position, price)
                continue

        # 매수 (일봉 전략: RSI만 사용)
        if position == 0 and rsi < rsi_buy and cash >= order_amount:
            buy_price = price * (1 + slippage_rate)
            qty = (order_amount * (1 - fee_rate)) / buy_price
            cash -= order_amount
            position += qty
            entry_price = buy_price
            highest_price = price
            trades.append({"type": "BUY", "price": buy_price, "ts": ts, "reason": "RSI"})

        # 매도
        elif position > 0 and (rsi > rsi_sell or death):
            sell_price = price * (1 - slippage_rate)
            net_sell_price = sell_price * (1 - fee_rate)
            pnl_pct = (net_sell_price - entry_price) / entry_price * 100
            cash += position * net_sell_price
            trades.append({
                "type": "SELL", "price": net_sell_price, "ts": ts,
                "reason": "RSI/MA", "pnl_pct": pnl_pct,
            })
            position = 0.0
            entry_price = 0.0
            highest_price = 0.0

        update_mdd(cash, position, price)

    liquidation_price = df["close"].iloc[-1] * (1 - slippage_rate) * (1 - fee_rate)
    final_value = cash + position * liquidation_price
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
