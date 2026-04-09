import logging

from backend.database import get_db
from backend.ai.chart_generator import get_coin_signal_indicators
from backend.config import get_settings
from backend.live_performance import recent_symbol_performance
from backend.runtime_params import get_active_buy_symbols, runtime_selection_meta

logger = logging.getLogger(__name__)


def count_bearish_signals(indicators: dict) -> int:
    rsi = indicators.get("rsi", 50)
    ma5 = indicators.get("ma5", 0)
    ma20 = indicators.get("ma20", 0)
    current_price = indicators.get("current_price", 0)

    signals = 0
    if rsi < 45:
        signals += 1
    if ma5 and ma20 and ma5 < ma20:
        signals += 1
    if current_price and ma20 and current_price < ma20:
        signals += 1
    return signals


def get_market_regime(indicators: dict) -> str:
    bearish_signals = count_bearish_signals(indicators)
    if bearish_signals >= 2:
        return "risk_off"
    if bearish_signals == 1:
        return "caution"
    return "risk_on"


def is_risk_off_market(indicators: dict) -> bool:
    return get_market_regime(indicators) == "risk_off"


def get_order_size_ratio_for_regime(regime: str) -> float:
    settings = get_settings()
    if regime == "risk_off":
        return settings.risk_off_order_size_ratio
    if regime == "caution":
        return settings.caution_order_size_ratio
    return settings.risk_on_order_size_ratio


def get_runtime_status() -> dict:
    btc_indicators = {}
    regime = "risk_on"
    try:
        btc_indicators = get_coin_signal_indicators("KRW-BTC")
        regime = get_market_regime(btc_indicators)
    except Exception as exc:
        logger.error(f"BTC runtime 상태 조회 실패: {exc}")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(SUM(pnl_krw), 0) AS realized_pnl_krw,
                COUNT(*) FILTER (WHERE action = 'SELL') AS sell_count,
                COUNT(*) FILTER (WHERE action = 'SELL' AND pnl_pct > 0) AS win_count
            FROM trades
            WHERE market = 'coin' AND executed_at >= NOW() - INTERVAL '30 days'
            """
        )
        perf_row = cur.fetchone()

        cur.execute(
            """
            SELECT symbol
            FROM watchlist
            WHERE market = 'coin' AND active = TRUE
            ORDER BY symbol
            """
        )
        watchlist_symbols = [row["symbol"] for row in cur.fetchall()]

    sell_count = int(perf_row["sell_count"] or 0)
    win_count = int(perf_row["win_count"] or 0)
    run_meta = runtime_selection_meta()
    selection = [
        {
            "symbol": symbol,
            "name": meta["name"],
            "enabled": meta["enabled"],
            "base_enabled": meta.get("base_enabled", meta["enabled"]),
            "live_derated": meta.get("live_derated", False),
            "loss_streak_cooled": meta.get("loss_streak_cooled", False),
            "reason": meta["reason"],
            "realistic_return_pct": meta["realistic_return_pct"],
            "recent_oos_pct": meta["recent_oos_pct"],
            "selection_score": meta.get("selection_score"),
            "live_score_adjustment": meta.get("live_score_adjustment"),
            "effective_selection_score": meta.get("effective_selection_score"),
        }
        for symbol, meta in sorted(run_meta.items())
    ]
    active = get_active_buy_symbols()
    signal_candle_time = btc_indicators.get("signal_candle_time")
    live_perf = recent_symbol_performance()
    live_derated_symbols = {
        symbol: meta["reason"]
        for symbol, meta in run_meta.items()
        if meta.get("live_derated")
    }
    loss_streak_cooled_symbols = {
        symbol: meta["reason"]
        for symbol, meta in run_meta.items()
        if meta.get("loss_streak_cooled")
    }
    return {
        "regime": regime,
        "risk_off": regime == "risk_off",
        "signal_basis": "previous_closed_day",
        "suggested_order_size_ratio": get_order_size_ratio_for_regime(regime),
        "btc": {
            "rsi": round(float(btc_indicators.get("rsi", 0) or 0), 2),
            "ma5": round(float(btc_indicators.get("ma5", 0) or 0), 2),
            "ma20": round(float(btc_indicators.get("ma20", 0) or 0), 2),
            "current_price": round(float(btc_indicators.get("current_price", 0) or 0), 2),
            "signal_candle_time": signal_candle_time.isoformat() if signal_candle_time else None,
        },
        "buy_enabled_symbols": list(active.keys()),
        "buy_blocked_symbols": [symbol for symbol, meta in run_meta.items() if not meta["enabled"]],
        "selection": selection,
        "active_watchlist_symbols": watchlist_symbols,
        "live_derated_symbols": live_derated_symbols,
        "loss_streak_cooled_symbols": loss_streak_cooled_symbols,
        "recent_symbol_performance": live_perf,
        "recent_30d": {
            "realized_pnl_krw": round(float(perf_row["realized_pnl_krw"] or 0), 2),
            "sell_count": sell_count,
            "win_count": win_count,
            "win_rate": round((win_count / sell_count * 100) if sell_count else 0.0, 1),
        },
    }
