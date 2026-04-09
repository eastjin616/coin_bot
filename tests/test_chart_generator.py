"""일봉 신호는 마지막 확정 봉 기준으로 계산해야 한다."""
from datetime import datetime

import pandas as pd

from backend.ai.chart_generator import get_coin_signal_indicators


def test_get_coin_signal_indicators_uses_previous_closed_candle():
    index = pd.to_datetime([
        "2026-04-07 09:00:00",
        "2026-04-08 09:00:00",
        "2026-04-09 09:00:00",
    ])
    df = pd.DataFrame(
        {
            "close": [100, 90, 120],
            "volume": [10, 12, 50],
        },
        index=index,
    )

    # 충분한 rolling window 확보
    history = pd.DataFrame(
        {
            "close": [100] * 30,
            "volume": [10] * 30,
        },
        index=pd.date_range("2026-03-08 09:00:00", periods=30, freq="D"),
    )
    df = pd.concat([history, df])

    import pyupbit
    from unittest.mock import patch

    with patch.object(pyupbit, "get_ohlcv", return_value=df):
        indicators = get_coin_signal_indicators("KRW-BTC")

    assert indicators["signal_candle_time"] == datetime(2026, 4, 8, 9, 0, 0)
    assert indicators["current_price"] == 90
