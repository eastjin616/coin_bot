from backtesting.optimize import run_research


def recommend_runtime_universe() -> list[dict]:
    full_results, walk_summaries, recent_oos_results = run_research([
        "KRW-BTC", "KRW-SOL", "KRW-DOGE", "KRW-DOT", "KRW-ADA",
        "KRW-AVAX", "KRW-LINK", "KRW-TRX", "KRW-SUI", "KRW-HBAR",
        "KRW-ICP", "KRW-ATOM", "KRW-UNI", "KRW-SHIB", "KRW-BCH",
    ])

    walk_map = {item["symbol"]: item for item in walk_summaries}
    oos_map = {item["symbol"]: item for item in recent_oos_results}

    recommendations = []
    for result in full_results:
        symbol = result["symbol"]
        walk = walk_map.get(symbol, {})
        oos = oos_map.get(symbol, {})
        realistic = result["return_pct"]
        recent_oos = oos.get("return_pct")
        avg_oos = walk.get("avg_test_return_pct", 0.0)
        enabled = realistic > 0 and (recent_oos is None or recent_oos > -3.0) and avg_oos >= -1.0
        recommendations.append({
            "symbol": symbol,
            "enabled": enabled,
            "realistic_return_pct": realistic,
            "avg_walk_forward_oos_pct": avg_oos,
            "recent_oos_pct": recent_oos,
            "reason": (
                "현실화 수익 양수 + 최근 OOS 방어"
                if enabled else
                "현실화 수익 또는 OOS 방어 기준 미달"
            ),
        })
    return recommendations


if __name__ == "__main__":
    recommendations = recommend_runtime_universe()
    print("RUNTIME_SELECTION 후보:")
    for item in recommendations:
        print(
            f"{item['symbol']}: enabled={item['enabled']} | "
            f"realistic={item['realistic_return_pct']:+.1f}% | "
            f"walk_oos={item['avg_walk_forward_oos_pct']:+.1f}% | "
            f"recent_oos={item['recent_oos_pct'] if item['recent_oos_pct'] is not None else 'n/a'}"
        )
