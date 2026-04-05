# coin_bot 🤖

> Automated crypto trading bot on Upbit — Daily RSI strategy with per-coin optimized parameters via 8-year backtesting

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql)
![AWS EC2](https://img.shields.io/badge/AWS-EC2_t3.micro-orange?logo=amazonaws)
![Upbit](https://img.shields.io/badge/Exchange-Upbit-blue)

---

## Overview

A fully automated cryptocurrency trading bot that runs 24/7 on AWS EC2. It monitors 15 coins every 60 seconds on Upbit (Korean exchange), executes buy/sell orders based on RSI signals, and manages risk with per-coin take-profit/stop-loss thresholds — all optimized via 8 years of historical backtesting.

**Key highlights:**
- RSI-based entry/exit strategy optimized per coin via grid search backtesting
- Bear market filter: blocks altcoin buys when BTC RSI < 40
- Dynamic position sizing: 20% of available balance (min ₩10,000 / max ₩50,000)
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
│  │  ③ Take-profit / Stop-loss check                │   │
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
BTC RSI < 40? → Block all altcoin buys (bear market filter)
  ↓
RSI < buy_threshold  → BUY  (20% of balance, ₩10K–₩50K)
RSI > sell_threshold → SELL
  ↓
Real-time take-profit / stop-loss check (per-coin values)
```

---

## Per-coin Optimized Parameters

Parameters tuned via 8-year grid search (2017–2025) on Upbit daily OHLCV data.

| Coin | RSI Buy | RSI Sell | Take Profit | Stop Loss | Backtest Return |
|------|---------|----------|-------------|-----------|-----------------|
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
│   ├── telegram_bot.py      # Trade alerts + /balance /status commands
│   └── execution/
│       └── coin_executor.py # Upbit order execution
├── backtesting/
│   ├── optimize.py          # Grid search: RSI + take-profit/stop-loss
│   └── data/                # Cached OHLCV (gitignored)
└── tests/
    └── test_orchestrator.py
```

---

## Backtester

Downloads 8 years of daily OHLCV from Upbit and runs grid search to find optimal parameters per coin.

```bash
# Step 1: Optimize RSI buy/sell thresholds
python -m backtesting.optimize

# Step 2: Optimize take-profit / stop-loss (locks in best RSI from step 1)
python -m backtesting.optimize risk
```

Grid search ranges:
- RSI buy: `[30, 35, 40, 45, 50]`
- RSI sell: `[55, 60, 65, 70]`
- Take profit: `[5%, 8%, 10%, 15%, 20%, 25%]`
- Stop loss: `[3%, 5%, 7%, 10%]`

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
