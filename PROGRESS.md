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

## 🔄 진행 중인 작업
- Task 7: FastAPI 백엔드

## 📋 남은 작업
- Task 7: FastAPI 백엔드
- Task 8: React 프론트엔드

