import itertools
from dataclasses import dataclass

import pandas as pd

from backtesting.data_fetcher import fetch_ohlcv
from backtesting.simulator import run_backtest

SYMBOLS = [
    "KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-DOGE",
    "KRW-DOT", "KRW-ADA", "KRW-AVAX", "KRW-LINK", "KRW-TRX",
    "KRW-SUI", "KRW-NEAR", "KRW-HBAR", "KRW-ICP", "KRW-OP",
    "KRW-ATOM", "KRW-UNI", "KRW-SHIB", "KRW-LTC", "KRW-BCH",
]

ACTIVE_RUNTIME_SYMBOLS = [
    "KRW-BTC", "KRW-SOL", "KRW-DOGE", "KRW-DOT", "KRW-ADA",
    "KRW-AVAX", "KRW-LINK", "KRW-TRX", "KRW-SUI", "KRW-HBAR",
    "KRW-ICP", "KRW-ATOM", "KRW-UNI", "KRW-SHIB", "KRW-BCH",
]

RSI_BUY_RANGE = [30, 35, 40, 45, 50]
RSI_SELL_RANGE = [55, 60, 65, 70]
TRAILING_ACTIVATION_RANGE = [1.5, 2.5, 3.5, 5.0]
STOP_LOSS_RANGE = [3, 5, 7, 10]
DATA_DAYS = 3000
INTERVAL = "day"

FEE_RATE = 0.0005
SLIPPAGE_RATE = 0.0005

TRAIN_DAYS = 720
TEST_DAYS = 180
STEP_DAYS = 180
RECENT_OOS_DAYS = 180


@dataclass(frozen=True)
class StrategyParams:
    rsi_buy: int
    rsi_sell: int
    trailing_activation_percent: float
    stop_loss: int


def load_symbol_data(symbol: str, *, cache_only: bool = True) -> pd.DataFrame:
    print(f"\n📊 {symbol} 데이터 로딩 중...")
    return fetch_ohlcv(symbol, interval=INTERVAL, count=DATA_DAYS, cache_only=cache_only)


def score_result(result: dict) -> tuple[float, float, float]:
    return (result["total_return_pct"], result["win_rate"], result["mdd"])


def evaluate_params(df: pd.DataFrame, params: StrategyParams) -> dict:
    return run_backtest(
        df,
        rsi_buy=params.rsi_buy,
        rsi_sell=params.rsi_sell,
        stop_loss=params.stop_loss,
        trailing_activation_percent=params.trailing_activation_percent,
        use_trailing_stop=True,
        fee_rate=FEE_RATE,
        slippage_rate=SLIPPAGE_RATE,
    )


def optimize_rsi(symbol: str, df: pd.DataFrame) -> list[dict]:
    if df.empty:
        print(f"  데이터 없음: {symbol}")
        return []

    results = []
    for rsi_buy, rsi_sell in itertools.product(RSI_BUY_RANGE, RSI_SELL_RANGE):
        if rsi_buy >= rsi_sell:
            continue
        params = StrategyParams(rsi_buy, rsi_sell, 2.5, 5)
        result = evaluate_params(df, params)
        results.append({
            "symbol": symbol,
            "rsi_buy": rsi_buy,
            "rsi_sell": rsi_sell,
            "return_pct": round(result["total_return_pct"], 2),
            "win_rate": round(result["win_rate"], 1),
            "mdd": round(result["mdd"], 1),
            "num_trades": result["num_trades"],
        })
    return sorted(results, key=lambda item: (item["return_pct"], item["win_rate"], item["mdd"]), reverse=True)


def optimize_risk(symbol: str, df: pd.DataFrame, base_rsi: tuple[int, int] | None = None) -> list[dict]:
    if df.empty:
        print(f"  데이터 없음: {symbol}")
        return []

    if base_rsi is None:
        rsi_results = optimize_rsi(symbol, df)
        if not rsi_results:
            return []
        base_rsi = (rsi_results[0]["rsi_buy"], rsi_results[0]["rsi_sell"])

    rsi_buy, rsi_sell = base_rsi
    results = []
    for trailing_activation, stop_loss in itertools.product(TRAILING_ACTIVATION_RANGE, STOP_LOSS_RANGE):
        params = StrategyParams(rsi_buy, rsi_sell, trailing_activation, stop_loss)
        result = evaluate_params(df, params)
        results.append({
            "symbol": symbol,
            "rsi_buy": rsi_buy,
            "rsi_sell": rsi_sell,
            "trailing_activation_percent": trailing_activation,
            "stop_loss": stop_loss,
            "return_pct": round(result["total_return_pct"], 2),
            "win_rate": round(result["win_rate"], 1),
            "mdd": round(result["mdd"], 1),
            "num_trades": result["num_trades"],
        })
    return sorted(results, key=lambda item: (item["return_pct"], item["win_rate"], item["mdd"]), reverse=True)


def optimize_full(symbol: str, df: pd.DataFrame) -> dict | None:
    if df.empty:
        return None

    rsi_results = optimize_rsi(symbol, df)
    if not rsi_results:
        return None

    best_rsi = (rsi_results[0]["rsi_buy"], rsi_results[0]["rsi_sell"])
    risk_results = optimize_risk(symbol, df, base_rsi=best_rsi)
    return risk_results[0] if risk_results else None


def walk_forward_validate(symbol: str, df: pd.DataFrame) -> list[dict]:
    if df.empty or len(df) < (TRAIN_DAYS + TEST_DAYS):
        return []

    windows = []
    start = 0
    while start + TRAIN_DAYS + TEST_DAYS <= len(df):
        train_df = df.iloc[start:start + TRAIN_DAYS].copy()
        test_df = df.iloc[start + TRAIN_DAYS:start + TRAIN_DAYS + TEST_DAYS].copy()
        best = optimize_full(symbol, train_df)
        if not best:
            start += STEP_DAYS
            continue

        params = StrategyParams(
            best["rsi_buy"],
            best["rsi_sell"],
            best["trailing_activation_percent"],
            best["stop_loss"],
        )
        train_result = evaluate_params(train_df, params)
        test_result = evaluate_params(test_df, params)
        windows.append({
            "symbol": symbol,
            "train_start": train_df.index[0].date().isoformat(),
            "train_end": train_df.index[-1].date().isoformat(),
            "test_start": test_df.index[0].date().isoformat(),
            "test_end": test_df.index[-1].date().isoformat(),
            "rsi_buy": params.rsi_buy,
            "rsi_sell": params.rsi_sell,
            "trailing_activation_percent": params.trailing_activation_percent,
            "stop_loss": params.stop_loss,
            "train_return_pct": round(train_result["total_return_pct"], 2),
            "test_return_pct": round(test_result["total_return_pct"], 2),
            "test_mdd": round(test_result["mdd"], 2),
            "test_num_trades": test_result["num_trades"],
        })
        start += STEP_DAYS
    return windows


def summarize_walk_forward(windows: list[dict]) -> dict:
    if not windows:
        return {"windows": 0, "avg_test_return_pct": 0.0, "win_windows": 0, "last_window": None}

    win_windows = len([window for window in windows if window["test_return_pct"] > 0])
    avg_test_return = sum(window["test_return_pct"] for window in windows) / len(windows)
    return {
        "windows": len(windows),
        "avg_test_return_pct": round(avg_test_return, 2),
        "win_windows": win_windows,
        "last_window": windows[-1],
    }


def recent_oos_check(symbol: str, df: pd.DataFrame) -> dict | None:
    if df.empty or len(df) < (TRAIN_DAYS + RECENT_OOS_DAYS):
        return None

    train_df = df.iloc[: len(df) - RECENT_OOS_DAYS].copy()
    test_df = df.iloc[len(df) - RECENT_OOS_DAYS :].copy()
    best = optimize_full(symbol, train_df)
    if not best:
        return None

    params = StrategyParams(
        best["rsi_buy"],
        best["rsi_sell"],
        best["trailing_activation_percent"],
        best["stop_loss"],
    )
    test_result = evaluate_params(test_df, params)
    return {
        "symbol": symbol,
        "test_start": test_df.index[0].date().isoformat(),
        "test_end": test_df.index[-1].date().isoformat(),
        "rsi_buy": params.rsi_buy,
        "rsi_sell": params.rsi_sell,
        "trailing_activation_percent": params.trailing_activation_percent,
        "stop_loss": params.stop_loss,
        "return_pct": round(test_result["total_return_pct"], 2),
        "win_rate": round(test_result["win_rate"], 1),
        "mdd": round(test_result["mdd"], 2),
        "num_trades": test_result["num_trades"],
    }


def print_full_report(results: list[dict]):
    print("\n" + "=" * 96)
    print(f"📈 현실화 백테스팅 리포트 (수수료 {FEE_RATE * 100:.02f}%, 슬리피지 {SLIPPAGE_RATE * 100:.02f}%)")
    print("=" * 96)
    print(f"\n{'코인':<12} {'RSI':<9} {'활성화%':<9} {'손절%':<8} {'수익률':<10} {'승률':<8} {'MDD':<8} {'거래수'}")
    print("-" * 96)
    for result in results:
        emoji = "✅" if result["return_pct"] > 0 else "❌"
        print(
            f"{emoji} {result['symbol'][4:]:<10} {result['rsi_buy']}/{result['rsi_sell']:<6} "
            f"+{result['trailing_activation_percent']:<8} -{result['stop_loss']:<7} "
            f"{result['return_pct']:>+6.1f}%   {result['win_rate']:>5.1f}%   "
            f"{result['mdd']:>5.1f}%   {result['num_trades']}"
        )


def print_runtime_overrides(results: list[dict]):
    print("\n📋 runtime `_PROFIT_STOP_OVERRIDES` 추천값:")
    print("_PROFIT_STOP_OVERRIDES: dict[str, tuple[float, float]] = {")
    for result in results:
        print(
            f'    "{result["symbol"]}": ({result["trailing_activation_percent"]}, {result["stop_loss"]}), '
            f'# return {result["return_pct"]:+.1f}%, RSI {result["rsi_buy"]}/{result["rsi_sell"]}'
        )
    print("}")


def print_walk_forward_report(summaries: list[dict]):
    print("\n" + "=" * 96)
    print("🧪 Walk-Forward 검증")
    print("=" * 96)
    print(f"\n{'코인':<12} {'윈도우수':<8} {'평균 OOS':<10} {'양수구간':<8} {'최근 OOS'}")
    print("-" * 96)
    for summary in summaries:
        last_window = summary["last_window"]
        last_return = f"{last_window['test_return_pct']:+.1f}%" if last_window else "n/a"
        print(
            f"{summary['symbol'][4:]:<12} {summary['windows']:<8} "
            f"{summary['avg_test_return_pct']:>+6.1f}%   {summary['win_windows']:<8} {last_return}"
        )


def print_recent_oos_report(results: list[dict]):
    print("\n" + "=" * 96)
    print(f"📆 최근 {RECENT_OOS_DAYS}일 OOS 성능")
    print("=" * 96)
    print(f"\n{'코인':<12} {'기간':<24} {'RSI':<9} {'활성화%':<9} {'손절%':<8} {'수익률':<10} {'MDD':<8}")
    print("-" * 96)
    for result in results:
        period = f"{result['test_start']}~{result['test_end']}"
        print(
            f"{result['symbol'][4:]:<12} {period:<24} {result['rsi_buy']}/{result['rsi_sell']:<6} "
            f"+{result['trailing_activation_percent']:<8} -{result['stop_loss']:<7} "
            f"{result['return_pct']:>+6.1f}%   {result['mdd']:>5.1f}%"
        )


def run_research(symbols: list[str], *, cache_only: bool = True) -> tuple[list[dict], list[dict], list[dict]]:
    full_results = []
    walk_summaries = []
    recent_oos_results = []

    for symbol in symbols:
        df = load_symbol_data(symbol, cache_only=cache_only)
        if df.empty:
            print(f"  데이터 없음: {symbol}")
            continue

        best = optimize_full(symbol, df)
        if best:
            full_results.append(best)

        windows = walk_forward_validate(symbol, df)
        walk_summary = summarize_walk_forward(windows)
        walk_summary["symbol"] = symbol
        walk_summaries.append(walk_summary)

        recent = recent_oos_check(symbol, df)
        if recent:
            recent_oos_results.append(recent)

    return full_results, walk_summaries, recent_oos_results


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "research"
    symbols = ACTIVE_RUNTIME_SYMBOLS

    if mode == "rsi":
        for symbol in symbols:
            df = load_symbol_data(symbol)
            results = optimize_rsi(symbol, df)
            if results:
                best = results[0]
                print(f"{symbol}: RSI {best['rsi_buy']}/{best['rsi_sell']} -> {best['return_pct']:+.1f}%")
    elif mode == "risk":
        for symbol in symbols:
            df = load_symbol_data(symbol)
            results = optimize_risk(symbol, df)
            if results:
                best = results[0]
                print(
                    f"{symbol}: 활성화 +{best['trailing_activation_percent']}% / "
                    f"손절 -{best['stop_loss']}% -> {best['return_pct']:+.1f}%"
                )
    else:
        full_results, walk_summaries, recent_oos_results = run_research(symbols)
        print_full_report(full_results)
        print_runtime_overrides(full_results)
        print_walk_forward_report(walk_summaries)
        print_recent_oos_report(recent_oos_results)
