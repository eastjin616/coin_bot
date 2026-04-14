import json
from unittest.mock import patch

from backend.live_performance import live_score_adjustments
from backend.runtime_params import get_active_buy_symbols, runtime_selection_meta


def test_get_active_buy_symbols_excludes_live_derated_symbols(tmp_path, monkeypatch):
    path = tmp_path / "runtime_params.json"
    path.write_text(
        json.dumps(
            {
                "KRW-LINK": {
                    "name": "링크",
                    "enabled": True,
                    "reason": "init",
                    "realistic_return_pct": 1.0,
                    "avg_walk_forward_oos_pct": 0.0,
                    "recent_oos_pct": -1.0,
                    "selection_score": 0.0,
                    "rsi_buy": 30,
                    "rsi_sell": 60,
                    "take_profit_percent": 3.0,
                    "trailing_activation_percent": 1.5,
                    "stop_loss_percent": 5,
                },
                "KRW-BCH": {
                    "name": "비캐",
                    "enabled": True,
                    "reason": "init",
                    "realistic_return_pct": 1.0,
                    "avg_walk_forward_oos_pct": 0.0,
                    "recent_oos_pct": -1.0,
                    "selection_score": 0.0,
                    "rsi_buy": 30,
                    "rsi_sell": 60,
                    "take_profit_percent": 3.0,
                    "trailing_activation_percent": 1.5,
                    "stop_loss_percent": 5,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNTIME_PARAMS_PATH", str(path))
    from backend import runtime_params as runtime_module

    runtime_module._table = None
    runtime_module._table_mtime_ns = None

    with patch("backend.runtime_params.get_live_derated_symbols", return_value={"KRW-LINK": "bad live pnl"}):
        active = get_active_buy_symbols()

    assert "KRW-LINK" not in active
    assert "KRW-BCH" in active


def test_runtime_selection_meta_marks_live_derated_reason(tmp_path, monkeypatch):
    path = tmp_path / "runtime_params.json"
    path.write_text(
        json.dumps(
            {
                "KRW-LINK": {
                    "name": "링크",
                    "enabled": True,
                    "reason": "init",
                    "realistic_return_pct": 1.0,
                    "avg_walk_forward_oos_pct": 0.0,
                    "recent_oos_pct": -1.0,
                    "selection_score": 0.0,
                    "rsi_buy": 30,
                    "rsi_sell": 60,
                    "take_profit_percent": 3.0,
                    "trailing_activation_percent": 1.5,
                    "stop_loss_percent": 5,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNTIME_PARAMS_PATH", str(path))
    from backend import runtime_params as runtime_module

    runtime_module._table = None
    runtime_module._table_mtime_ns = None

    with patch("backend.runtime_params.get_live_derated_symbols", return_value={"KRW-LINK": "bad live pnl"}):
        meta = runtime_selection_meta()

    assert meta["KRW-LINK"]["enabled"] is False
    assert meta["KRW-LINK"]["base_enabled"] is True
    assert meta["KRW-LINK"]["live_derated"] is True
    assert "live-derated" in meta["KRW-LINK"]["reason"]


def test_live_score_adjustments_reward_positive_recent_results():
    with patch(
        "backend.live_performance.recent_symbol_performance",
        return_value={
            "KRW-LINK": {"sell_count": 4, "win_rate": 75.0, "realized_pnl_krw": 25000.0, "avg_pnl_pct": 2.0},
            "KRW-ADA": {"sell_count": 4, "win_rate": 25.0, "realized_pnl_krw": -20000.0, "avg_pnl_pct": -2.0},
        },
    ):
        adjustments = live_score_adjustments()

    assert adjustments["KRW-LINK"] > 0
    assert adjustments["KRW-ADA"] < 0


def test_runtime_selection_meta_exposes_effective_selection_score():
    with patch("backend.runtime_params.get_live_derated_symbols", return_value={}), \
         patch("backend.runtime_params.live_score_adjustments", return_value={"KRW-LINK": 1.5}):
        meta = runtime_selection_meta()

    assert meta["KRW-LINK"]["selection_score"] is not None
    assert meta["KRW-LINK"]["live_score_adjustment"] == 1.5
    assert meta["KRW-LINK"]["effective_selection_score"] == round(meta["KRW-LINK"]["selection_score"] + 1.5, 3)


def test_runtime_selection_meta_recomputes_tactical_score_from_row_metrics(tmp_path, monkeypatch):
    path = tmp_path / "runtime_params.json"
    path.write_text(
        """
{
  "KRW-TEST": {
    "name": "테스트",
    "enabled": true,
    "reason": "old snapshot",
    "realistic_return_pct": 10.0,
    "avg_walk_forward_oos_pct": 1.0,
    "recent_oos_pct": -1.0,
    "selection_score": -999.0,
    "rsi_buy": 30,
    "rsi_sell": 60,
    "take_profit_percent": 3.0,
    "trailing_activation_percent": 1.5,
    "stop_loss_percent": 5
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNTIME_PARAMS_PATH", str(path))
    from backend import runtime_params as runtime_module

    runtime_module._table = None
    runtime_module._table_mtime_ns = None

    with patch("backend.runtime_params.get_live_derated_symbols", return_value={}), \
         patch("backend.runtime_params.get_loss_streak_cooldown_symbols", return_value={}), \
         patch("backend.runtime_params.live_score_adjustments", return_value={}):
        meta = runtime_selection_meta()

    assert meta["KRW-TEST"]["selection_score"] == 1.7
    assert "runtime-tactical-score +1.7" in meta["KRW-TEST"]["reason"]
