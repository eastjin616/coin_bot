# Backtester Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 업비트 코인 과거 데이터로 RSI + MA 크로스 전략을 백테스팅하여 최적 파라미터를 찾는다.

**Architecture:** 업비트 API로 최대 200일치 15분봉 데이터를 크롤링하고, RSI + MA 전략을 시뮬레이션하여 수익률/승률/MDD를 계산한다. 파라미터 그리드 서치로 최적값을 찾아 리포트로 출력한다.

**Tech Stack:** Python, pyupbit, pandas, numpy

**실행 방법:** 항상 `python -m backtesting.optimize` 형태로 실행 (패키지 import 경로 보장)

---

### Task 1: 데이터 크롤러

**Files:**
- Create: `backtesting/__init__.py`
- Create: `backtesting/data_fetcher.py`

- [ ] **Step 1: 패키지 초기화 및 data_fetcher.py 작성**

```python
# backtesting/__init__.py
# (비워둠)
```

```python
# backtesting/data_fetcher.py
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

    # 200일 × 96봉/일 (15분봉) = 19,200개, 한 번에 200개씩 요청
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
```

- [ ] **Step 2: 실행 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m backtesting.data_fetcher
```

Expected: `BTC 데이터: 2880개 봉, ...`

- [ ] **Step 3: 커밋**

```bash
git add backtesting/
git commit -m "feat: 업비트 OHLCV 데이터 크롤러 (캐시, 재시도 포함)"
```

---

### Task 2: 기술적 지표 계산

**Files:**
- Create: `backtesting/indicators.py`

- [ ] **Step 1: indicators.py 작성**

RSI 계산 방식은 `backend/ai/chart_generator.py`와 동일하게 `loss.replace(0, 1e-9)` 사용 (loss=0일 때 RSI=100 수렴).

```python
# backtesting/indicators.py
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
    """DataFrame에 RSI, ma_fast, ma_slow 컬럼 추가"""
    df = df.copy()
    df["rsi"] = calc_rsi(df["close"], rsi_period)
    df["ma_fast"] = calc_ma(df["close"], ma_fast)
    df["ma_slow"] = calc_ma(df["close"], ma_slow)
    return df.dropna()
```

- [ ] **Step 2: 커밋**

```bash
git add backtesting/indicators.py
git commit -m "feat: RSI + MA 지표 계산 모듈"
```

---

### Task 3: 전략 시뮬레이터

**Files:**
- Create: `backtesting/simulator.py`

- [ ] **Step 1: simulator.py 작성**

```python
# backtesting/simulator.py
import pandas as pd
from backtesting.indicators import add_indicators


def run_backtest(
    df: pd.DataFrame,
    rsi_buy: float = 40.0,
    rsi_sell: float = 60.0,
    ma_fast: int = 5,
    ma_slow: int = 20,
    order_amount: int = 10000,
    take_profit: float = 10.0,
    stop_loss: float = 5.0,
) -> dict:
    """
    RSI + MA 크로스 전략 백테스팅.
    반환: {total_return_pct, win_rate, mdd, num_trades, final_value, trades}
    """
    df = add_indicators(df, ma_fast=ma_fast, ma_slow=ma_slow)
    cash = 100000.0
    position = 0.0
    entry_price = 0.0
    trades = []
    peak_value = cash
    min_drawdown = 0.0  # MDD 추적 (음수)

    def update_mdd(current_cash: float, current_pos: float, current_price: float):
        nonlocal peak_value, min_drawdown
        portfolio_value = current_cash + current_pos * current_price
        if portfolio_value > peak_value:
            peak_value = portfolio_value
        drawdown = (portfolio_value - peak_value) / peak_value * 100
        if drawdown < min_drawdown:
            min_drawdown = drawdown

    for ts, row in df.iterrows():
        price = row["close"]
        rsi = row["rsi"]
        golden = row["ma_fast"] > row["ma_slow"]
        death = row["ma_fast"] < row["ma_slow"]

        # 익절/손절
        if position > 0 and entry_price > 0:
            change_pct = (price - entry_price) / entry_price * 100
            if change_pct >= take_profit or change_pct <= -stop_loss:
                cash += position * price
                trades.append({
                    "type": "SELL", "price": price, "ts": ts,
                    "reason": "익절" if change_pct >= take_profit else "손절",
                    "pnl_pct": change_pct,
                })
                position = 0.0
                entry_price = 0.0
                update_mdd(cash, position, price)
                continue

        # 매수
        if position == 0 and rsi < rsi_buy and golden and cash >= order_amount:
            qty = order_amount / price
            cash -= order_amount
            position += qty
            entry_price = price
            trades.append({"type": "BUY", "price": price, "ts": ts, "reason": "RSI+MA"})

        # 매도
        elif position > 0 and (rsi > rsi_sell or death):
            pnl_pct = (price - entry_price) / entry_price * 100
            cash += position * price
            trades.append({
                "type": "SELL", "price": price, "ts": ts,
                "reason": "RSI/MA", "pnl_pct": pnl_pct,
            })
            position = 0.0
            entry_price = 0.0

        update_mdd(cash, position, price)

    # 최종 정산 (미청산 포지션은 마지막 봉 종가로 청산 가정)
    final_value = cash + position * df["close"].iloc[-1]
    total_return = (final_value - 100000) / 100000 * 100

    sell_trades = [t for t in trades if t["type"] == "SELL" and "pnl_pct" in t]
    win_rate = (
        len([t for t in sell_trades if t["pnl_pct"] > 0]) / len(sell_trades) * 100
        if sell_trades else 0
    )

    return {
        "total_return_pct": total_return,
        "win_rate": win_rate,
        "mdd": min_drawdown,
        "num_trades": len(sell_trades),
        "final_value": final_value,
        "trades": trades,
    }
```

- [ ] **Step 2: 커밋**

```bash
git add backtesting/simulator.py
git commit -m "feat: RSI+MA 크로스 전략 시뮬레이터 (MDD 포함)"
```

---

### Task 4: 파라미터 최적화 + 리포트

**Files:**
- Create: `backtesting/optimize.py`

- [ ] **Step 1: optimize.py 작성**

```python
# backtesting/optimize.py
import itertools
from backtesting.data_fetcher import fetch_ohlcv
from backtesting.simulator import run_backtest

SYMBOLS = ["KRW-BTC", "KRW-ETH", "KRW-SOL", "KRW-XRP", "KRW-DOGE"]
RSI_BUY_RANGE = [30, 35, 40, 45]
RSI_SELL_RANGE = [55, 60, 65, 70]
DATA_DAYS = 200


def optimize(symbol: str) -> list[dict]:
    print(f"\n📊 {symbol} 데이터 로딩 중...")
    df = fetch_ohlcv(symbol, count=DATA_DAYS)
    if df.empty:
        print(f"  데이터 없음: {symbol}")
        return []

    results = []
    for rsi_buy, rsi_sell in itertools.product(RSI_BUY_RANGE, RSI_SELL_RANGE):
        if rsi_buy >= rsi_sell:
            continue
        result = run_backtest(df, rsi_buy=rsi_buy, rsi_sell=rsi_sell)
        results.append({
            "symbol": symbol,
            "rsi_buy": rsi_buy,
            "rsi_sell": rsi_sell,
            "return_pct": round(result["total_return_pct"], 2),
            "win_rate": round(result["win_rate"], 1),
            "mdd": round(result["mdd"], 1),
            "num_trades": result["num_trades"],
        })

    return sorted(results, key=lambda x: x["return_pct"], reverse=True)


def print_report(all_results: list[dict]):
    print("\n" + "=" * 72)
    print("📈 백테스팅 결과 리포트 (최근 200일, 15분봉)")
    print("=" * 72)

    best_by_symbol: dict[str, dict] = {}
    for r in all_results:
        sym = r["symbol"]
        if sym not in best_by_symbol or r["return_pct"] > best_by_symbol[sym]["return_pct"]:
            best_by_symbol[sym] = r

    print(f"\n{'코인':<12} {'RSI매수':<8} {'RSI매도':<8} {'수익률':<10} {'승률':<8} {'MDD':<8} {'거래수'}")
    print("-" * 72)
    for sym, r in best_by_symbol.items():
        emoji = "✅" if r["return_pct"] > 0 else "❌"
        print(
            f"{emoji} {sym[4:]:<10} {r['rsi_buy']:<8} {r['rsi_sell']:<8} "
            f"{r['return_pct']:>+6.1f}%   {r['win_rate']:>5.1f}%   "
            f"{r['mdd']:>5.1f}%   {r['num_trades']}"
        )

    if all_results:
        best = sorted(all_results, key=lambda x: x["return_pct"], reverse=True)[0]
        print(f"\n🏆 최적 파라미터: RSI 매수 {best['rsi_buy']} / 매도 {best['rsi_sell']}")
        print(f"   ({best['symbol'][4:]} 기준, 수익률 {best['return_pct']:+.1f}%, MDD {best['mdd']:.1f}%)")
        print(f"\n→ config.py에 반영: rsi_buy_threshold={best['rsi_buy']}, rsi_sell_threshold={best['rsi_sell']}")


if __name__ == "__main__":
    all_results = []
    for sym in SYMBOLS:
        results = optimize(sym)
        all_results.extend(results)
        if results:
            print(f"  최고: RSI {results[0]['rsi_buy']}/{results[0]['rsi_sell']} → {results[0]['return_pct']:+.1f}%")

    print_report(all_results)
```

- [ ] **Step 2: 실행**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m backtesting.optimize
```

- [ ] **Step 3: 커밋**

```bash
git add backtesting/optimize.py
git commit -m "feat: 백테스팅 파라미터 최적화 + 리포트 출력"
```

---

### Task 5: 결과 반영

- [ ] **Step 1: 리포트 결과 확인 후 config.py의 `rsi_buy_threshold` / `rsi_sell_threshold` 최적값으로 업데이트**
- [ ] **Step 2: PROGRESS.md 업데이트 후 커밋**
- [ ] **Step 3: EC2 배포**

```bash
rsync -av --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='.env' \
  /Users/seodongjin/Documents/GitHub/coin_bot/ \
  ubuntu@43.203.205.237:/home/ubuntu/coin_bot/ \
  -e "ssh -i ~/Desktop/coin-bot-key.pem"
ssh -i ~/Desktop/coin-bot-key.pem ubuntu@43.203.205.237 "sudo systemctl restart coinbot"
```
