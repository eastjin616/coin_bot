import pyupbit
import pandas as pd
import time
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def fetch_ohlcv(symbol: str, interval: str = "minute15", count: int = 200) -> pd.DataFrame:
    """업비트에서 OHLCV 데이터 크롤링. count일치 데이터 반환.
    캐시: 같은 날 1시간 이내 재요청 시 파일 재사용.
    """
    DATA_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    cache_file = DATA_DIR / f"{symbol.replace('-', '_')}_{interval}_{count}_{today}.csv"

    if cache_file.exists():
        mtime = cache_file.stat().st_mtime
        if (time.time() - mtime) < 3600:
            return pd.read_csv(cache_file, index_col=0, parse_dates=True)

    candles_needed = count * 96 if interval == "minute15" else count * 24
    all_frames = []
    to = None
    max_retries = 3

    while candles_needed > 0:
        fetch = min(candles_needed, 200)
        kwargs = {"interval": interval, "count": fetch}
        if to:
            kwargs["to"] = to

        df = None
        for attempt in range(max_retries):
            df = pyupbit.get_ohlcv(symbol, **kwargs)
            if df is not None and not df.empty:
                break
            time.sleep(0.5 * (attempt + 1))

        if df is None or df.empty:
            print(f"  ⚠️ 데이터 수신 실패 ({symbol}), 중단")
            break

        all_frames.append(df)
        to = df.index[0].strftime("%Y-%m-%d %H:%M:%S")
        candles_needed -= fetch
        time.sleep(0.2)

    if not all_frames:
        return pd.DataFrame()

    result = pd.concat(all_frames).sort_index().drop_duplicates()
    result.to_csv(cache_file)
    return result


if __name__ == "__main__":
    df = fetch_ohlcv("KRW-BTC", count=30)
    print(f"BTC 데이터: {len(df)}개 봉, {df.index[0]} ~ {df.index[-1]}")
