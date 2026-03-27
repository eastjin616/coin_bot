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
               │ REST / WebSocket
┌──────────────▼──────────────────┐
│       FastAPI (기존 coin_bot)    │
│  + /chat 엔드포인트 추가         │
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

- 기존 coin_bot FastAPI 백엔드에 `/chat` 엔드포인트만 추가
- LangChain Agent가 DB 툴을 호출해 실제 데이터 기반 답변 생성
- 프론트는 Vercel, 백엔드는 기존 EC2에 배포

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
- 전체 매매 내역 테이블
- 기간별 수익/손실 그래프

---

## RAG Agent 설계

### 동작 흐름

```
유저 질문 → LangChain Agent → Tool 선택 → DB 조회 → Groq 답변 생성
```

예시:
- "이번 달 수익 어때?" → `get_trade_history(days=30)` → DB 집계 → 답변
- "지금 ETH 어때?" → `get_market_signal("KRW-ETH")` → 실시간 가격 + AI 분석값 → 답변
- "내 포트폴리오 보여줘" → `get_portfolio()` → 업비트 잔고 조회 → 답변

### Agent 툴 3개

| 툴 | 파라미터 | 하는 일 |
|---|---|---|
| `get_portfolio()` | 없음 | 현재 보유 코인 + 평가금액 (업비트 API) |
| `get_trade_history(days)` | days: int | N일치 매매 내역 + 수익 집계 (DB) |
| `get_market_signal(coin)` | coin: str | 실시간 가격 + AI 분석값 (업비트 + Groq) |

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 프론트엔드 | Next.js 14 (App Router) + Tailwind CSS |
| 백엔드 | 기존 FastAPI + LangChain |
| LLM | Groq llama-4-scout-17b (무료) |
| DB | PostgreSQL (기존) |
| 프론트 배포 | Vercel |
| 백엔드 배포 | AWS EC2 (기존) |

---

## 구현 범위 (MVP)

포함:
- 대시보드 3개 화면
- LangChain Agent + 툴 3개
- FastAPI `/chat` 엔드포인트
- 모바일/PC 반응형

제외 (MVP 이후):
- 로그인/인증 (개인용이므로 IP 제한으로 대체)
- 푸시 알림 (텔레그램으로 이미 커버)
- 멀티유저
