# coin_bot 🤖

GPT-4.1-mini Vision 기반 코인 자동매매 시스템.
업비트 API + 캔들차트 이미지 + 기술지표(RSI/MA/거래량)를 LLM에 전송해 매수 확률을 계산하고 자동으로 매매합니다.

## 주요 기능

- **AI 차트 분석**: 캔들차트 이미지 + RSI/MA/거래량 지표를 GPT-4.1-mini Vision에 전송 → 매수 확률 0~100% 반환
- **변동성 필터**: RSI 중립 + 거래량 보합 + MA 평탄 구간은 GPT 호출 skip → API 비용 ~37% 절감
- **동적 매수 임계값**: RSI<30 → 65%, 중립 → 80%, RSI>70 → 85% (시장 상황별 자동 조정)
- **자동 익절/손절**: 익절 +10%, 손절 -5% 자동 매도
- **LLM 폴백**: OpenAI 잔액 소진 시 Groq llama-3.2-vision으로 자동 전환 (무료)
- **텔레그램 알림**: 매수/매도 실행 시 실시간 알림 + `/balance` 잔고조회
- **24시간 자동매매**: AWS EC2에 systemd 서비스로 배포

## 감시 종목

BTC, ETH, SOL, XRP, DOGE — 5분마다 순회

## 기술 스택

| 영역 | 기술 |
|------|------|
| 백엔드 | FastAPI, APScheduler, psycopg3 |
| DB | PostgreSQL |
| AI | GPT-4.1-mini Vision, Groq llama-3.2-vision |
| 코인 거래소 | 업비트 (pyupbit) |
| 알림 | Telegram Bot API |
| 배포 | AWS EC2 t3.micro (서울), systemd |

## 동작 방식

```
5분마다 BTC/ETH/SOL/XRP/DOGE 순회
  ↓
기술지표 계산 (RSI, MA5/MA20, 거래량)
  ↓
변동성 필터 통과 여부 판단
  ├─ skip → 다음 코인으로
  └─ 통과 → 캔들차트 생성 → GPT 분석 → 매수 확률 반환
              ↓
        동적 임계값 비교
          ├─ 매수 확률 ≥ 임계값 → 5,000원 매수
          ├─ 매수 확률 < 20% → 매도
          └─ 나머지 → HOLD
```

## 로컬 실행

### 1. 환경 설정

```bash
pip install -r requirements.txt
cp .env.example .env  # .env 파일에 API 키 입력
```

### 2. PostgreSQL 시작

```bash
brew services start postgresql@16
```

### 3. 서버 실행

```bash
uvicorn backend.main:app --port 8002
```

서버 시작 시 자동으로:
- DB 테이블 생성
- 오케스트레이터 시작 (5분마다 AI 분석)
- 텔레그램 봇 polling 시작

## .env 설정

```env
DATABASE_URL=postgresql://user:password@localhost:5432/coinbot
UPBIT_ACCESS_KEY=업비트_액세스_키
UPBIT_SECRET_KEY=업비트_시크릿_키
TELEGRAM_BOT_TOKEN=텔레그램_봇_토큰
TELEGRAM_ALLOWED_CHAT_IDS=텔레그램_chat_id
OPENAI_API_KEY=OpenAI_API_키
GROQ_API_KEY=Groq_API_키

# 매매 설정
SIGNAL_BUY_THRESHOLD=80.0        # 매수 임계값 (동적 임계값 비활성화 시 사용)
SIGNAL_SELL_THRESHOLD=20.0       # 매도 임계값
COOLDOWN_MINUTES=5               # 종목별 재매매 대기 시간
COIN_BUDGET_KRW=5000             # 1회 매수 금액 (원)

# 기능 플래그
ENABLE_VOLATILITY_FILTER=true    # 변동성 필터 (false로 롤백 가능)
ENABLE_DYNAMIC_THRESHOLD=true    # 동적 임계값 (false로 롤백 가능)
```

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/balance` | 현재 잔고 조회 |
| GET | `/api/watchlist` | 감시 종목 목록 |
| POST | `/api/watchlist` | 종목 추가 |
| DELETE | `/api/watchlist/{market}/{symbol}` | 종목 삭제 |
| GET | `/api/trades` | 매매 내역 조회 |
| GET | `/api/signals` | AI 신호 내역 |
| POST | `/api/test/buy/{symbol}?amount=10000` | 수동 매수 테스트 |
| POST | `/api/test/sell/{symbol}` | 수동 매도 테스트 |

## 테스트

```bash
python -m pytest tests/test_orchestrator.py -v
```

- `TestShouldSkipAnalysis` (10개): 변동성 필터 로직
- `TestGetDynamicThresholds` (6개): 동적 임계값 로직

## 프로젝트 구조

```
coin_bot/
├── backend/
│   ├── ai/
│   │   ├── chart_generator.py   # 캔들차트 + 기술지표 생성
│   │   ├── llm_engine.py        # GPT/Groq Vision 호출
│   │   └── vision_engine.py     # Vision 엔진 래퍼
│   ├── execution/
│   │   └── coin_executor.py     # 업비트 매수/매도 실행
│   ├── routers/                 # FastAPI 라우터
│   ├── config.py                # 환경변수 로드
│   ├── database.py              # PostgreSQL 연결 + 테이블 생성
│   ├── orchestrator.py          # 핵심 자동매매 루프
│   ├── telegram_bot.py          # 텔레그램 알림 + 명령어
│   └── main.py                  # FastAPI 앱 진입점
├── tests/
│   └── test_orchestrator.py
├── requirements.txt
└── .env.example
```
