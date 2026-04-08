# coin_bot 🤖

> Automated crypto trading bot on Upbit — Daily RSI strategy with per-coin optimized parameters and trailing-stop validation via 8-year backtesting

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql)
![AWS EC2](https://img.shields.io/badge/AWS-EC2_t3.micro-orange?logo=amazonaws)
![Upbit](https://img.shields.io/badge/Exchange-Upbit-blue)

---

## Overview

A fully automated cryptocurrency trading bot that runs 24/7 on AWS EC2. It monitors 15 coins every 60 seconds on Upbit (Korean exchange), executes buy/sell orders based on RSI signals, and manages risk with per-coin trailing-stop/stop-loss thresholds validated via historical backtesting.

**Key highlights:**
- RSI-based entry/exit strategy optimized per coin via grid search backtesting
- Regime filter: blocks altcoin buys when BTC shows multiple bearish signals
- Dynamic position sizing: 20% of available balance (min ₩10,000 / max ₩50,000)
- Trailing-stop risk management aligned between runtime and backtester
- Runtime buy universe narrowed to coins with relatively better realistic/OOS performance
- Telegram bot for real-time trade alerts and portfolio status
- Zombie position cleanup: auto-detects and removes stale DB entries

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AWS EC2 t3.micro                      │
│                                                          │
│  FastAPI + APScheduler                                   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Orchestrator (60s polling loop)                 │   │
│  │                                                  │   │
│  │  ① BTC RSI check → bear market filter           │   │
│  │  ② Per-coin RSI signal (BUY / SELL / HOLD)      │   │
│  │  ③ Trailing-stop / Stop-loss check              │   │
│  │  ④ Zombie position cleanup                      │   │
│  └──────────┬───────────────────┬───────────────────┘   │
│             │                   │                        │
│    ┌────────▼────────┐  ┌───────▼──────────┐            │
│    │  CoinExecutor   │  │  TelegramBot     │            │
│    │  (pyupbit API)  │  │  alerts + cmds   │            │
│    └────────┬────────┘  └──────────────────┘            │
│             │                                            │
│    ┌────────▼────────┐                                   │
│    │   PostgreSQL    │                                   │
│    │  positions      │                                   │
│    │  trades         │                                   │
│    └─────────────────┘                                   │
└─────────────────────────────────────────────────────────┘
```

---

## Strategy

Pure RSI strategy on daily candles. No AI, no external signals — just technical indicators with per-coin parameters tuned via backtesting.

```
Every 60 seconds:
  ↓
BTC risk-off regime? → Block all altcoin buys
  ↓
RSI < buy_threshold  → BUY  (20% of balance, ₩10K–₩50K)
RSI > sell_threshold → SELL
  ↓
Real-time trailing-stop / stop-loss check (per-coin values)
```

---

## Per-coin Optimized Parameters

Parameters tuned via cached daily OHLCV data with conservative assumptions:
- Fee: `0.05%`
- Slippage: `0.05%`
- Validation: in-sample optimization + walk-forward + recent 180-day OOS check

| Coin | RSI Buy | RSI Sell | Trailing Activation | Stop Loss | Realistic Return |
|------|---------|----------|---------------------|-----------|------------------|
| BTC  | 50 | 65 | +1.5% | -3%  | -10.1% |
| SOL  | 35 | 70 | +1.5% | -3%  | +2.6%  |
| DOGE | 35 | 55 | +1.5% | -5%  | +3.7%  |
| DOT  | 35 | 55 | +1.5% | -3%  | -4.7%  |
| ADA  | 35 | 55 | +1.5% | -3%  | -5.7%  |
| AVAX | 35 | 55 | +1.5% | -3%  | -3.4%  |
| LINK | 50 | 70 | +5.0% | -5%  | +21.2% |
| TRX  | 35 | 55 | +1.5% | -10% | -1.0%  |
| SUI  | 45 | 70 | +1.5% | -3%  | +0.0%  |
| HBAR | 40 | 70 | +1.5% | -5%  | +4.2%  |
| ICP  | 35 | 55 | +1.5% | -3%  | +0.2%  |
| ATOM | 45 | 60 | +1.5% | -5%  | -0.3%  |
| UNI  | 50 | 70 | +1.5% | -7%  | +5.3%  |
| SHIB | 50 | 60 | +1.5% | -5%  | -1.4%  |
| BCH  | 40 | 60 | +1.5% | -5%  | +6.8%  |

> ETH, XRP, NEAR, OP excluded — negative backtest returns

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, APScheduler, psycopg3 |
| Database | PostgreSQL 16 |
| Exchange | Upbit API (pyupbit) |
| Notifications | Telegram Bot API |
| Infra | AWS EC2 t3.micro (Seoul), systemd |

---

## Project Structure

```
coin_bot/
├── backend/
│   ├── main.py              # FastAPI entrypoint, lifespan hooks
│   ├── orchestrator.py      # Core trading loop (RSI signals, risk mgmt)
│   ├── config.py            # Settings via pydantic-settings
│   ├── database.py          # PostgreSQL connection + schema
│   ├── runtime_status.py    # Runtime universe / regime / performance status
│   ├── telegram_bot.py      # Trade alerts + /balance /status commands
│   ├── routers/
│   │   └── runtime.py       # /api/runtime/status
│   └── execution/
│       └── coin_executor.py # Upbit order execution
├── backtesting/
│   ├── optimize.py          # Grid search: RSI + trailing-stop/stop-loss
│   ├── reselect_runtime.py  # Runtime universe reselection helper
│   └── data/                # Cached OHLCV (gitignored)
└── tests/
    ├── test_orchestrator.py
    ├── test_backtesting.py
    └── test_runtime_router.py
```

---

## Backtester

Downloads 8 years of daily OHLCV from Upbit and runs grid search to find optimal parameters per coin.

```bash
# Step 1: Optimize RSI buy/sell thresholds
python -m backtesting.optimize

# Step 2: Optimize trailing-stop / stop-loss (locks in best RSI from step 1)
python -m backtesting.optimize risk

# Step 3: Recompute runtime universe recommendation
python -m backtesting.reselect_runtime
```

Grid search ranges:
- RSI buy: `[30, 35, 40, 45, 50]`
- RSI sell: `[55, 60, 65, 70]`
- Stop loss: `[3%, 5%, 7%, 10%]`
- Trailing activation: `[1.5%, 2.5%, 3.5%, 5.0%]`
- Walk-forward: `train=720d`, `test=180d`, `step=180d`

## Recent OOS Snapshot

Cached-data recent 180-day OOS results were mostly flat-to-negative:
- DOGE `+0.1%`
- DOT `+0.4%`
- BCH `-1.0%`
- LINK `-2.5%`
- BTC `-3.5%`
- SOL `-4.8%`

This means the strategy is not yet robust enough to claim a strong recent live edge across the full watchlist.

## Runtime Universe

Current new-buy runtime universe is intentionally narrower, and the DB watchlist is auto-synced to match it:
- `KRW-BTC`
- `KRW-SOL`
- `KRW-DOGE`
- `KRW-LINK`
- `KRW-HBAR`
- `KRW-UNI`
- `KRW-BCH`

Other coins can still be held temporarily as existing positions. New entries are blocked, and the active watchlist is automatically aligned to:
- the runtime buy universe
- current held positions

## Regime Filter

Altcoin buys are blocked when BTC shows at least 2 of the following 3 bearish conditions:
- RSI `< 45`
- `MA5 < MA20`
- Current price `< MA20`

## Runtime Status

Operational status is available from:
- Telegram `/status`
- API `GET /api/runtime/status`

The runtime status includes:
- `regime` (`risk_on` / `caution` / `risk_off`)
- `risk_off` 여부
- 권장 매수 비중
- BTC RSI / MA5 / MA20 / 현재가
- 신규 매수 허용 종목
- 신규 매수 제외 종목
- 종목별 허용/제외 사유
- active watchlist 종목
- 최근 30일 실현손익 / 승률 / 매도 횟수

## Deprioritized Positions

Coins outside the runtime buy universe are not force-sold immediately.

Instead, if they are already held, the bot will prefer exiting them when either:
- unrealized P&L reaches `+1.0%` or better
- RSI reaches a weak sell zone

## Position Sizing

The bot now uses regime-aware sizing:
- `risk_on`: `20%`
- `caution`: `10%`
- `risk_off`: `5%`

For altcoins, `risk_off` still blocks new buys. The ratio is mainly relevant for BTC or future regime-aware expansions.

## Testing

```bash
PYTHONPATH=. pytest -q
```

Current local regression status:
- `33 passed`

---

## Local Setup

### Prerequisites
- Python 3.13
- PostgreSQL 16
- Upbit account with API keys
- Telegram bot token

### 1. Clone & install

```bash
git clone https://github.com/eastjin616/coin_bot.git
cd coin_bot
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in your API keys
```

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/coinbot
UPBIT_ACCESS_KEY=your_key
UPBIT_SECRET_KEY=your_secret
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_ALLOWED_CHAT_IDS=your_chat_id
```

### 3. Start

```bash
# Start PostgreSQL
brew services start postgresql@16

# Run server (auto-creates tables, starts polling loop + Telegram bot)
uvicorn backend.main:app --port 8002
```

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/balance` | Current positions + KRW balance |
| `/status` | Real-time RSI + unrealized P&L per coin |

Automated alerts: trade executions, low balance warnings, daily 9AM portfolio report, weekly P&L summary.

---

## License

MIT
