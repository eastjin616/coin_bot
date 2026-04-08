import logging

from backend.database import get_db
from backend.ai.chart_generator import get_coin_indicators
from backend.config import get_settings

logger = logging.getLogger(__name__)

RUNTIME_SELECTION: dict[str, dict] = {
    "KRW-BTC": {"name": "비트코인", "enabled": True, "reason": "시장 기준 자산으로 유지", "realistic_return_pct": -10.1, "recent_oos_pct": -3.5},
    "KRW-SOL": {"name": "솔라나", "enabled": True, "reason": "장기 현실화 수익 양수, 운영 유지", "realistic_return_pct": 2.6, "recent_oos_pct": -4.8},
    "KRW-DOGE": {"name": "도지코인", "enabled": True, "reason": "최근 OOS 방어력 상대 우수", "realistic_return_pct": 3.7, "recent_oos_pct": 0.1},
    "KRW-LINK": {"name": "체인링크", "enabled": True, "reason": "현실화 백테스트 최고 수익군", "realistic_return_pct": 21.2, "recent_oos_pct": -2.5},
    "KRW-HBAR": {"name": "헤데라", "enabled": True, "reason": "양수 기대수익 유지", "realistic_return_pct": 4.2, "recent_oos_pct": -0.8},
    "KRW-UNI": {"name": "유니스왑", "enabled": True, "reason": "양수 기대수익 유지", "realistic_return_pct": 5.3, "recent_oos_pct": None},
    "KRW-BCH": {"name": "비트코인캐시", "enabled": True, "reason": "양수 기대수익 및 walk-forward 방어 우수", "realistic_return_pct": 6.8, "recent_oos_pct": -1.0},
    "KRW-DOT": {"name": "폴카닷", "enabled": False, "reason": "장기 현실화 수익 음수", "realistic_return_pct": -4.7, "recent_oos_pct": 0.4},
    "KRW-ADA": {"name": "에이다", "enabled": False, "reason": "장기/최근 성능 모두 약세", "realistic_return_pct": -5.7, "recent_oos_pct": -4.4},
    "KRW-AVAX": {"name": "아발란체", "enabled": False, "reason": "장기 현실화 수익 음수", "realistic_return_pct": -3.4, "recent_oos_pct": -3.1},
    "KRW-TRX": {"name": "트론", "enabled": False, "reason": "기대수익이 거의 0에 수렴", "realistic_return_pct": -1.0, "recent_oos_pct": -0.8},
    "KRW-SUI": {"name": "수이", "enabled": False, "reason": "장기/최근 성능 모두 불안정", "realistic_return_pct": 0.0, "recent_oos_pct": -4.3},
    "KRW-ICP": {"name": "인터넷컴퓨터", "enabled": False, "reason": "표본 거래 수가 너무 적음", "realistic_return_pct": 0.2, "recent_oos_pct": None},
    "KRW-ATOM": {"name": "코스모스", "enabled": False, "reason": "장기 현실화 수익이 0 근처", "realistic_return_pct": -0.3, "recent_oos_pct": -2.6},
    "KRW-SHIB": {"name": "시바이누", "enabled": False, "reason": "최근 OOS와 장기 기대수익 모두 약세", "realistic_return_pct": -1.4, "recent_oos_pct": -2.0},
}

ACTIVE_BUY_SYMBOLS: dict[str, str] = {
    symbol: meta["name"] for symbol, meta in RUNTIME_SELECTION.items() if meta["enabled"]
}


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
        btc_indicators = get_coin_indicators("KRW-BTC")
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
    selection = [
        {
            "symbol": symbol,
            "name": meta["name"],
            "enabled": meta["enabled"],
            "reason": meta["reason"],
            "realistic_return_pct": meta["realistic_return_pct"],
            "recent_oos_pct": meta["recent_oos_pct"],
        }
        for symbol, meta in sorted(RUNTIME_SELECTION.items())
    ]
    return {
        "regime": regime,
        "risk_off": regime == "risk_off",
        "suggested_order_size_ratio": get_order_size_ratio_for_regime(regime),
        "btc": {
            "rsi": round(float(btc_indicators.get("rsi", 0) or 0), 2),
            "ma5": round(float(btc_indicators.get("ma5", 0) or 0), 2),
            "ma20": round(float(btc_indicators.get("ma20", 0) or 0), 2),
            "current_price": round(float(btc_indicators.get("current_price", 0) or 0), 2),
        },
        "buy_enabled_symbols": list(ACTIVE_BUY_SYMBOLS.keys()),
        "buy_blocked_symbols": [symbol for symbol, meta in RUNTIME_SELECTION.items() if not meta["enabled"]],
        "selection": selection,
        "active_watchlist_symbols": watchlist_symbols,
        "recent_30d": {
            "realized_pnl_krw": round(float(perf_row["realized_pnl_krw"] or 0), 2),
            "sell_count": sell_count,
            "win_count": win_count,
            "win_rate": round((win_count / sell_count * 100) if sell_count else 0.0, 1),
        },
    }
