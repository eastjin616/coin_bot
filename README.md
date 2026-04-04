# coin_bot 🤖

> 업비트 기반 코인 자동매매 봇 — 일봉 RSI 전략 + 코인별 파라미터 최적화
>
> Automated crypto trading bot on Upbit — Daily RSI strategy with per-coin optimized parameters

---

## 전략 개요 / Strategy Overview

순수 기술적 지표(RSI) 기반 자동매매. AI 없이 백테스팅으로 최적화된 파라미터 사용.

Pure technical indicator (RSI) based trading. No AI — parameters optimized via backtesting on 8 years of daily candle data.

```
매 60초마다 15개 코인 순회
  ↓
BTC RSI < 40? → 하락장 판단 → 알트코인 매수 전체 차단
  ↓
코인별 RSI 계산 (일봉 200개)
  ├─ RSI < 매수 임계값 → 매수 (잔고 × 20%, 최소 1만 / 최대 5만)
  ├─ RSI > 매도 임계값 → 매도
  └─ 그 외 → HOLD
  ↓
익절/손절 실시간 체크 (코인별 최적값 적용)
```

---

## 코인별 최적 파라미터 / Per-coin Parameters

백테스팅 8년치 그리드서치 결과 (업비트 일봉).

Optimized via grid search on 8 years of Upbit daily candle data.

| 코인 | RSI 매수 | RSI 매도 | 익절 | 손절 | 백테스팅 수익률 |
|------|---------|---------|------|------|--------------|
| BTC  | 50      | 65      | +5%  | -3%  | +3.5%        |
| SOL  | 35      | 55      | +10% | -3%  | +5.7%        |
| DOGE | 35      | 55      | +5%  | -5%  | +8.9%        |
| DOT  | 35      | 55      | +5%  | -3%  | +0.9%        |
| ADA  | 35      | 55      | +5%  | -3%  | +3.1%        |
| AVAX | 45      | 70      | +8%  | -5%  | +5.8%        |
| LINK | 50      | 70      | +15% | -10% | +33.0%       |
| TRX  | 35      | 55      | +5%  | -10% | +4.8%        |
| SUI  | 50      | 70      | +15% | -5%  | +8.0%        |
| HBAR | 45      | 70      | +20% | -5%  | +17.9%       |
| ICP  | 35      | 55      | +5%  | -3%  | +0.3%        |
| ATOM | 45      | 60      | +15% | -5%  | +11.5%       |
| UNI  | 50      | 65      | +25% | -3%  | +6.4%        |
| SHIB | 50      | 60      | +8%  | -5%  | +6.3%        |
| BCH  | 40      | 60      | +15% | -3%  | +18.0%       |

> ETH, XRP, NEAR, OP — 백테스팅 음수로 감시 제외

---

## 주요 기능 / Features

- **코인별 RSI 최적화** — 코인마다 다른 매수/매도 임계값 적용
- **코인별 익절/손절 최적화** — 변동성 특성에 맞는 리스크 파라미터
- **BTC 하락장 필터** — BTC RSI < 40이면 알트코인 매수 전체 차단
- **복리 매수** — 잔고 × 20% 동적 매수금액 (최소 10,000원 / 최대 50,000원)
- **좀비 포지션 자동 정리** — 실제 잔고 없는 DB 포지션 자동 삭제
- **텔레그램 알림** — 매수/매도/잔고부족/오류 실시간 알림
- **24시간 자동매매** — AWS EC2 systemd 서비스

---

## 텔레그램 명령어 / Telegram Commands

| 명령어 | 설명 |
|--------|------|
| `/balance` | KRW 잔고 + 보유 포지션 조회 |
| `/status` | 포지션별 현재 RSI + 미실현 손익 |

**자동 알림:**
- 매수/매도 체결 시 즉시 알림 (종목, 체결가, RSI, 수익률)
- 잔고 부족으로 매수 기회 놓칠 때 (4시간마다 1회)
- 동일 오류 3회 연속 발생 시 경고
- 매일 오전 9시 KST — 포지션 현황 + 미실현 손익
- 매주 월요일 오전 9시 KST — 주간 수익률 리포트
- 매시간 디스크 사용량 체크 (80% 초과 시 경고)

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
# RSI 임계값 최적화 (1단계)
python -m backtesting.optimize

# 익절/손절 최적화 (2단계)
python -m backtesting.optimize risk
```

업비트 일봉 최대 3000개(~8년) 데이터 기준 그리드서치.

Grid search on up to 3,000 daily candles (~8 years) from Upbit.

---

## 로컬 실행 / Local Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # API 키 입력
brew services start postgresql@16
uvicorn backend.main:app --port 8002
```

---

## .env 설정

```env
DATABASE_URL=postgresql://user:password@localhost:5432/coinbot
UPBIT_ACCESS_KEY=업비트_액세스_키
UPBIT_SECRET_KEY=업비트_시크릿_키
TELEGRAM_BOT_TOKEN=텔레그램_봇_토큰
TELEGRAM_ALLOWED_CHAT_IDS=텔레그램_chat_id

# 전략 파라미터 (코인별 오버라이드가 우선 적용됨)
RSI_BUY_THRESHOLD=35
RSI_SELL_THRESHOLD=55
TAKE_PROFIT_PERCENT=10.0
STOP_LOSS_PERCENT=5.0
COOLDOWN_MINUTES=5
POLL_INTERVAL_SECONDS=60
```

---

## 배포 / Deployment

```bash
# EC2에 배포 (.env 제외)
rsync -av --exclude='.git' --exclude='venv' --exclude='__pycache__' \
  --exclude='.env' --exclude='backtesting/data' \
  ./ ubuntu@<EC2_IP>:/home/ubuntu/coin_bot/ \
  -e "ssh -i <PEM_KEY>"

# 서비스 재시작
ssh -i <PEM_KEY> ubuntu@<EC2_IP> "sudo systemctl restart coinbot"
```

---

## 프로젝트 구조 / Project Structure

```
coin_bot/
├── backend/
│   ├── ai/
│   │   └── chart_generator.py   # RSI/MA 지표 계산
│   ├── execution/
│   │   └── coin_executor.py     # 업비트 매수/매도 실행
│   ├── routers/                 # FastAPI 라우터
│   ├── config.py                # 환경변수 설정
│   ├── database.py              # PostgreSQL 연결
│   ├── orchestrator.py          # 핵심 자동매매 루프
│   ├── telegram_bot.py          # 텔레그램 알림 + 명령어
│   └── main.py                  # FastAPI 앱 진입점
├── backtesting/
│   ├── data_fetcher.py          # 업비트 일봉 데이터 수집
│   ├── simulator.py             # 백테스팅 시뮬레이터
│   ├── indicators.py            # RSI/MA 지표 계산
│   └── optimize.py              # 파라미터 그리드서치
└── tests/
```
