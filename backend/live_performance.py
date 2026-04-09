import logging
from datetime import UTC, datetime

from backend.config import get_settings
from backend.database import get_db

logger = logging.getLogger(__name__)


def recent_symbol_performance() -> dict[str, dict]:
    """Recent realized performance by symbol from SELL trades."""
    settings = get_settings()
    lookback_days = int(getattr(settings, "live_derating_lookback_days", 30) or 30)

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT
                    symbol,
                    COUNT(*) FILTER (WHERE action = 'SELL') AS sell_count,
                    COUNT(*) FILTER (WHERE action = 'SELL' AND pnl_pct > 0) AS win_count,
                    COALESCE(SUM(pnl_krw) FILTER (WHERE action = 'SELL'), 0) AS realized_pnl_krw,
                    COALESCE(AVG(pnl_pct) FILTER (WHERE action = 'SELL'), 0) AS avg_pnl_pct
                FROM trades
                WHERE market = 'coin' AND executed_at >= NOW() - INTERVAL '{lookback_days} days'
                GROUP BY symbol
                """
            )
            rows = cur.fetchall()
    except Exception as exc:
        logger.warning("최근 종목 성과 조회 실패: %s", exc)
        return {}

    out: dict[str, dict] = {}
    for row in rows:
        sell_count = int(row["sell_count"] or 0)
        win_count = int(row["win_count"] or 0)
        out[row["symbol"]] = {
            "sell_count": sell_count,
            "win_count": win_count,
            "win_rate": round((win_count / sell_count * 100) if sell_count else 0.0, 1),
            "realized_pnl_krw": round(float(row["realized_pnl_krw"] or 0.0), 2),
            "avg_pnl_pct": round(float(row["avg_pnl_pct"] or 0.0), 2),
        }
    return out


def get_live_derated_symbols() -> dict[str, str]:
    """Symbols temporarily blocked for new buys due to weak recent live performance."""
    settings = get_settings()
    if not getattr(settings, "live_derating_enabled", True):
        return {}

    perf = recent_symbol_performance()
    min_sell_count = int(getattr(settings, "live_derating_min_sell_count", 3) or 3)
    min_win_rate = float(getattr(settings, "live_derating_min_win_rate_pct", 40.0) or 40.0)
    min_avg_pnl_pct = float(getattr(settings, "live_derating_min_avg_pnl_pct", -0.5) or -0.5)

    derated: dict[str, str] = {}
    for symbol, row in perf.items():
        if row["sell_count"] < min_sell_count:
            continue
        if row["realized_pnl_krw"] >= 0:
            continue
        if row["win_rate"] >= min_win_rate and row["avg_pnl_pct"] >= min_avg_pnl_pct:
            continue
        derated[symbol] = (
            f"recent live underperformance: pnl {row['realized_pnl_krw']:+,.0f} KRW, "
            f"win_rate {row['win_rate']:.1f}%, avg_pnl {row['avg_pnl_pct']:+.2f}%"
        )
    return derated


def live_score_adjustments() -> dict[str, float]:
    """Score adjustments derived from recent realized live performance.

    Positive recent live performance slightly boosts priority.
    Negative recent live performance penalizes priority even before full derating.
    """
    settings = get_settings()
    perf = recent_symbol_performance()
    min_sell_count = int(getattr(settings, "live_derating_min_sell_count", 3) or 3)

    adjustments: dict[str, float] = {}
    for symbol, row in perf.items():
        if row["sell_count"] < min_sell_count:
            adjustments[symbol] = 0.0
            continue

        pnl_component = max(min(row["avg_pnl_pct"], 5.0), -5.0) * 0.8
        win_component = (row["win_rate"] - 50.0) * 0.08
        realized_component = max(min(row["realized_pnl_krw"] / 10000.0, 3.0), -3.0)
        adjustments[symbol] = round(pnl_component + win_component + realized_component, 3)

    return adjustments


def recent_loss_streaks() -> dict[str, dict]:
    """Consecutive losing SELL streak by symbol, newest-first."""
    settings = get_settings()
    lookback_days = int(getattr(settings, "loss_streak_lookback_days", 30) or 30)

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT symbol, executed_at, pnl_pct
                FROM trades
                WHERE market = 'coin'
                  AND action = 'SELL'
                  AND executed_at >= NOW() - INTERVAL '{lookback_days} days'
                ORDER BY symbol, executed_at DESC
                """
            )
            rows = cur.fetchall()
    except Exception as exc:
        logger.warning("최근 loss streak 조회 실패: %s", exc)
        return {}

    out: dict[str, dict] = {}
    for row in rows:
        symbol = row["symbol"]
        if symbol in out and out[symbol].get("closed"):
            continue

        entry = out.setdefault(symbol, {"loss_streak": 0, "last_sell_at": row["executed_at"], "closed": False})
        pnl_pct = float(row["pnl_pct"] or 0.0)
        if pnl_pct < 0:
            entry["loss_streak"] += 1
        else:
            entry["closed"] = True

    for value in out.values():
        value.pop("closed", None)
    return out


def get_loss_streak_cooldown_symbols(now: datetime | None = None) -> dict[str, str]:
    """Symbols temporarily blocked after repeated recent losing exits."""
    settings = get_settings()
    if not getattr(settings, "loss_streak_cooldown_enabled", True):
        return {}

    now = now or datetime.now(UTC)
    threshold = int(getattr(settings, "loss_streak_threshold", 2) or 2)
    cooldown_days = int(getattr(settings, "loss_streak_cooldown_days", 7) or 7)

    cooled: dict[str, str] = {}
    for symbol, row in recent_loss_streaks().items():
        streak = int(row.get("loss_streak") or 0)
        last_sell_at = row.get("last_sell_at")
        if streak < threshold or not last_sell_at:
            continue

        last_sell_at = last_sell_at.replace(tzinfo=UTC) if getattr(last_sell_at, "tzinfo", None) is None else last_sell_at.astimezone(UTC)
        days_since = (now - last_sell_at).total_seconds() / 86400
        if days_since >= cooldown_days:
            continue

        remaining_days = max(cooldown_days - int(days_since), 1)
        cooled[symbol] = (
            f"loss-streak cooldown: {streak} losses in a row, "
            f"{remaining_days}d remaining"
        )
    return cooled
