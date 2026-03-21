# coin_bot 구현 현황

## ✅ 완료된 작업

### Task 1: 프로젝트 기반 설정 (2026-03-21)
- requirements.txt: 필요한 패키지 목록 정의
- .env.example: 환경변수 템플릿 (API 키, DB 설정 등)
- backend/config.py: pydantic-settings로 환경변수 로드
- backend/database.py: PostgreSQL 연결 + 테이블 자동 생성 (trades, watchlist, cooldowns, positions)

### Task 2: AI 엔진 + 차트 생성기 (2026-03-21)
- backend/ai/vision_engine.py: notsure VisionEngine 재사용 + 모델 없을 시 랜덤 예측 모드
- backend/ai/chart_generator.py: yfinance(주식)/pyupbit(코인) 차트 이미지 생성

### Task 3: 텔레그램 봇 (2026-03-21)
- backend/telegram_bot.py: 매매 알림 및 명령어 처리
  - send_trade_alert(): 매수/매도 실행 시 포맷된 알림 메시지 전송 (주식: 📈/📉 아이콘, 코인: 🪙 아이콘)
  - send_message(): 허용된 chat_id에만 메시지 전송 (보안)
  - /start: 봇 소개 메시지
  - /balance: 현재 보유 포지션 조회 (허용된 사용자만)
  - 토큰/chat_id 미설정 시 경고 로그 후 건너뜀 (앱 중단 없음)

### Task 4: 코인 실행 엔진 (업비트) (2026-03-21)
- backend/execution/__init__.py: 패키지 초기화 파일
- backend/execution/coin_executor.py: 업비트 API 기반 자동매매 실행
  - API 키 없을 시 모의 모드로 동작 (실제 주문 없이 로그만 기록)
  - buy(): 잔고의 order_size_ratio만큼 시장가 매수, 최소 주문 5,000원 체크
  - sell(): 보유 수량 전체 시장가 매도
  - 체결 완료 후 trades, positions 테이블에 자동 저장
  - JWT 인증은 pyupbit 라이브러리가 처리

### Task 5: 주식 실행 엔진 (2026-03-21)
- backend/execution/stock_executor.py: yfinance 기반 주식 자동매매 실행
  - API 키 없을 시 모의 모드로 동작 (실제 주문 없이 로그 기록)
  - buy(): 현재가 조회 → 잔고의 50%로 수량 계산 → 시장가 매수
  - sell(): DB 포지션 조회 → 보유 수량 전체 매도
  - 체결 완료 후 trades, positions 테이블에 자동 저장

### Task 6: 오케스트레이터 (2026-03-21)
- backend/orchestrator.py: 주기적 폴링 → AI 신호 판단 → 자동 주문
  - APScheduler로 설정된 주기(기본 60초)마다 감시 종목 순회
  - 주식: KST 09:00~15:30 평일에만 실행 (pytz 시간대 처리)
  - 코인: 24시간 365일 실행
  - 신호 판단: buy_prob ≥ 80% → BUY, buy_prob < 20% → SELL, 나머지 → HOLD
  - 쿨다운: 종목별 N분 (BUY/SELL 각각 독립), PostgreSQL에 영속화
  - 매매 성공 시 텔레그램 알림 자동 발송
  - is_on_cooldown(), update_cooldown(), get_watchlist() 헬퍼 함수 포함

### Task 7: FastAPI 백엔드 + 라우터 (2026-03-21)
- backend/main.py: FastAPI 앱 진입점
  - lifespan으로 시작 시 DB 테이블 생성 + 오케스트레이터 자동 시작/종료
  - CORS 전체 허용 (개발 편의)
  - /api/trades, /api/watchlist, /api/signals, /api/balance 라우터 등록
- backend/routers/__init__.py: 라우터 패키지 초기화 파일
- backend/routers/trades.py: GET /api/trades — 최근 매매 내역 조회 (limit 파라미터)
- backend/routers/watchlist.py: GET/POST/DELETE /api/watchlist — 감시 종목 관리
  - POST: 중복 종목은 ON CONFLICT로 active=TRUE 복구
  - DELETE: 소프트 삭제 (active=FALSE)
- backend/routers/signals.py: GET /api/signals — 최근 AI 신호 조회 (market 필터 옵션)
- backend/routers/balance.py: GET /api/balance — 주식/코인 잔고 조회

### Task 8: React 프론트엔드 (2026-03-21)
- frontend/: Vite + React + TypeScript + Tailwind CSS 기반 UI
- frontend/src/api/client.ts: 백엔드 API 호출 함수 모음 (axios 기반)
- frontend/src/components/StockTab.tsx: 주식 탭 — 감시 종목 추가/삭제 + 최근 AI 신호 표시
- frontend/src/components/CoinTab.tsx: 코인 탭 — 감시 종목 추가/삭제 + 최근 AI 신호 표시
- frontend/src/App.tsx: 메인 앱 — 탭 네비게이션 + 실시간 잔고 표시 + 전체 매매 내역 테이블
  - 주식/코인/매매내역 3개 탭 구성
  - 헤더에 주식/코인 잔고 실시간 표시
  - 1분마다 자동 새로고침 (setInterval)

### 핫픽스: DB 드라이버 + 텔레그램 polling (2026-03-21)
- requirements.txt: psycopg2-binary → psycopg[binary] (Python 3.13 호환)
- backend/database.py: psycopg2 → psycopg3 문법으로 마이그레이션
- backend/main.py: 서버 시작 시 텔레그램 봇 polling 자동 시작
  - /start, /balance 명령어 실제 응답 확인 완료 ✅
- .gitignore: .env 파일 깃 추적 제외 (API 키 보안)

## 🎉 실제 동작 확인 (2026-03-21)
- PostgreSQL DB 연결 및 테이블 생성 완료
- 업비트 API 연결 완료
- 텔레그램 봇 @sdjtrader_bot 실제 응답 확인
- 오케스트레이터 1분 주기 자동 실행 중

## 📋 다음 작업 (예정)
- 기술적 지표(이동평균선 등) 기반 신호 로직 강화 (현재 랜덤 예측 모드)
- AI 모델 학습 또는 기술적 지표로 대체

