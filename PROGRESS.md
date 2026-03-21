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

## 🔄 진행 중인 작업
- Task 4: 코인 실행 엔진 (업비트)

## 📋 남은 작업
- Task 4: 코인 실행 엔진 (업비트)
- Task 5: 주식 실행 엔진
- Task 6: 오케스트레이터
- Task 7: FastAPI 백엔드
- Task 8: React 프론트엔드

