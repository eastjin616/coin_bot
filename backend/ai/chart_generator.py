from datetime import datetime
import os

import pandas as pd
import pyupbit


def generate_stock_chart(symbol: str, output_dir: str = "/tmp/charts") -> str:
    """주식 차트 이미지 생성. 반환값: 이미지 파일 경로"""
    import yfinance as yf
    import mplfinance as mpf

    os.makedirs(output_dir, exist_ok=True)
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="5d", interval="1h")
    if df.empty:
        raise ValueError(f"데이터 없음: {symbol}")
    output_path = os.path.join(output_dir, f"{symbol.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    mpf.plot(df, type='candle', style='charles', savefig=output_path, figsize=(6.4, 6.4))
    return output_path


def generate_coin_chart(symbol: str, output_dir: str = "/tmp/charts") -> str:
    """코인 차트 이미지 생성. 반환값: 이미지 파일 경로"""
    import mplfinance as mpf

    os.makedirs(output_dir, exist_ok=True)
    df = pyupbit.get_ohlcv(symbol, interval="minute60", count=120)
    if df is None or df.empty:
        raise ValueError(f"데이터 없음: {symbol}")
    output_path = os.path.join(output_dir, f"{symbol.replace('-', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    mpf.plot(df, type='candle', style='charles', savefig=output_path, figsize=(6.4, 6.4))
    return output_path


def _calc_indicators(df: pd.DataFrame, *, candle_offset: int = 0) -> dict:
    """RSI, 이동평균, 거래량 기술적 지표 계산.

    candle_offset=0  -> 마지막 봉
    candle_offset=-1 -> 마지막으로 확정된 이전 봉
    """
    close = df["close"] if "close" in df.columns else df["Close"]
    if close.empty:
        return {}

    target_end = len(close) + candle_offset
    if target_end <= 0:
        return {}

    # 이동평균
    ma5_series = close.rolling(5).mean()
    ma20_series = close.rolling(20).mean()
    ma5 = ma5_series.iloc[target_end - 1]
    ma20 = ma20_series.iloc[target_end - 1]
    current = close.iloc[target_end - 1]

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = (100 - 100 / (1 + rs)).iloc[target_end - 1]

    # 거래량 추세 (최근 5봉 vs 이전 5봉)
    vol = df["volume"] if "volume" in df.columns else df["Volume"]
    vol_recent = vol.iloc[max(0, target_end - 5):target_end].mean()
    vol_prev = vol.iloc[max(0, target_end - 10):max(0, target_end - 5)].mean()
    vol_trend = "증가" if vol_recent > vol_prev * 1.1 else ("감소" if vol_recent < vol_prev * 0.9 else "보합")
    candle_time = df.index[target_end - 1]
    candle_time = pd.Timestamp(candle_time).to_pydatetime() if candle_time is not None else None

    return {
        "current_price": current,
        "ma5": ma5,
        "ma20": ma20,
        "rsi": rsi,
        "signal_candle_time": candle_time,
        "ma5_signal": "골든크로스 근접" if ma5 > ma20 else "데드크로스 근접",
        "price_vs_ma20": f"{'위' if current > ma20 else '아래'} ({abs(current - ma20) / ma20 * 100:.1f}%)",
        "volume_trend": vol_trend,
    }


def get_coin_indicators(symbol: str) -> dict:
    """코인 기술적 지표 반환 (일봉 200개 = 약 7개월)"""
    df = pyupbit.get_ohlcv(symbol, interval="day", count=200)
    if df is None or df.empty:
        return {}
    return _calc_indicators(df)


def get_coin_signal_indicators(symbol: str) -> dict:
    """전략 신호용 기술적 지표 반환.

    분 단위로 루프를 돌더라도 마지막 미완성 일봉은 제외하고, 직전 확정 일봉만 사용한다.
    """
    df = pyupbit.get_ohlcv(symbol, interval="day", count=201)
    if df is None or len(df) < 2:
        return {}
    return _calc_indicators(df, candle_offset=-1)


def generate_chart(market: str, symbol: str) -> str:
    """market: 'stock' or 'coin'"""
    if market == "stock":
        return generate_stock_chart(symbol)
    elif market == "coin":
        return generate_coin_chart(symbol)
    else:
        raise ValueError(f"알 수 없는 마켓: {market}")
