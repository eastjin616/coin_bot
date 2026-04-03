import itertools
from backtesting.data_fetcher import fetch_ohlcv
from backtesting.simulator import run_backtest

SYMBOLS = ["KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-DOGE"]
RSI_BUY_RANGE = [35, 40, 45, 50]
RSI_SELL_RANGE = [55, 60, 65, 70]
DATA_DAYS = 3000  # 일봉 최대치 (~8년)
INTERVAL = "day"


def optimize(symbol: str) -> list[dict]:
    print(f"\n📊 {symbol} 데이터 로딩 중...")
    df = fetch_ohlcv(symbol, interval=INTERVAL, count=DATA_DAYS)
    if df.empty:
        print(f"  데이터 없음: {symbol}")
        return []

    results = []
    for rsi_buy, rsi_sell in itertools.product(RSI_BUY_RANGE, RSI_SELL_RANGE):
        if rsi_buy >= rsi_sell:
            continue
        result = run_backtest(df, rsi_buy=rsi_buy, rsi_sell=rsi_sell)
        results.append({
            "symbol": symbol,
            "rsi_buy": rsi_buy,
            "rsi_sell": rsi_sell,
            "return_pct": round(result["total_return_pct"], 2),
            "win_rate": round(result["win_rate"], 1),
            "mdd": round(result["mdd"], 1),
            "num_trades": result["num_trades"],
        })

    return sorted(results, key=lambda x: x["return_pct"], reverse=True)


def print_report(all_results: list[dict]):
    print("\n" + "=" * 72)
    print("📈 백테스팅 결과 리포트 (일봉 ~8년치)")
    print("=" * 72)

    best_by_symbol: dict[str, dict] = {}
    for r in all_results:
        sym = r["symbol"]
        if sym not in best_by_symbol or r["return_pct"] > best_by_symbol[sym]["return_pct"]:
            best_by_symbol[sym] = r

    print(f"\n{'코인':<12} {'RSI매수':<8} {'RSI매도':<8} {'수익률':<10} {'승률':<8} {'MDD':<8} {'거래수'}")
    print("-" * 72)
    for sym, r in best_by_symbol.items():
        emoji = "✅" if r["return_pct"] > 0 else "❌"
        print(
            f"{emoji} {sym[4:]:<10} {r['rsi_buy']:<8} {r['rsi_sell']:<8} "
            f"{r['return_pct']:>+6.1f}%   {r['win_rate']:>5.1f}%   "
            f"{r['mdd']:>5.1f}%   {r['num_trades']}"
        )

    if all_results:
        best = sorted(all_results, key=lambda x: x["return_pct"], reverse=True)[0]
        print(f"\n🏆 최적 파라미터: RSI 매수 {best['rsi_buy']} / 매도 {best['rsi_sell']}")
        print(f"   ({best['symbol'][4:]} 기준, 수익률 {best['return_pct']:+.1f}%, MDD {best['mdd']:.1f}%)")
        print(f"\n→ config.py에 반영: rsi_buy_threshold={best['rsi_buy']}, rsi_sell_threshold={best['rsi_sell']}")


if __name__ == "__main__":
    all_results = []
    for sym in SYMBOLS:
        results = optimize(sym)
        all_results.extend(results)
        if results:
            print(f"  최고: RSI {results[0]['rsi_buy']}/{results[0]['rsi_sell']} → {results[0]['return_pct']:+.1f}%")

    print_report(all_results)
