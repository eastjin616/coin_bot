# coin_bot 🤖

> Automated crypto trading bot on Upbit — Daily RSI strategy with per-coin optimized parameters and trailing-stop validation via 8-year backtesting

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql)
![AWS EC2](https://img.shields.io/badge/AWS-EC2_t3.micro-orange?logo=amazonaws)
![Upbit](https://img.shields.io/badge/Exchange-Upbit-blue)

---

작업 요약·운영 메모(한글): [`MEMORY.md`](MEMORY.md) — 상세 변경 이력: [`PROGRESS.md`](PROGRESS.md).

## Overview

A fully automated cryptocurrency trading bot that runs 24/7 on AWS EC2. It monitors 15 coins every 60 seconds on Upbit (Korean exchange), executes buy/sell orders based on RSI signals, and manages risk with per-coin trailing-stop/stop-loss thresholds validated via historical backtesting.

**Key highlights:**
- RSI-based entry/exit strategy optimized per coin via grid search backtesting
- Regime filter: blocks altcoin buys when BTC shows multiple bearish signals
- Dynamic position sizing: regime-aware base ratio with seed-aware concentration cap
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

For small seed accounts, the runtime now favors concentration over broad diversification:
- new-buy universe is intentionally narrowed to the strongest core symbols
- max simultaneous positions are capped by total equity and `target_position_budget_krw`
- when multiple BUY signals appear together, deeper oversold signals with better backtest metadata are evaluated first
- RSI buy/sell decisions use the **last fully closed daily candle**, not the still-forming current candle
- once a daily BUY/SELL signal is executed, the same candle is locked to prevent same-day re-entry after an intraday stop

```
Every 60 seconds:
  ↓
BTC risk-off regime? → Block all altcoin buys
  ↓
RSI < buy_threshold  → BUY  (seed-aware 집중 배분, min/max configurable)
RSI > sell_threshold → SELL
  ↓
Real-time trailing-stop / stop-loss check (per-coin values)
  ↓
Time stop: hold too long without profit → SELL
```

---

## Per-coin Optimized Parameters

Parameters tuned via cached daily OHLCV data with conservative assumptions:
- Fee: `0.05%`
- Slippage: `0.05%`
- Validation: in-sample optimization + walk-forward + recent 180-day OOS check

| Coin | RSI Buy | RSI Sell | Trailing Activation | Stop Loss | Realistic Return |
|------|---------|----------|---------------------|-----------|------------------|
| BTC  | 35 | 65 | +1.5% | -5%  | -5.2%  |
| SOL  | 30 | 70 | +2.5% | -7%  | +6.2%  |
| DOGE | 30 | 70 | +3.5% | -5%  | +3.5%  |
| DOT  | 30 | 70 | +5.0% | -3%  | +4.1%  |
| ADA  | 30 | 55 | +5.0% | -3%  | +12.5% |
| AVAX | 30 | 70 | +3.5% | -10% | +1.1%  |
| LINK | 50 | 70 | +5.0% | -10% | +24.5% |
| TRX  | 40 | 70 | +5.0% | -7%  | +6.8%  |
| SUI  | 50 | 65 | +1.5% | -5%  | +11.6% |
| HBAR | 45 | 55 | +1.5% | -5%  | +16.5% |
| ICP  | 35 | 55 | +1.5% | -3%  | +0.2%  |
| ATOM | 30 | 55 | +3.5% | -3%  | +1.9%  |
| UNI  | 30 | 60 | +1.5% | -3%  | +8.3%  |
| SHIB | 40 | 70 | +3.5% | -5%  | -2.1%  |
| BCH  | 40 | 70 | +5.0% | -7%  | +22.2% |

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
│   ├── runtime_params.json  # Single source: buy universe, per-coin RSI & trailing/stop %
│   ├── runtime_params.py    # Load/cache RUNTIME_PARAMS_PATH or default JSON
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

# Step 4: Write a markdown report snapshot
python -m backtesting.reselect_runtime --write-report
```

Grid search ranges:
- RSI buy: `[30, 35, 40, 45, 50]`
- RSI sell: `[55, 60, 65, 70]`
- Stop loss: `[3%, 5%, 7%, 10%]`
- Trailing activation: `[1.5%, 2.5%, 3.5%, 5.0%]`
- Walk-forward: `train=720d`, `test=180d`, `step=180d`

## Recent OOS Snapshot

Cached-data recent 180-day OOS results remain soft overall, so runtime now prefers concentration over broad exposure:
- TRX `-0.6%`
- BCH `-2.2%`
- SOL `-3.0%`
- DOGE `-3.5%`
- LINK `-7.0%`

The practical takeaway is that the bot should hold fewer simultaneous positions and wait for stronger entries, rather than splitting a small seed across many symbols.

## Runtime configuration

- Per-coin **buy eligibility**, **RSI thresholds**, and **trailing-stop / stop-loss** percentages live in `backend/runtime_params.json`.
- Override the file path with env **`RUNTIME_PARAMS_PATH`** (optional).
- After research, merge universe flags and OOS metadata into that file (RSI/trailing unchanged) with:

```bash
PYTHONPATH=. python -m backtesting.reselect_runtime --write-backend
```

Restart the bot process after edits so the in-memory cache reloads.

Runtime research snapshots can be written to:
- `docs/superpowers/reports/YYYY-MM-DD-runtime-universe.md`

On EC2, the runtime report can also be scheduled daily via systemd timer:
- unit: `coinbot-runtime-report.timer`
- schedule: `00:15 UTC` daily (`09:15 KST`)
- server timer uses `--allow-fetch --auto-apply-runtime`
- if safety gates pass, it updates `backend/runtime_params.json` automatically
- if gates fail, it leaves params unchanged and records the blocked reason in the report
- timer also sends a Telegram summary for auto-apply success/block when bot credentials are configured
- verified on EC2: systemd one-shot run completed and logged `📨 sent Telegram notification`

## Runtime Universe

Current new-buy runtime universe is intentionally narrower, and the DB watchlist is auto-synced to match it:
- `KRW-LINK`
- `KRW-BCH`
- `KRW-ADA`

`KRW-BTC` is still used for regime detection, but is no longer eligible for new buys under the default runtime profile.

Selection is now score-based rather than threshold-only:
- rank by realistic return, walk-forward OOS, recent OOS, trade count, and drawdown penalty
- enable only the top `N` symbols that also pass minimum robustness gates
- default runtime profile uses `top_n=3`
- then apply a recent live-performance overlay:
  - look back `30` days
  - require at least `3` realized SELL trades
  - if realized P&L is negative and live win-rate / avg P&L stay weak, block new buys temporarily
- for prioritization, use `effective_selection_score = selection_score + live_score_adjustment`
- then apply loss-streak cooldown:
  - if recent SELL trades show `2+` consecutive losses
  - block new buys for `7` days

Other coins can still be held temporarily as existing positions. New entries are blocked, and the active watchlist is automatically aligned to:
- the runtime buy universe
- current held positions

## Risk caps (optional)

Configure via environment / `config.py`:

- **`max_open_positions`** — max distinct `positions` rows before new-symbol BUYs are skipped (default `12`, set `0` to disable).
- **`max_buys_per_day`** — max `BUY` rows in `trades` per KST calendar day (default `48`, set `0` to disable).
- **`target_position_budget_krw`** — seed-aware concentration cap. Example: `50,000` means total 자산 90,000원일 때 신규 포지션은 최대 1개, 120,000원일 때 최대 2개 수준으로 제한.
- **`min_order_amount_krw` / `max_order_amount_krw`** — 업비트 최소 주문/집중 매수 상한. `max_order_amount_krw=0`이면 상한 비활성화.

Upbit market orders use short retries for submit and polling until the order reports fill or timeout.

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
- 종목별 `selection_score`, `base_enabled`, `live_derated`
- 종목별 `live_score_adjustment`, `effective_selection_score`
- 종목별 `loss_streak_cooled`
- 종목별 `state_label`
- 최근 종목별 실현 성과 요약
- active watchlist 종목
- 최근 30일 실현손익 / 승률 / 매도 횟수

Telegram `/status` now also summarizes:
- currently selected symbols with `effective_selection_score`
- blocked symbols, tagged as `live` or `score`
- top symbol stateboard (`enabled`, `live-derated`, `streak-cooled`, `score-blocked`)

## Deprioritized Positions

Coins outside the runtime buy universe are not force-sold immediately.

Instead, if they are already held, the bot will prefer exiting them when either:
- unrealized P&L reaches `+1.0%` or better
- RSI reaches a weak sell zone

## Position Sizing

The bot now uses regime-aware sizing plus seed-aware concentration:
- `risk_on`: `20%`
- `caution`: `10%`
- `risk_off`: `5%`

Then it raises the order ratio when needed so that a small account does not get fragmented across too many positions. With the default `target_position_budget_krw=50,000`, total equity around `90,000 KRW` is effectively capped at one open position, and around `120,000 KRW` at two.

It also uses a simple time stop:
- `max_hold_days=10`
- `time_stop_min_pnl_pct=0.0`

If a position has been held for at least that many daily candles and is still below the minimum required P&L, the bot exits it on the next closed-candle evaluation.

For altcoins, `risk_off` still blocks new buys. The ratio is mainly relevant for BTC or future regime-aware expansions.

## Testing

```bash
PYTHONPATH=. pytest -q
```

Current local regression status:
- `66 passed`

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

Detailed operator guide: [docs/superpowers/telegram-commands.md](docs/superpowers/telegram-commands.md)

| Command | Description |
|---------|-------------|
| `/start` | Bot introduction + command summary |
| `/balance` | Current positions + KRW balance |
| `/status` | Runtime status, RSI, P&L, selection score, blocked summary |

Automated alerts: trade executions, low balance warnings, disk warnings, daily 9AM portfolio report, weekly P&L summary, runtime auto-apply result notifications.

---

## License

MIT
