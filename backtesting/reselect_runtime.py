import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

from backtesting.optimize import run_research

_BACKEND_PARAMS = Path(__file__).resolve().parent.parent / "backend" / "runtime_params.json"
_REPORTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "reports"
DEFAULT_TOP_N = 3
MIN_REALISTIC_RETURN_PCT = -5.0
MIN_AVG_WALK_OOS_PCT = -1.0
MIN_RECENT_OOS_PCT = -6.0
MIN_WALK_WINDOWS = 3
DEFAULT_MAX_SYMBOL_CHANGES = 2


def selection_score(result: dict, walk: dict, oos: dict) -> float:
    """Composite score for short-term tactical runtime universe selection."""
    realistic = float(result.get("return_pct") or 0.0)
    avg_oos = float(walk.get("avg_test_return_pct") or 0.0)
    recent_oos = oos.get("return_pct")
    recent_component = float(recent_oos) if recent_oos is not None else -3.0
    windows = int(walk.get("windows") or 0)
    num_trades = int(result.get("num_trades") or 0)
    mdd = abs(float(result.get("mdd") or 0.0))

    trade_bonus = min(num_trades, 120) / 60.0
    window_bonus = min(windows, 12) * 0.2
    drawdown_penalty = max(mdd - 8.0, 0.0) * 0.5

    return round(
        realistic * 0.25
        + avg_oos * 2.2
        + recent_component * 3.0
        + trade_bonus
        + window_bonus
        - drawdown_penalty,
        3,
    )


def is_selection_candidate(result: dict, walk: dict, oos: dict) -> bool:
    realistic = float(result.get("return_pct") or 0.0)
    avg_oos = float(walk.get("avg_test_return_pct") or 0.0)
    recent_oos = oos.get("return_pct")
    windows = int(walk.get("windows") or 0)
    return (
        realistic > MIN_REALISTIC_RETURN_PCT
        and avg_oos >= MIN_AVG_WALK_OOS_PCT
        and (recent_oos is None or float(recent_oos) >= MIN_RECENT_OOS_PCT)
        and windows >= MIN_WALK_WINDOWS
    )


def recommend_runtime_universe(top_n: int = DEFAULT_TOP_N, *, cache_only: bool = True) -> list[dict]:
    full_results, walk_summaries, recent_oos_results = run_research([
        "KRW-BTC", "KRW-SOL", "KRW-DOGE", "KRW-DOT", "KRW-ADA",
        "KRW-AVAX", "KRW-LINK", "KRW-TRX", "KRW-SUI", "KRW-HBAR",
        "KRW-ICP", "KRW-ATOM", "KRW-UNI", "KRW-SHIB", "KRW-BCH",
    ], cache_only=cache_only)

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
        score = selection_score(result, walk, oos)
        recommendations.append({
            "symbol": symbol,
            "realistic_return_pct": realistic,
            "avg_walk_forward_oos_pct": avg_oos,
            "recent_oos_pct": recent_oos,
            "selection_score": score,
            "num_trades": result.get("num_trades", 0),
            "walk_windows": walk.get("windows", 0),
            "mdd": result.get("mdd", 0.0),
        })

    candidates = [item for item in recommendations if is_selection_candidate(
        {
            "return_pct": item["realistic_return_pct"],
            "num_trades": item["num_trades"],
            "mdd": item["mdd"],
        },
        {"avg_test_return_pct": item["avg_walk_forward_oos_pct"], "windows": item["walk_windows"]},
        {"return_pct": item["recent_oos_pct"]},
    )]
    selected_symbols = {
        item["symbol"]
        for item in sorted(candidates, key=lambda item: item["selection_score"], reverse=True)[:top_n]
    }

    for item in recommendations:
        item["enabled"] = item["symbol"] in selected_symbols
        if item["enabled"]:
            rank = (
                sorted(candidates, key=lambda row: row["selection_score"], reverse=True)
                .index(next(row for row in candidates if row["symbol"] == item["symbol"]))
                + 1
            )
            item["reason"] = f"점수 기반 상위 {top_n} 선발 #{rank} (score {item['selection_score']:+.1f})"
        else:
            item["reason"] = f"상위 {top_n} 밖 또는 최소 기준 미달 (score {item['selection_score']:+.1f})"

    recommendations.sort(key=lambda item: item["selection_score"], reverse=True)
    return recommendations


def merge_recommendations_into_params(path: Path, recommendations: list[dict]) -> None:
    """Update enabled/reason/OOS fields in backend/runtime_params.json; preserves RSI/take-profit/trailing columns."""
    with path.open(encoding="utf-8") as f:
        table = json.load(f)
    by_sym = {r["symbol"]: r for r in recommendations}
    for sym, row in table.items():
        rec = by_sym.get(sym)
        if not rec:
            continue
        row["enabled"] = rec["enabled"]
        row["reason"] = rec["reason"]
        row["realistic_return_pct"] = rec["realistic_return_pct"]
        row["avg_walk_forward_oos_pct"] = rec["avg_walk_forward_oos_pct"]
        row["recent_oos_pct"] = rec["recent_oos_pct"]
        row["selection_score"] = rec["selection_score"]
    with path.open("w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_enabled_symbols(path: Path) -> set[str]:
    with path.open(encoding="utf-8") as f:
        table = json.load(f)
    return {symbol for symbol, row in table.items() if row.get("enabled")}


def auto_apply_decision(
    current_enabled: set[str],
    recommendations: list[dict],
    *,
    top_n: int,
    max_symbol_changes: int = DEFAULT_MAX_SYMBOL_CHANGES,
) -> dict:
    proposed_enabled = {item["symbol"] for item in recommendations if item["enabled"]}
    added = sorted(proposed_enabled - current_enabled)
    removed = sorted(current_enabled - proposed_enabled)
    changed = len(added) + len(removed)

    reasons: list[str] = []
    if len(proposed_enabled) < top_n:
        reasons.append(f"enabled count {len(proposed_enabled)} < top_n {top_n}")
    if changed > max_symbol_changes:
        reasons.append(f"changed symbols {changed} > max {max_symbol_changes}")

    return {
        "applied": not reasons,
        "current_enabled": sorted(current_enabled),
        "proposed_enabled": sorted(proposed_enabled),
        "added": added,
        "removed": removed,
        "changed_count": changed,
        "reasons": reasons,
    }


def maybe_auto_apply_runtime_params(
    path: Path,
    recommendations: list[dict],
    *,
    top_n: int,
    max_symbol_changes: int = DEFAULT_MAX_SYMBOL_CHANGES,
) -> dict:
    current_enabled = load_enabled_symbols(path)
    decision = auto_apply_decision(
        current_enabled,
        recommendations,
        top_n=top_n,
        max_symbol_changes=max_symbol_changes,
    )
    if decision["applied"]:
        merge_recommendations_into_params(path, recommendations)
    return decision


def default_report_path(today: date | None = None) -> Path:
    today = today or date.today()
    return _REPORTS_DIR / f"{today.isoformat()}-runtime-universe.md"


def render_runtime_report(recommendations: list[dict], top_n: int, *, auto_apply_summary: dict | None = None) -> str:
    enabled = [item for item in recommendations if item["enabled"]]
    blocked = [item for item in recommendations if not item["enabled"]]

    lines = [
        f"# Runtime Universe Report ({date.today().isoformat()})",
        "",
        f"Top-N setting: `{top_n}`",
        "",
        "Mode: `short-term tactical`",
        "",
        "## Enabled",
        "",
        "| Rank | Symbol | Score | Realistic | Walk OOS | Recent OOS | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rank, item in enumerate(enabled, start=1):
        recent = item["recent_oos_pct"]
        recent_str = "n/a" if recent is None else f"{recent:+.2f}%"
        lines.append(
            f"| {rank} | {item['symbol']} | {item['selection_score']:+.2f} | "
            f"{item['realistic_return_pct']:+.2f}% | {item['avg_walk_forward_oos_pct']:+.2f}% | "
            f"{recent_str} | {item['reason']} |"
        )

    lines.extend([
        "",
        "## Blocked",
        "",
        "| Symbol | Score | Realistic | Walk OOS | Recent OOS | Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for item in blocked:
        recent = item["recent_oos_pct"]
        recent_str = "n/a" if recent is None else f"{recent:+.2f}%"
        lines.append(
            f"| {item['symbol']} | {item['selection_score']:+.2f} | "
            f"{item['realistic_return_pct']:+.2f}% | {item['avg_walk_forward_oos_pct']:+.2f}% | "
            f"{recent_str} | {item['reason']} |"
        )

    lines.extend([
        "",
        "## Selection Rules",
        "",
        f"- `top_n={top_n}`",
        f"- `realistic_return_pct > {MIN_REALISTIC_RETURN_PCT}`",
        f"- `avg_walk_forward_oos_pct >= {MIN_AVG_WALK_OOS_PCT}`",
        f"- `recent_oos_pct >= {MIN_RECENT_OOS_PCT}` when recent OOS exists",
        f"- `walk_windows >= {MIN_WALK_WINDOWS}`",
    ])
    if auto_apply_summary is not None:
        lines.extend([
            "",
            "## Auto Apply",
            "",
            f"- applied: `{auto_apply_summary['applied']}`",
            f"- current enabled: `{', '.join(auto_apply_summary['current_enabled']) or 'none'}`",
            f"- proposed enabled: `{', '.join(auto_apply_summary['proposed_enabled']) or 'none'}`",
            f"- added: `{', '.join(auto_apply_summary['added']) or 'none'}`",
            f"- removed: `{', '.join(auto_apply_summary['removed']) or 'none'}`",
            f"- changed_count: `{auto_apply_summary['changed_count']}`",
        ])
        if auto_apply_summary["reasons"]:
            lines.append(f"- blocked by: `{'; '.join(auto_apply_summary['reasons'])}`")
    return "\n".join(lines) + "\n"


def write_runtime_report(path: Path, recommendations: list[dict], top_n: int, *, auto_apply_summary: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_runtime_report(recommendations, top_n, auto_apply_summary=auto_apply_summary), encoding="utf-8")


def format_auto_apply_notification(summary: dict, *, top_n: int, report_path: Path | None = None) -> str:
    icon = "✅" if summary["applied"] else "⏸"
    lines = [
        f"{icon} runtime auto-apply",
        f"top_n={top_n}",
        f"applied={summary['applied']}",
        f"enabled={', '.join(summary['proposed_enabled']) or 'none'}",
        f"added={', '.join(summary['added']) or 'none'}",
        f"removed={', '.join(summary['removed']) or 'none'}",
        f"changed_count={summary['changed_count']}",
    ]
    if summary["reasons"]:
        lines.append(f"blocked_by={'; '.join(summary['reasons'])}")
    if report_path is not None:
        lines.append(f"report={report_path.name}")
    return "\n".join(lines)


def maybe_notify_telegram(summary: dict, *, top_n: int, report_path: Path | None = None) -> None:
    from backend.telegram_bot import send_message

    text = format_auto_apply_notification(summary, top_n=top_n, report_path=report_path)
    asyncio.run(send_message(text))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runtime universe research helper")
    parser.add_argument(
        "--write-backend",
        action="store_true",
        help=f"Merge results into {_BACKEND_PARAMS} (RSI/trailing keys unchanged)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of runtime symbols to enable (default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--write-report",
        nargs="?",
        const="__DEFAULT__",
        help="Write a markdown runtime-universe report. Optional custom path.",
    )
    parser.add_argument(
        "--allow-fetch",
        action="store_true",
        help="Allow fetching OHLCV from Upbit if cache is missing.",
    )
    parser.add_argument(
        "--auto-apply-runtime",
        action="store_true",
        help="Automatically write recommendations into runtime_params.json when safety gates pass.",
    )
    parser.add_argument(
        "--max-symbol-changes",
        type=int,
        default=DEFAULT_MAX_SYMBOL_CHANGES,
        help=f"Maximum allowed enabled-symbol changes for auto apply (default: {DEFAULT_MAX_SYMBOL_CHANGES})",
    )
    parser.add_argument(
        "--notify-telegram",
        action="store_true",
        help="Send auto-apply result summary to Telegram.",
    )
    args = parser.parse_args()

    recommendations = recommend_runtime_universe(top_n=args.top_n, cache_only=not args.allow_fetch)
    print("runtime_params.json 후보 (enabled / score / realistic / walk OOS / recent OOS):")
    for item in recommendations:
        print(
            f"{item['symbol']}: enabled={item['enabled']} | "
            f"score={item['selection_score']:+.1f} | "
            f"realistic={item['realistic_return_pct']:+.1f}% | "
            f"walk_oos={item['avg_walk_forward_oos_pct']:+.1f}% | "
            f"recent_oos={item['recent_oos_pct'] if item['recent_oos_pct'] is not None else 'n/a'}"
        )

    auto_apply_summary = None
    if args.auto_apply_runtime:
        auto_apply_summary = maybe_auto_apply_runtime_params(
            _BACKEND_PARAMS,
            recommendations,
            top_n=args.top_n,
            max_symbol_changes=args.max_symbol_changes,
        )
        if auto_apply_summary["applied"]:
            print(f"\n✅ auto-applied runtime params to {_BACKEND_PARAMS}")
        else:
            print(f"\n⏸ auto-apply blocked: {'; '.join(auto_apply_summary['reasons'])}")

    elif args.write_backend:
        merge_recommendations_into_params(_BACKEND_PARAMS, recommendations)
        print(f"\n✅ merged into {_BACKEND_PARAMS} — restart bot or call reload to pick up")

    if args.write_report is not None:
        report_path = default_report_path() if args.write_report == "__DEFAULT__" else Path(args.write_report)
        write_runtime_report(report_path, recommendations, args.top_n, auto_apply_summary=auto_apply_summary)
        print(f"📝 wrote runtime report to {report_path}")
    else:
        report_path = None

    if args.notify_telegram and auto_apply_summary is not None:
        maybe_notify_telegram(auto_apply_summary, top_n=args.top_n, report_path=report_path)
        print("📨 sent Telegram notification")
