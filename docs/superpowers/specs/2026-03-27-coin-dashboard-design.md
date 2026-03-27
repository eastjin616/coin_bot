# coin_bot AI 투자 대시보드 설계 문서

**날짜:** 2026-03-27
**상태:** 승인됨

---

## 개요

기존 coin_bot(FastAPI 자동매매 봇)에 Next.js 웹 대시보드를 추가한다. 핵심은 LangChain RAG Agent 기반 AI 채팅으로, 유저가 "이번 달 수익 어때?", "지금 BTC 사도 돼?" 같은 자연어 질문을 하면 AI가 실제 DB 데이터를 조회해 정확한 답변을 준다. 개인 사용 전용, 모바일/PC 반응형.

---

## 아키텍처

```
┌─────────────────────────────────┐
│        Next.js 14 (프론트)       │
│  - 대시보드 (가격, 포트폴리오)    │
│  - AI 채팅 UI                   │
│  - 매매 히스토리                 │
└──────────────┬──────────────────┘
               │ REST (X-API-Key 인증)
┌──────────────▼──────────────────┐
│       FastAPI (기존 coin_bot)    │
│  + /chat 엔드포인트 추가         │
│  + /api/portfolio 엔드포인트     │
│  + LangChain RAG Agent          │
│    - Tool: get_portfolio()      │
│    - Tool: get_trade_history()  │
│    - Tool: get_market_signal()  │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│     PostgreSQL (기존 DB)         │
│  - trades, watchlist 테이블 활용 │
└─────────────────────────────────┘
```

- 기존 coin_bot FastAPI 백엔드에 `/chat`, `/api/portfolio` 엔드포인트 추가
- LangChain Agent가 DB 툴을 호출해 실제 데이터 기반 답변 생성
- 통신은 REST만 사용 (WebSocket 제외, MVP 이후 고려)
- 프론트는 Vercel, 백엔드는 기존 EC2에 배포

---

## 보안

- **인증 방식**: API Key (`X-API-Key` 헤더) — FastAPI Middleware에서 검증, 환경변수로 관리
- **CORS**: `allow_origins`를 Vercel 배포 도메인으로 제한 (`https://<project>.vercel.app`)
- **환경변수**:
  - EC2 `.env`: `DASHBOARD_API_KEY=<random secret>`
  - Vercel: `NEXT_PUBLIC_API_URL=https://<ec2-domain>` (공개), `API_KEY=<same secret>` (서버사이드 전용)
- **중요**: Next.js 클라이언트 코드에서 EC2에 직접 요청하지 않는다. 반드시 Next.js API Route(`/api/*`) 서버사이드를 경유해 `API_KEY`를 붙여서 EC2에 전달. 이렇게 해야 브라우저에 API Key가 노출되지 않는다.

---

## 화면 구성 (반응형)

### 1. 메인 대시보드
- 상단: 원화 잔고 + 총 평가금액
- 중간: 보유 코인 카드 (코인명 / 현재가 / 수익률%)
- 하단: 최근 매매 내역 3건

### 2. AI 채팅
- 카카오톡 스타일 채팅 UI
- 추천 질문 버튼: "지금 BTC 사도 돼?", "이번주 수익 어때?", "제일 많이 번 코인이 뭐야?"
- 하단 텍스트 입력창

### 3. 히스토리
- 전체 매매 내역 테이블 (수익/손실 그래프는 MVP 이후)

---

## RAG Agent 설계

### 동작 흐름

```
유저 질문 → LangChain Agent → Tool 선택 → DB/API 조회 → Groq 답변 생성
```

예시:
- "이번 달 수익 어때?" → `get_trade_history(days=30)` → DB BUY/SELL 페어 집계 → 답변
- "지금 ETH 어때?" → `get_market_signal("KRW-ETH")` → 실시간 가격 + 최근 분석값 → 답변
- "내 포트폴리오 보여줘" → `get_portfolio()` → 업비트 잔고 + 현재가 → 답변

### Agent 툴 3개

| 툴 | 파라미터 | 구현 방법 |
|---|---|---|
| `get_portfolio()` | 없음 | `pyupbit.get_balances()` + 현재가 조회 → 평가금액 계산 |
| `get_trade_history(days)` | days: int | DB `trades` 테이블 BUY/SELL 페어 매칭 → 실현 수익 집계 |
| `get_market_signal(coin)` | coin: str | 실시간 가격 + DB 최근 `confidence` 값 재사용 (재분석 없음) |

### 수익 계산 방식
`trades` 테이블에 `profit` 컬럼 없음 → BUY/SELL 페어 매칭으로 실현 수익 계산:
```
수익 = (SELL price × quantity) - (직전 BUY 1건 price × quantity)
```
- 같은 symbol의 직전 BUY 1건과만 매칭 (복수 BUY 무시)
- 아직 SELL이 없는 미결 포지션은 집계에서 제외

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 프론트엔드 | Next.js 14 (App Router) + Tailwind CSS |
| 백엔드 | 기존 FastAPI + LangChain 0.3.x |
| LLM | Groq `meta-llama/llama-4-scout-17b-16e-instruct` (무료, langchain-groq 0.2.x) |
| DB | PostgreSQL (기존) |
| 프론트 배포 | Vercel |
| 백엔드 배포 | AWS EC2 (기존) |

---

## 구현 범위 (MVP)

포함:
- 대시보드 3개 화면 (반응형)
- LangChain Agent + 툴 3개
- FastAPI `/chat`, `/api/portfolio` 엔드포인트
- API Key 인증 미들웨어
- CORS Vercel 도메인 제한

제외 (MVP 이후):
- 로그인/회원가입 (API Key로 대체)
- WebSocket / 스트리밍 응답
- 히스토리 수익/손실 그래프
- 푸시 알림 (텔레그램으로 이미 커버)
- 멀티유저
