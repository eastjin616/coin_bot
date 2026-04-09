from unittest.mock import patch

from backend.live_performance import live_score_adjustments
from backend.runtime_params import get_active_buy_symbols, runtime_selection_meta


def test_get_active_buy_symbols_excludes_live_derated_symbols():
    with patch("backend.runtime_params.get_live_derated_symbols", return_value={"KRW-LINK": "bad live pnl"}):
        active = get_active_buy_symbols()

    assert "KRW-LINK" not in active
    assert "KRW-BCH" in active


def test_runtime_selection_meta_marks_live_derated_reason():
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
