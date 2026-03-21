# coin_bot 구현 현황

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

### 3. 프론트엔드 시작 (별도 터미널)
```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot/frontend
npm install   # 처음 한 번만
npm run dev
```
브라우저에서 http://localhost:5174 접속

### 4. 백그라운드로 돌리고 싶을 때
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

### Task 8: React 프론트엔드 (2026-03-21)
- frontend/: Vite + React + TypeScript + Tailwind CSS
- CoinTab.tsx: 잔고 카드 + 수동 매수 패널 (금액 입력, 빠른 버튼) + 감시 종목 매도 버튼
- App.tsx: 주식 탭 비활성화, 코인/매매내역 2탭, 헤더 잔고 실시간 표시, 1분 자동 새로고침

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
rsync -avz --exclude='.env' --exclude='__pycache__' --exclude='frontend/node_modules' --exclude='.git' \
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

## 🎉 현재 동작 중 (2026-03-21)
- EC2 서버: http://43.203.227.201 (24시간)
- **5분마다** BTC/ETH/SOL/XRP/DOGE GPT-4.1-mini 차트 분석 중 (1분→5분, 비용 1/5)
- 텔레그램 @sdjtrader_bot 매매 알림 대기 중
- 업비트 잔고 ~25,000원 운용 중
- 매수 임계값 70%, 매도 임계값 20%
- 매수 금액: 고정 5,000원씩 (잔고 50% 방식 → 고정 금액으로 변경)
- OpenAI 잔액 소진 시 Groq llama-3.2-vision으로 자동 폴백 (무료)

## 📋 개선 아이디어
- 임계값 조정 (현재 80% BUY — 시장 상황에 따라 70%로 낮출 수 있음)
- 분봉 단위 변경 (현재 1시간봉 → 15분봉으로 더 빠른 반응)
- 손절/익절 자동화 (현재 AI 신호에만 의존)
