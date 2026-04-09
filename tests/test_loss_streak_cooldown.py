from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from backend.live_performance import get_loss_streak_cooldown_symbols
from backend.runtime_params import get_active_buy_symbols, runtime_selection_meta


def test_loss_streak_cooldown_blocks_recent_consecutive_losses():
    now = datetime.now(UTC)
    with patch(
        "backend.live_performance.recent_loss_streaks",
        return_value={
            "KRW-LINK": {"loss_streak": 2, "last_sell_at": now - timedelta(days=1)},
            "KRW-BCH": {"loss_streak": 1, "last_sell_at": now - timedelta(days=1)},
        },
    ):
        cooled = get_loss_streak_cooldown_symbols(now=now)

    assert "KRW-LINK" in cooled
    assert "KRW-BCH" not in cooled


def test_get_active_buy_symbols_excludes_loss_streak_cooled_symbols():
    with patch("backend.runtime_params.get_live_derated_symbols", return_value={}), \
         patch("backend.runtime_params.get_loss_streak_cooldown_symbols", return_value={"KRW-BCH": "loss-streak cooldown"}):
        active = get_active_buy_symbols()

    assert "KRW-BCH" not in active


def test_runtime_selection_meta_marks_loss_streak_cooldown():
    with patch("backend.runtime_params.get_live_derated_symbols", return_value={}), \
         patch("backend.runtime_params.get_loss_streak_cooldown_symbols", return_value={"KRW-BCH": "loss-streak cooldown"}), \
         patch("backend.runtime_params.live_score_adjustments", return_value={}):
        meta = runtime_selection_meta()

    assert meta["KRW-BCH"]["enabled"] is False
    assert meta["KRW-BCH"]["loss_streak_cooled"] is True
    assert "streak-cooled" in meta["KRW-BCH"]["reason"]
