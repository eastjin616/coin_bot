import yfinance as yf
import mplfinance as mpf
import os
from datetime import datetime
import pyupbit
import pandas as pd


def generate_stock_chart(symbol: str, output_dir: str = "/tmp/charts") -> str:
    """주식 차트 이미지 생성. 반환값: 이미지 파일 경로"""
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
    os.makedirs(output_dir, exist_ok=True)
    df = pyupbit.get_ohlcv(symbol, interval="minute60", count=120)
    if df is None or df.empty:
        raise ValueError(f"데이터 없음: {symbol}")
    output_path = os.path.join(output_dir, f"{symbol.replace('-', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    mpf.plot(df, type='candle', style='charles', savefig=output_path, figsize=(6.4, 6.4))
    return output_path


def _calc_indicators(df: pd.DataFrame) -> dict:
    """RSI, 이동평균, 거래량 기술적 지표 계산"""
    close = df["close"] if "close" in df.columns else df["Close"]

    # 이동평균
    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    current = close.iloc[-1]

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = (100 - 100 / (1 + rs)).iloc[-1]

    # 거래량 추세 (최근 5봉 vs 이전 5봉)
    vol = df["volume"] if "volume" in df.columns else df["Volume"]
    vol_recent = vol.iloc[-5:].mean()
    vol_prev = vol.iloc[-10:-5].mean()
    vol_trend = "증가" if vol_recent > vol_prev * 1.1 else ("감소" if vol_recent < vol_prev * 0.9 else "보합")

    return {
        "current_price": current,
        "ma5": ma5,
        "ma20": ma20,
        "rsi": rsi,
        "ma5_signal": "골든크로스 근접" if ma5 > ma20 else "데드크로스 근접",
        "price_vs_ma20": f"{'위' if current > ma20 else '아래'} ({abs(current - ma20) / ma20 * 100:.1f}%)",
        "volume_trend": vol_trend,
    }


def get_coin_indicators(symbol: str) -> dict:
    """코인 기술적 지표 반환"""
    df = pyupbit.get_ohlcv(symbol, interval="minute60", count=120)
    if df is None or df.empty:
        return {}
    return _calc_indicators(df)


def generate_chart(market: str, symbol: str) -> str:
    """market: 'stock' or 'coin'"""
    if market == "stock":
        return generate_stock_chart(symbol)
    elif market == "coin":
        return generate_coin_chart(symbol)
    else:
        raise ValueError(f"알 수 없는 마켓: {market}")
