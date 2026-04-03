import pandas as pd
import numpy as np


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)  # chart_generator.py와 동일
    return 100 - (100 / (1 + rs))


def calc_ma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def add_indicators(
    df: pd.DataFrame,
    rsi_period: int = 14,
    ma_fast: int = 5,
    ma_slow: int = 20,
) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = calc_rsi(df["close"], rsi_period)
    df["ma_fast"] = calc_ma(df["close"], ma_fast)
    df["ma_slow"] = calc_ma(df["close"], ma_slow)
    return df.dropna()
