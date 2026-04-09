from pathlib import Path

from backtesting.reselect_runtime import (
    auto_apply_decision,
    default_report_path,
    format_auto_apply_notification,
    maybe_auto_apply_runtime_params,
    recommend_runtime_universe,
    render_runtime_report,
    selection_score,
    write_runtime_report,
)


def test_selection_score_rewards_robust_recent_candidates():
    score = selection_score(
        {"return_pct": 10.0, "num_trades": 120, "mdd": -8.0},
        {"avg_test_return_pct": 1.0, "windows": 8},
        {"return_pct": -1.0},
    )
    weak_score = selection_score(
        {"return_pct": 10.0, "num_trades": 10, "mdd": -15.0},
        {"avg_test_return_pct": -2.0, "windows": 1},
        {"return_pct": -8.0},
    )
    assert score > weak_score


def test_recommend_runtime_universe_selects_top_n_candidates(monkeypatch):
    full_results = [
        {"symbol": "KRW-A", "return_pct": 15.0, "num_trades": 100, "mdd": -8.0},
        {"symbol": "KRW-B", "return_pct": 12.0, "num_trades": 80, "mdd": -8.0},
        {"symbol": "KRW-C", "return_pct": 6.0, "num_trades": 90, "mdd": -9.0},
        {"symbol": "KRW-D", "return_pct": 20.0, "num_trades": 5, "mdd": -20.0},
    ]
    walk_summaries = [
        {"symbol": "KRW-A", "avg_test_return_pct": 1.5, "windows": 10},
        {"symbol": "KRW-B", "avg_test_return_pct": 1.0, "windows": 8},
        {"symbol": "KRW-C", "avg_test_return_pct": -0.2, "windows": 6},
        {"symbol": "KRW-D", "avg_test_return_pct": -3.0, "windows": 1},
    ]
    recent_oos = [
        {"symbol": "KRW-A", "return_pct": -1.0},
        {"symbol": "KRW-B", "return_pct": -2.0},
        {"symbol": "KRW-C", "return_pct": -0.5},
        {"symbol": "KRW-D", "return_pct": -7.0},
    ]

    monkeypatch.setattr(
        "backtesting.reselect_runtime.run_research",
        lambda _symbols, cache_only=True: (full_results, walk_summaries, recent_oos),
    )

    result = recommend_runtime_universe(top_n=2)
    enabled = [row["symbol"] for row in result if row["enabled"]]

    assert enabled == ["KRW-A", "KRW-B"]
    assert all("score" in row["reason"] for row in result)


def test_render_runtime_report_includes_enabled_and_blocked_sections():
    report = render_runtime_report(
        [
            {
                "symbol": "KRW-BCH",
                "enabled": True,
                "selection_score": 17.8,
                "realistic_return_pct": 22.2,
                "avg_walk_forward_oos_pct": 1.1,
                "recent_oos_pct": -2.2,
                "reason": "top 3",
            },
            {
                "symbol": "KRW-TRX",
                "enabled": False,
                "selection_score": 7.3,
                "realistic_return_pct": 6.8,
                "avg_walk_forward_oos_pct": -0.3,
                "recent_oos_pct": -0.6,
                "reason": "blocked",
            },
        ],
        top_n=3,
    )

    assert "## Enabled" in report
    assert "KRW-BCH" in report
    assert "## Blocked" in report
    assert "KRW-TRX" in report


def test_render_runtime_report_includes_auto_apply_summary():
    report = render_runtime_report(
        [
            {
                "symbol": "KRW-BCH",
                "enabled": True,
                "selection_score": 17.8,
                "realistic_return_pct": 22.2,
                "avg_walk_forward_oos_pct": 1.1,
                "recent_oos_pct": -2.2,
                "reason": "top 3",
            }
        ],
        top_n=3,
        auto_apply_summary={
            "applied": False,
            "current_enabled": ["KRW-BCH"],
            "proposed_enabled": ["KRW-BCH", "KRW-LINK"],
            "added": ["KRW-LINK"],
            "removed": [],
            "changed_count": 1,
            "reasons": ["enabled count 2 < top_n 3"],
        },
    )

    assert "## Auto Apply" in report
    assert "blocked by" in report


def test_auto_apply_decision_blocks_large_symbol_turnover():
    decision = auto_apply_decision(
        {"KRW-A", "KRW-B", "KRW-C"},
        [
            {"symbol": "KRW-D", "enabled": True},
            {"symbol": "KRW-E", "enabled": True},
            {"symbol": "KRW-F", "enabled": True},
        ],
        top_n=3,
        max_symbol_changes=2,
    )

    assert decision["applied"] is False
    assert decision["changed_count"] == 6


def test_maybe_auto_apply_runtime_params_writes_when_safe(tmp_path: Path):
    path = tmp_path / "runtime_params.json"
    path.write_text(
        """
{
  "KRW-A": {"enabled": true, "name": "A"},
  "KRW-B": {"enabled": true, "name": "B"},
  "KRW-C": {"enabled": false, "name": "C"}
}
""".strip(),
        encoding="utf-8",
    )

    decision = maybe_auto_apply_runtime_params(
        path,
        [
            {"symbol": "KRW-A", "enabled": True, "reason": "keep", "realistic_return_pct": 1, "avg_walk_forward_oos_pct": 1, "recent_oos_pct": 1, "selection_score": 1},
            {"symbol": "KRW-B", "enabled": False, "reason": "drop", "realistic_return_pct": 1, "avg_walk_forward_oos_pct": 1, "recent_oos_pct": 1, "selection_score": 1},
            {"symbol": "KRW-C", "enabled": True, "reason": "add", "realistic_return_pct": 1, "avg_walk_forward_oos_pct": 1, "recent_oos_pct": 1, "selection_score": 1},
        ],
        top_n=2,
        max_symbol_changes=2,
    )

    assert decision["applied"] is True
    text = path.read_text(encoding="utf-8")
    assert '"KRW-C"' in text
    assert '"enabled": true' in text


def test_format_auto_apply_notification_includes_outcome_and_report():
    text = format_auto_apply_notification(
        {
            "applied": False,
            "proposed_enabled": ["KRW-BCH", "KRW-LINK"],
            "added": ["KRW-LINK"],
            "removed": [],
            "changed_count": 1,
            "reasons": ["enabled count 2 < top_n 3"],
        },
        top_n=3,
        report_path=Path("2026-04-09-runtime-universe.md"),
    )

    assert "runtime auto-apply" in text
    assert "applied=False" in text
    assert "blocked_by=enabled count 2 < top_n 3" in text
    assert "report=2026-04-09-runtime-universe.md" in text


def test_write_runtime_report_writes_markdown(tmp_path: Path):
    path = tmp_path / "runtime.md"
    write_runtime_report(
        path,
        [
            {
                "symbol": "KRW-BCH",
                "enabled": True,
                "selection_score": 17.8,
                "realistic_return_pct": 22.2,
                "avg_walk_forward_oos_pct": 1.1,
                "recent_oos_pct": -2.2,
                "reason": "top 3",
            }
        ],
        top_n=3,
    )

    text = path.read_text(encoding="utf-8")
    assert "# Runtime Universe Report" in text
    assert "KRW-BCH" in text


def test_default_report_path_uses_reports_dir():
    path = default_report_path()
    assert "docs/superpowers/reports" in str(path)
