# coin_bot 구현 현황

## 2026-03-22: 폴링 주기 단축

### 변경 내용
- **폴링 주기 5분 → 1분으로 단축** (EC2 `.env` `POLL_INTERVAL_SECONDS=60`)
  - Groq 무료 폴백 있어서 OpenAI 소진 후에도 비용 걱정 없음
  - 쿨다운 5분 유지 → 과매매 없이 신호 감지만 빨라짐

---

## 2026-03-21: API 비용 최적화 + 매매 전략 업그레이드

### 변경 내용
- **변동성 필터 추가**: RSI 중립(45~55) + 거래량 보합 + MA 차이 0.5% 미만이면 GPT 호출 skip
  - BTC/ETH: 더 좁은 중립 범위(48~52) → 더 자주 분석
  - 최대 30분 연속 skip 방지 (기회 완전 누락 차단)
  - 한 번도 분석 안 된 코인은 항상 분석 (초기 상태 버그 수정 포함)
- **RSI 기반 동적 임계값**: RSI<30 → 65%, 중립 → 80%, RSI>70 → 85%
- **호출 순서 개선**: indicators 먼저 → 필터 → chart 생성 → GPT (불필요한 pyupbit 호출 제거)
- **롤백 플래그**: .env에서 `ENABLE_VOLATILITY_FILTER=false` / `ENABLE_DYNAMIC_THRESHOLD=false` 설정 후 서비스 재시작으로 비활성화 가능

### 예상 효과
- GPT 호출 평균 37% 감소 (횡보장 최대 50%)
- 과매도 구간 매수 기회 확대, 과매수 추격 매수 방지

### 테스트
- 16개 단위 테스트 추가 (tests/test_orchestrator.py)
- TestShouldSkipAnalysis (10개): 변동성 필터 로직 검증
- TestGetDynamicThresholds (6개): 동적 임계값 로직 검증

## 🚀 실행 방법

### 사전 조건
- Python 3.13, Node.js, PostgreSQL (brew 설치)
- `.env` 파일 설정 완료 (아래 참고)

### 1. PostgreSQL 시작
```bash
brew services start postgresql@16
```

### 2. 백엔드 서버 시작
```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot

# 패키지 설치 (처음 한 번만)
pip install -r requirements.txt

# 서버 실행 (포트 8002)
uvicorn backend.main:app --port 8002
```
서버가 뜨면 자동으로:
- DB 테이블 생성
- 오케스트레이터 시작 (1분마다 AI 분석)
- 텔레그램 봇 polling 시작

### 3. 백그라운드로 돌리고 싶을 때
```bash
# 백엔드 백그라운드 실행
uvicorn backend.main:app --port 8002 > /tmp/coinbot.log 2>&1 &

# 로그 실시간 확인
tail -f /tmp/coinbot.log

# 서버 종료
lsof -ti:8002 | xargs kill -9
```

### 5. .env 파일 설정 항목
```
DATABASE_URL=postgresql://seodongjin:1234@localhost:5432/coinbot
UPBIT_ACCESS_KEY=업비트_액세스_키
UPBIT_SECRET_KEY=업비트_시크릿_키
TELEGRAM_BOT_TOKEN=텔레그램_봇_토큰
TELEGRAM_ALLOWED_CHAT_IDS=텔레그램_chat_id
OPENAI_API_KEY=OpenAI_API_키           ← GPT-4.1-mini로 차트 분석
GEMINI_API_KEY=Gemini_API_키           ← (선택) Gemini 사용 시
SIGNAL_BUY_THRESHOLD=80.0             ← 이 값 이상이면 자동 매수
SIGNAL_SELL_THRESHOLD=20.0            ← 이 값 미만이면 자동 매도
COOLDOWN_MINUTES=5                    ← 같은 종목 재매매 대기 시간
POLL_INTERVAL_SECONDS=60              ← AI 분석 주기 (초)
ORDER_SIZE_RATIO=0.5                  ← 잔고의 몇 %를 1회 주문에 사용
COIN_BUDGET_KRW=50000                 ← 모의모드 시 사용되는 가상 잔고
```

### 6. API 엔드포인트
| 주소 | 설명 |
|------|------|
| GET /api/balance | 현재 잔고 조회 |
| GET /api/watchlist | 감시 종목 목록 |
| POST /api/watchlist | 종목 추가 (body: market, symbol, name) |
| DELETE /api/watchlist/{market}/{symbol} | 종목 삭제 |
| GET /api/trades | 매매 내역 조회 |
| GET /api/signals | AI 신호 내역 |
| POST /api/test/buy/{symbol}?amount=10000 | 수동 매수 테스트 |
| POST /api/test/sell/{symbol} | 수동 매도 테스트 |

---

## ✅ 완료된 작업

### Task 1: 프로젝트 기반 설정 (2026-03-21)
- requirements.txt: 필요한 패키지 목록 정의
- .env.example: 환경변수 템플릿 (API 키, DB 설정 등)
- backend/config.py: pydantic-settings로 환경변수 로드
- backend/database.py: PostgreSQL 연결 + 테이블 자동 생성 (trades, watchlist, cooldowns, positions)

### Task 2: AI 엔진 + 차트 생성기 (2026-03-21)
- backend/ai/vision_engine.py: CNN 기반 VisionEngine (학습 모델 없을 시 랜덤 모드)
- backend/ai/chart_generator.py: yfinance(주식)/pyupbit(코인) 캔들차트 이미지 생성
  - RSI(14), MA5, MA20, 거래량 추세 기술지표 계산 함수 포함

### Task 3: 텔레그램 봇 (2026-03-21)
- backend/telegram_bot.py: 매매 알림 및 명령어 처리
  - send_trade_alert(): 매수/매도 실행 시 포맷된 알림 메시지 전송
  - /start: 봇 소개 메시지
  - /balance: 현재 보유 포지션 조회 (허용된 사용자만)
  - 텔레그램 봇: @sdjtrader_bot

### Task 4: 코인 실행 엔진 - 업비트 (2026-03-21)
- backend/execution/coin_executor.py: 업비트 API 기반 자동매매
  - buy(): 잔고의 order_size_ratio만큼 시장가 매수, 최소 5,000원 체크
  - buy_fixed_amount(): 금액 직접 지정 매수
  - sell(): 보유 수량 전체 시장가 매도
  - 체결 후 trades, positions 테이블 자동 저장

### Task 5: 주식 실행 엔진 (2026-03-21)
- backend/execution/stock_executor.py: yfinance 기반 주식 자동매매 (모의 모드)

### Task 6: 오케스트레이터 (2026-03-21)
- backend/orchestrator.py: 주기적 폴링 → AI 신호 판단 → 자동 주문
  - APScheduler로 60초마다 감시 종목 순회
  - 주식: KST 09:00~15:30 평일에만 실행
  - 코인: 24시간 365일 실행
  - 신호 판단: buy_prob ≥ 80% → BUY / buy_prob < 20% → SELL / 나머지 → HOLD
  - 쿨다운: 종목별 5분 (BUY/SELL 각각 독립), DB에 영속화
  - 매매 성공 시 텔레그램 알림 자동 발송

### Task 7: FastAPI 백엔드 + 라우터 (2026-03-21)
- backend/main.py: FastAPI 앱 진입점, lifespan으로 오케스트레이터 + 텔레그램 자동 시작
- backend/routers/trades.py, watchlist.py, signals.py, balance.py, test_trade.py

### LLM Vision AI 엔진 (2026-03-21)
- backend/ai/llm_engine.py: GPT-4.1-mini / Gemini / Claude Vision으로 차트 분석
  - 우선순위: OpenAI → Gemini → Claude → 랜덤 폴백
  - 캔들차트 이미지(base64) + RSI/MA/거래량 텍스트 지표를 함께 LLM에 전송
  - 매수 확률 0~100% 파싱
- 실제 동작 확인: BTC 70%, ETH 70%, SOL 65%, XRP 60%, DOGE 60% ✅
- 감시 종목: BTC, ETH, SOL, XRP, DOGE (5개)
- 업비트 잔고 10,000원 입금 후 실전 대기 중

### AWS EC2 배포 (2026-03-21)
- 서버: AWS EC2 t3.micro (ap-northeast-2, 서울)
- IP: 43.203.227.201 / 포트: 80 (HTTP 기본)
- systemd 서비스로 등록 → 서버 재부팅 시 자동 재시작
- 맥북 꺼도 24시간 자동매매 동작
- 업비트 API 허용 IP: 43.203.227.201 등록 완료

---

## ========== 사용법 및 EC2 관리 ==========

### SSH 접속
```bash
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201
```

### 로그 확인
```bash
# 실시간 로그 (나가려면 Ctrl+C)
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201 "sudo journalctl -u coinbot -f"

# 최근 50줄만 보기
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201 "sudo journalctl -n 50 -u coinbot --no-pager"

# 오류만 필터링
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201 "sudo journalctl -u coinbot --no-pager | grep -i error"
```

### 서버 재시작
```bash
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201 "sudo systemctl restart coinbot"
```

### 코드 수정 후 배포
```bash
# 1. 코드 EC2로 전송
rsync -avz --exclude='.env' --exclude='__pycache__' --exclude='.git' \
  -e "ssh -i ~/Downloads/coin-bot-key.pem" \
  /Users/seodongjin/Documents/GitHub/coin_bot/ ubuntu@43.203.227.201:~/coin_bot/

# 2. 서버 재시작
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201 "sudo systemctl restart coinbot"
```

### 서비스 상태 확인
```bash
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201 "sudo systemctl status coinbot"
```

---

## 🎉 현재 동작 중 (2026-03-21 최신)
- EC2 서버: http://43.203.227.201 (24시간)
- **1분마다** BTC/ETH/SOL/XRP/DOGE 순회 — 변동성 필터 통과 시에만 GPT 분석
  - RSI 중립 + 거래량 보합 + MA 평탄 → GPT 호출 skip (평균 ~37% 절감)
  - BTC/ETH: 더 자주 분석 (tight RSI 범위 48~52)
- **동적 임계값:** RSI<30 → 매수 65%, 중립 → 80%, RSI>70 → 85% (매도는 항상 20%)
- 텔레그램 @sdjtrader_bot 매매 알림 + /balance 잔고조회
- 업비트 잔고 운용 중
- 매수 금액: 고정 5,000원씩
- 익절 +10%, 손절 -5% 자동 매도 (.env에서 조정 가능)
- OpenAI 잔액 소진 시 Groq llama-3.2-vision으로 자동 폴백 (무료)
- 긴급 롤백: `.env`에 `ENABLE_VOLATILITY_FILTER=false` 추가 후 재시작

## ⚠️ 비용 및 리스크
- **OpenAI API:** $6.64 잔액 (2026-03-21 기준), 변동성 필터 적용으로 ~$0.32/day 예상 (기존 ~$0.50/day → 37% 절감)
- **AWS EC2:** 프리티어 2026년 7월 초 만료 → 이후 월 ~$13 발생
- **Groq:** 무료, OpenAI 소진 시 자동 폴백
- **손절 -5% / 익절 +10%** 설정으로 큰 손실 방어

## 🔖 미결 사항 (TODO)

### 🟢 여유 있을 때
- [ ] **OpenAI → Groq 전환 텔레그램 알림**: 자동 폴백은 되지만 알림은 없음 (로그로 확인 가능, 급하지 않음)
- [ ] **EC2 보안그룹 강화**: SSH(22)/HTTP(80) 현재 0.0.0.0/0 전체 오픈
  - SSH는 본인 IP만 허용으로 변경 권장
- [ ] **재시작 후 GPT 버스트 완화**: 서비스 재시작 시 `_last_analyzed` 초기화 → 5개 코인 동시 GPT 호출
  - 코인별 시작 딜레이 추가 또는 DB에 last_analyzed 영속화로 해결 가능
- [ ] **분봉 단위 변경**: 현재 1시간봉 → 15분봉으로 더 빠른 반응
- [ ] **매수 금액 동적 조정**: 잔고 비례 (현재 고정 5,000원)
