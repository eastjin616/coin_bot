# coin_bot 🤖

> 업비트 기반 코인 자동매매 봇 — 일봉 RSI 전략 + 코인별 파라미터 최적화
>
> Automated crypto trading bot on Upbit — Daily RSI strategy with per-coin optimized parameters

---

## 전략 / Strategy

일봉 RSI 기반 자동매매. 백테스팅 8년치 그리드서치로 코인별 파라미터 최적화.

Pure RSI-based trading on daily candles. Parameters optimized via 8-year backtesting grid search.

```
매 60초 순회
  ↓
BTC RSI < 40 → 하락장 → 알트코인 매수 차단
  ↓
RSI < 매수 임계값 → 매수 (잔고 × 20%, 최소 1만 / 최대 5만)
RSI > 매도 임계값 → 매도
  ↓
익절/손절 실시간 체크 (코인별 최적값)
```

---

## 코인별 최적 파라미터 / Per-coin Parameters

| 코인 | RSI 매수 | RSI 매도 | 익절 | 손절 | 백테스팅 수익률 |
|------|---------|---------|------|------|--------------|
| BTC  | 50 | 65 | +5%  | -3%  | +3.5%  |
| SOL  | 35 | 55 | +10% | -3%  | +5.7%  |
| DOGE | 35 | 55 | +5%  | -5%  | +8.9%  |
| DOT  | 35 | 55 | +5%  | -3%  | +0.9%  |
| ADA  | 35 | 55 | +5%  | -3%  | +3.1%  |
| AVAX | 45 | 70 | +8%  | -5%  | +5.8%  |
| LINK | 50 | 70 | +15% | -10% | +33.0% |
| TRX  | 35 | 55 | +5%  | -10% | +4.8%  |
| SUI  | 50 | 70 | +15% | -5%  | +8.0%  |
| HBAR | 45 | 70 | +20% | -5%  | +17.9% |
| ICP  | 35 | 55 | +5%  | -3%  | +0.3%  |
| ATOM | 45 | 60 | +15% | -5%  | +11.5% |
| UNI  | 50 | 65 | +25% | -3%  | +6.4%  |
| SHIB | 50 | 60 | +8%  | -5%  | +6.3%  |
| BCH  | 40 | 60 | +15% | -3%  | +18.0% |

> ETH, XRP, NEAR, OP — 백테스팅 음수로 감시 제외

---

## 기술 스택 / Tech Stack

| 영역 | 기술 |
|------|------|
| 백엔드 | FastAPI, APScheduler, psycopg3 |
| DB | PostgreSQL |
| 거래소 | 업비트 (pyupbit) |
| 알림 | Telegram Bot API |
| 배포 | AWS EC2 t3.micro (서울), systemd |

---

## 백테스터 / Backtester

```bash
python -m backtesting.optimize        # RSI 최적화
python -m backtesting.optimize risk   # 익절/손절 최적화
```
