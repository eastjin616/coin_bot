import yfinance as yf
import mplfinance as mpf
import os
from datetime import datetime
import pyupbit


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


def generate_chart(market: str, symbol: str) -> str:
    """market: 'stock' or 'coin'"""
    if market == "stock":
        return generate_stock_chart(symbol)
    elif market == "coin":
        return generate_coin_chart(symbol)
    else:
        raise ValueError(f"알 수 없는 마켓: {market}")
