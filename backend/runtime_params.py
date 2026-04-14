"""Single source of truth for runtime universe, RSI thresholds, and trailing-stop params.

Data file: `backend/runtime_params.json` (override path with env `RUNTIME_PARAMS_PATH`).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from backend.live_performance import get_live_derated_symbols, get_loss_streak_cooldown_symbols, live_score_adjustments

logger = logging.getLogger(__name__)

_REQUIRED_ROW_KEYS = (
    "name",
    "enabled",
    "reason",
    "realistic_return_pct",
    "rsi_buy",
    "rsi_sell",
    "take_profit_percent",
    "trailing_activation_percent",
    "stop_loss_percent",
)

_default_path = Path(__file__).resolve().parent / "runtime_params.json"
_table: dict[str, dict[str, Any]] | None = None
_table_mtime_ns: int | None = None


def _params_path() -> Path:
    override = os.environ.get("RUNTIME_PARAMS_PATH", "").strip()
    return Path(override) if override else _default_path


def _validate_table(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("runtime params must be a non-empty JSON object keyed by symbol")
    out: dict[str, dict[str, Any]] = {}
    for symbol, row in raw.items():
        if not symbol.startswith("KRW-"):
            raise ValueError(f"invalid symbol key: {symbol!r}")
        if not isinstance(row, dict):
            raise ValueError(f"{symbol}: row must be an object")
        for key in _REQUIRED_ROW_KEYS:
            if key not in row:
                raise ValueError(f"{symbol}: missing {key!r}")
        out[symbol] = row
    return out


def load_runtime_params(*, force: bool = False) -> dict[str, dict[str, Any]]:
    """Load and cache the symbol table. Call with force=True to reload from disk."""
    global _table, _table_mtime_ns
    path = _params_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"runtime params not found: {path} "
            "(set RUNTIME_PARAMS_PATH or restore backend/runtime_params.json)"
        )
    mtime_ns = path.stat().st_mtime_ns
    if _table is not None and not force and _table_mtime_ns == mtime_ns:
        return _table
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    _table = _validate_table(raw)
    _table_mtime_ns = mtime_ns
    logger.info("runtime params loaded (%d symbols) from %s", len(_table), path)
    return _table


def symbol_table() -> dict[str, dict[str, Any]]:
    return load_runtime_params()


def reload_runtime_params() -> dict[str, dict[str, Any]]:
    """Public reload (e.g. tests or hot-refresh after research merge)."""
    return load_runtime_params(force=True)


def _manual_override(row: dict[str, Any]) -> str | None:
    value = str(row.get("manual_override") or "").strip().lower()
    return value if value in {"enabled", "disabled"} else None


def _base_enabled(row: dict[str, Any]) -> bool:
    override = _manual_override(row)
    if override == "enabled":
        return True
    if override == "disabled":
        return False
    return bool(row["enabled"])


def get_base_active_buy_symbols() -> dict[str, str]:
    """symbol -> display name for symbols enabled by research/runtime_params.json."""
    return {s: row["name"] for s, row in symbol_table().items() if _base_enabled(row)}


def get_active_buy_symbols() -> dict[str, str]:
    """symbol -> display name for symbols enabled after live-performance derating."""
    active = get_base_active_buy_symbols()
    derated = get_live_derated_symbols()
    cooled = get_loss_streak_cooldown_symbols()
    return {
        symbol: name
        for symbol, name in active.items()
        if symbol not in derated and symbol not in cooled
    }


def runtime_tactical_score(row: dict[str, Any]) -> float:
    realistic = float(row.get("realistic_return_pct") or 0.0)
    avg_oos = float(row.get("avg_walk_forward_oos_pct") or 0.0)
    recent_oos = row.get("recent_oos_pct")
    recent_component = float(recent_oos) if recent_oos is not None else -3.0
    return round(
        realistic * 0.25
        + avg_oos * 2.2
        + recent_component * 3.0,
        3,
    )


def runtime_selection_meta() -> dict[str, dict[str, Any]]:
    """Subset of fields used by /api/runtime/status `selection` list."""
    derated = get_live_derated_symbols()
    streak_cooled = get_loss_streak_cooldown_symbols()
    live_adjustments = live_score_adjustments()
    sel: dict[str, dict[str, Any]] = {}
    for sym, row in symbol_table().items():
        base_enabled = _base_enabled(row)
        effective_enabled = base_enabled and sym not in derated and sym not in streak_cooled
        base_score = runtime_tactical_score(row)
        reason = f"runtime-tactical-score {base_score:+.1f}"
        snapshot_reason = str(row["reason"])
        if snapshot_reason:
            reason = f"{reason} | research-snapshot: {snapshot_reason}"
        override = _manual_override(row)
        if override:
            reason = f"{reason} | manual-override: {override}"
        if sym in derated:
            reason = f"{reason} | live-derated: {derated[sym]}"
        if sym in streak_cooled:
            reason = f"{reason} | streak-cooled: {streak_cooled[sym]}"
        live_adjustment = float(live_adjustments.get(sym) or 0.0)
        sel[sym] = {
            "name": row["name"],
            "enabled": effective_enabled,
            "base_enabled": base_enabled,
            "live_derated": sym in derated,
            "loss_streak_cooled": sym in streak_cooled,
            "manual_override": override,
            "reason": reason,
            "realistic_return_pct": row["realistic_return_pct"],
            "recent_oos_pct": row.get("recent_oos_pct"),
            "selection_score": base_score,
            "live_score_adjustment": live_adjustment,
            "effective_selection_score": round(base_score + live_adjustment, 3),
        }
    return sel


def rsi_pair(symbol: str, default_buy: float, default_sell: float) -> tuple[float, float]:
    row = symbol_table().get(symbol)
    if not row:
        return (default_buy, default_sell)
    return (float(row["rsi_buy"]), float(row["rsi_sell"]))


def trailing_stop_pair(
    symbol: str,
    default_activation: float,
    default_stop: float,
) -> tuple[float, float]:
    """Returns (trailing_activation_percent, stop_loss_percent)."""
    row = symbol_table().get(symbol)
    if not row:
        return (default_activation, default_stop)
    return (float(row["trailing_activation_percent"]), float(row["stop_loss_percent"]))


def take_profit_percent(symbol: str, default_take_profit: float) -> float:
    row = symbol_table().get(symbol)
    if not row:
        return default_take_profit
    return float(row["take_profit_percent"])


def normalize_runtime_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not symbol:
        raise ValueError("empty symbol")
    return symbol if symbol.startswith("KRW-") else f"KRW-{symbol}"


def set_symbol_manual_override(symbol: str, override: str | None, *, actor: str = "operator") -> dict[str, Any]:
    symbol = normalize_runtime_symbol(symbol)
    path = _params_path()
    with path.open(encoding="utf-8") as f:
        table = json.load(f)
    row = table.get(symbol)
    if not row:
        raise KeyError(symbol)

    if override is None:
        row.pop("manual_override", None)
        row.pop("manual_override_note", None)
    else:
        override = override.strip().lower()
        if override not in {"enabled", "disabled"}:
            raise ValueError(f"invalid manual override: {override}")
        row["manual_override"] = override
        row["manual_override_note"] = f"set via {actor}"

    with path.open("w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=2)
        f.write("\n")
    reload_runtime_params()
    return table[symbol]
