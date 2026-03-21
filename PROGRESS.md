# coin_bot 구현 현황

## ✅ 완료된 작업

### Task 1: 프로젝트 기반 설정 (2026-03-21)
- requirements.txt: 필요한 패키지 목록 정의
- .env.example: 환경변수 템플릿 (API 키, DB 설정 등)
- backend/config.py: pydantic-settings로 환경변수 로드
- backend/database.py: PostgreSQL 연결 + 테이블 자동 생성 (trades, watchlist, cooldowns, positions)

## 🔄 진행 중인 작업
- Task 2: AI 엔진 + 차트 생성기

## 📋 남은 작업
- Task 3: 텔레그램 봇
- Task 4: 코인 실행 엔진 (업비트)
- Task 5: 주식 실행 엔진
- Task 6: 오케스트레이터
- Task 7: FastAPI 백엔드
- Task 8: React 프론트엔드
