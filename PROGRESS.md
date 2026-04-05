# coin_bot 구현 현황

## 2026-04-05: 트레일링 스탑 도입 (고정 익절 제거)

### 변경 내용 (`orchestrator.py`, `coin_executor.py`, `database.py`)
- 기존 고정 익절(+5~25%) 제거 → 트레일링 스탑으로 대체
- `positions` 테이블에 `highest_price` 컬럼 추가
- 트레일링 로직:
  - 손절: `entry_price` 기준 `-stop_loss%` (기존 유지)
  - 트레일링 활성화: `highest_price >= entry_price × (1 + stop_loss/200)`
  - 트레일링 발동: `current_price <= highest_price × (1 - stop_loss/100)`
- 트레일링/손절 텔레그램 알림 구분 (📉 트레일링 스탑 / 🛑 손절)
- `_check_profit_stop()` 반환 타입 `tuple[action, reason, highest_price]`로 개선 (race condition 제거)
- 기존 운영 포지션 6개 `highest_price` → `entry_price`로 자동 초기화

---

## 2026-04-05: 중복 매수 버그 수정 + 손익 기록 추가 + README 포트폴리오 강화

### 중복 매수 버그 수정 (`orchestrator.py`)
- 원인: 쿨다운(5분) 만료 후 RSI가 여전히 낮으면 같은 코인 재매수 → SOL/DOT 각 30,000원 몰빵
- 수정: `analyze_and_trade()`에 포지션 보유 중 재매수 차단 로직 추가
  - BUY 신호 발생 시 `_has_position()` 확인 → 이미 보유 중이면 HOLD 처리
  - 코인 매도 후에만 재진입 가능

### 매도 손익 DB 기록 추가 (`coin_executor.py`, `database.py`)
- trades 테이블에 `pnl_krw`, `pnl_pct` 컬럼 추가
- 매도 시 entry_price 기준 실현 손익(원/%) 자동 계산 후 저장
- 이후 수익률 분석, 주간 리포트 활용 가능

### README 포트폴리오 강화 (`README.md`)
- 아키텍처 다이어그램 (ASCII) 추가
- 전략 플로우, 코인별 파라미터 테이블, 백테스터 설명 정리
- 로컬 셋업 가이드, 텔레그램 명령어 추가
- 레포 public 전환 (포트폴리오용)

### EC2 DB 현황 (2026-04-05)
- 보유 포지션 6개: ATOM(10K), BTC(25K), DOT(30K), LINK(10K), SOL(30K), SUI(10K)
- 총 투자: 약 115,000원
- KRW 잔고: 0원 (수동 매수로 소진)

---

## 2026-04-05: MA Cross 조건 제거 — RSI 단독 전략 복귀

### MA Cross 진입 조건 제거 (`orchestrator.py`)
- 기존 BUY 조건: RSI < 임계값 AND MA5 > MA20 → 동시 성립 불가
  - RSI 낮음(과매도) = 최근 가격 하락 = MA5 < MA20(하락추세) → 항상 충돌
  - 예: DOT RSI 10.0 극단적 과매도에도 MA Cross 미충족으로 매수 차단되던 문제
- 변경: RSI < 임계값 단독 조건으로 단순화 (백테스팅 기반 원래 설계로 복귀)
- 매수 진입 빈도 정상화 기대

---

## 2026-04-05: 버그 수정 + 전략 고도화 (8건)

### 1. 익절/손절 오류 수정 (`orchestrator.py`)
- `_check_profit_stop()`에서 `get_db_conn()` 미import로 매 사이클마다 오류 발생
- `with get_db() as conn:` 패턴으로 교체 → 익절/손절 정상 동작

### 2. 좀비 포지션 자동 DB 정리 (`orchestrator.py`)
- `_cleanup_zombie_positions()` 추가: DB에 포지션 있지만 실제 업비트 잔고 없는 경우 자동 삭제
- 매 사이클마다 실행, 감지 시 텔레그램 알림

### 3. 잔고 부족 시 텔레그램 알림 (`orchestrator.py`)
- BUY 신호 발생 시 잔고 10,000원 미만이면 텔레그램 알림 (4시간마다 1회, 스팸 방지)

### 4. 전체 코인 백테스팅 + RSI 최적화 (`orchestrator.py`, `backtesting/optimize.py`)
- SYMBOLS 5개 → 전체 18개 코인으로 확장
- 결과: LINK +30.5%(50/70), BCH +17.0%(40/60), HBAR +13.2%(45/70), ATOM +10.3%(45/60)
- `_RSI_OVERRIDES` 1개 → 9개 코인 개별 최적 RSI 적용
- NEAR(-6.0%), OP(-2.0%) watchlist 비활성화 → 감시 15개 코인으로 축소

### 5. BTC 하락장 필터 + 복리 매수 (`orchestrator.py`, `coin_executor.py`)
- BTC RSI < 40이면 알트코인 전체 매수 차단 (익절/손절은 유지)
- 고정 10,000원 → 잔고 × 20% (최소 10,000원 / 최대 50,000원) 동적 매수금액

### 6. 코인별 익절/손절 % 백테스팅 최적화 (`orchestrator.py`, `backtesting/optimize.py`)
- 2단계 백테스팅: 최적 RSI 고정 후 take_profit/stop_loss 그리드서치
- TAKE_PROFIT_RANGE [5,8,10,15,20,25] × STOP_LOSS_RANGE [3,5,7,10] 조합
- `python -m backtesting.optimize risk` 명령으로 재실행 가능
- `_PROFIT_STOP_OVERRIDES` dict으로 15개 코인 개별 적용
- 주요 결과:
  - LINK: +15%/-10% → 백테스팅 +33.0% (기존 +10%/-5%)
  - BCH:  +15%/-3%  → +18.0%
  - HBAR: +20%/-5%  → +17.9%
  - ATOM: +15%/-5%  → +11.5%
  - BTC:  +5%/-3%   → 빠른 회전 전략

### 7. MA Cross 진입 조건 추가 (`orchestrator.py`)
- BUY 신호 발생 시 MA5 > MA20 (단기 이평 > 장기 이평) 추가 확인
- MA Cross 미충족 시 HOLD → 하락추세 구간 매수 차단
- MA 데이터 없는 경우 RSI만으로 판단 (fallback)
- 예: DOT RSI 10.0 과매도지만 MA5 < MA20 하락추세 → 매수 차단

### 8. 포지션 없을 때 SELL 신호 무시 (`orchestrator.py`)
- `_has_position()` 추가: DB 포지션 여부 확인
- SELL 신호 발생 시 포지션 없으면 HOLD 처리
- TRX처럼 보유 없이 매도 시도하던 노이즈 완전 제거

---

## 2026-04-04: 버그 수정 + 안정성 개선

### 매도 price 파싱 버그 수정 (`coin_executor.py`)
- 매도 체결 시 `price` → `avg_price` 우선 읽도록 수정 (buy와 동일 패턴)
- `avg_price`가 0이면 `estimated_value / quantity`로 직접 계산 (fallback 추가)
- 기존 코드는 매도 수익률 계산이 틀릴 수 있었음

### DB 연결 누수 수정 (`database.py` + 전 파일)
- `get_db()` context manager 추가: 예외 발생 시에도 반드시 연결 해제 보장
- `coin_executor.py`, `orchestrator.py`, `telegram_bot.py` 전체 `with get_db() as conn:` 패턴으로 통일
- EC2 t3.micro 장기 운영 시 연결 고갈 방지

### 감시 목록 제외 코인 포지션 자동 매도 (`orchestrator.py`)
- `_sell_orphaned_positions()` 메서드 추가
- `run_coin_cycle` 시작 시마다 watchlist에 없는 포지션(ETH 등) 자동 감지 → 매도 → 텔레그램 알림
- ETH처럼 백테스팅 음수로 감시 제외된 코인의 기존 포지션 처리 가능

---

## 2026-04-04: 전략 최적화 + 텔레그램 알림 전면 강화

### 전략 최적화
- **ETH, XRP 감시 목록 제외**: 백테스팅 음수 (ETH -6.2%, XRP -7.5%)
- **BTC 개별 RSI 임계값 적용**: 50/65 (기존 35/55 → +2.6% 백테스팅 성과)
- **코인별 RSI 오버라이드 구조 도입**: `_RSI_OVERRIDES` dict로 관리
- **현재 감시 코인 18개**: BTC(50/65), SOL/DOGE/ADA/AVAX/DOT/LINK/TRX/SUI/NEAR/HBAR/ICP/OP/ATOM/UNI/SHIB/LTC/BCH(35/55)

### 텔레그램 알림 전면 강화

### 변경 내용
- **매도 알림에 수익률(%) + 손익(원) 표시**
  - `telegram_bot.py`: `send_trade_alert()` 파라미터에 `entry_price`, `rsi` 추가
  - `coin_executor.sell()`: 매도 전 DB에서 `entry_price` 조회, 반환 dict에 포함
  - `orchestrator.py`: 매도 결과에서 `entry_price` 추출해 알림에 전달
  - 예시: `📉 수익률: -3.20% / 손익: -320원`
- **매수 알림에 RSI 값 표시**: 매수 근거 확인 가능
  - 예시: `RSI: 32.4`
- **`/status` 텔레그램 커맨드 추가**
  - 보유 포지션별 현재가 기준 미실현 손익(%) + RSI 실시간 표시
  - 합산 미실현 손익 + KRW 잔고 표시
- **매일 오전 9시 KST 포지션 현황 자동 전송**
  - 보유 코인별 미실현 손익, 합산 손익, KRW 잔고
- **연속 오류 3회 텔레그램 경고**
  - 동일 심볼에서 같은 오류가 3회 반복되면 즉시 알림
  - 성공 시 해당 심볼 오류 카운터 자동 초기화
- **디스크 사용량 모니터링**: 매시간 체크, 80% 초과 시 텔레그램 경고
- **주간 수익률 리포트**: 매주 월요일 오전 9시 KST 자동 전송
  - 최근 7일 매수/매도 횟수, 실현 손익, 현재 KRW 잔고 포함

---

## 2026-04-03: 일봉 RSI 단독 전략 + 백테스터 구축 (최종)

### 최종 전략 세팅
- **지표 봉:** 일봉 200개 (~7개월)
- **매수:** RSI < 35 (과매도)
- **매도:** RSI > 55 (과매수)
- **익절/손절:** +10% / -5% 유지
- **폴링:** 1분마다 20개 코인 순회
- **매수금액:** 10,000원 고정

### 백테스터 구축 (backtesting/)
- 업비트 일봉 8년치 데이터 크롤링 (2017~2026)
- 파라미터 그리드 서치 결과: RSI 35/55 최적
  - DOGE +8.9%, SOL +5.6%, BTC +2.6% (MDD -4.7% 이내)
  - ETH, XRP는 음수 → 해당 코인 주의
- `python -m backtesting.optimize`로 재실행 가능

### 인프라 변경
- /tmp/charts 29,337개(1.1GB) 삭제 → 디스크 100% 해소
- 매일 새벽 3시 UTC 자동 정리 크론 등록
- 업비트 허용 IP 43.203.205.237 추가
- Vercel dashboard 프로젝트 삭제, dashboard/ 폴더 제거

### 투자 현황 (2026-04-03)
- 기존 포지션: BTC/ETH/DOGE/ADA/TRX/DOT (약 38,000원, 전부 손실 중)
- 신규 충전: 103,000원
- 총 투자: 약 141,000원

---

## 2026-04-03: AI 완전 제거 → RSI + MA 크로스 전략으로 전환

### 변경 내용
- **AI(Groq/OpenAI) 완전 제거**: LLMEngine, 차트 이미지 생성 호출 삭제
  - 이유: Groq 무료 일일 한도 1,000건 → 20개 코인 × 60초 폴링 시 하루 안에 소진
  - AI 응답도 42, 42, 42... 반복으로 실질적 분석 효과 없었음
- **RSI + MA 크로스 전략 도입**:
  - 매수: RSI < 30 AND MA5 > MA20 (과매도 + 골든크로스)
  - 매도: RSI > 70 OR MA5 < MA20 (과매수 또는 데드크로스)
  - 익절 +10%, 손절 -5% 기존 유지
- **config.py**: `rsi_buy_threshold=30`, `rsi_sell_threshold=70` 추가
- **프론트엔드(dashboard/) 완전 제거**: Vercel 프로젝트도 삭제
- **EC2 디스크 정리**: /tmp/charts 29,337개(1.1GB) 삭제 → 디스크 100% → 83%

### 기타 (같은 날)
- 업비트 허용 IP에 현재 EC2 IP(43.203.205.237) 추가 (기존 43.203.227.201 유지)
- PostgreSQL 디스크 꽉 참으로 인한 DB 연결 실패 해결

---

## 2026-03-25: 주식 기능 완전 제거 + 코인 워치리스트 20개로 확대

### 변경 내용
- **주식 기능 완전 제거**: `StockExecutor`, `run_stock_cycle`, `is_stock_market_open` 코드 삭제
  - `orchestrator.py`, `balance.py`, `database.py`에서 stock 관련 코드 전부 제거
  - EC2 DB watchlist에서 삼성전자(005930.KS) 삭제
  - 원인: yfinance `005930.KS possibly delisted` 에러가 1분마다 반복 발생 중이었음
- **코인 워치리스트 10개 → 20개 확대**: Groq 무료 모델 전환으로 API 비용 부담 없어짐
  - 추가: SUI, NEAR, HBAR, ICP, OP, ATOM, UNI, SHIB, LTC, BCH
  - 현재 감시 목록: BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, DOT, LINK, TRX, SUI, NEAR, HBAR, ICP, OP, ATOM, UNI, SHIB, LTC, BCH

---

## 2026-03-24: entry_price 버그 수정 (익절/손절 비정상 동작 원인)

### 문제
- 업비트 시장가 매수 API `price` 필드 = KRW 주문 금액 (5000원), 코인 단가가 아님
- 이를 단가로 저장 → BTC entry_price 5,000원으로 기록 → +2,122,480% 익절 조건 매 사이클 발동
- DOGE/ADA/TRX 등은 -97% 손절 조건 매 사이클 발동 → 봇이 의도와 다르게 동작

### 수정 내용
- `avg_price` 필드 우선 사용 (실제 평균 체결 단가)
- `avg_price`가 0이면 `order_amount / quantity`로 직접 계산
- DB 기존 잘못된 entry_price 6건 즉시 복구 (`5000 / quantity`)

---

## 2026-03-24: 매수 금액 상향 + 추가매수 평균단가 계산

### 변경 내용
- **고정 매수 금액 5,000원 → 10,000원** (잔고 4만원 기준 최대 4번 추가매수 가능)
- **추가매수 시 평균단가 자동 계산**: `_save_position` 로직 개선
  - 기존: `ON CONFLICT DO NOTHING` → 추가매수해도 entry_price 업데이트 안 됨 (버그)
  - 변경: 보유 포지션 있으면 `(기존금액 + 신규금액) / 총수량` 으로 평균단가 재계산 후 UPDATE
  - 익절(+10%) / 손절(-5%) 기준 단가가 추가매수 후에도 정확히 반영됨

---

## 2026-03-22: 폴링 주기 단축 + 감시 종목 확대

### 변경 내용
- **폴링 주기 5분 → 1분으로 단축** (EC2 `.env` `POLL_INTERVAL_SECONDS=60`)
  - Groq 무료 폴백 있어서 OpenAI 소진 후에도 비용 걱정 없음
  - 쿨다운 5분 유지 → 과매매 없이 신호 감지만 빨라짐
- **감시 종목 5개 → 10개로 확대** (API로 DB에 직접 추가, 재시작 불필요)
  - 추가: ADA(에이다), AVAX(아발란체), DOT(폴카닷), LINK(체인링크), TRX(트론)
  - 현재 감시 목록: BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, DOT, LINK, TRX

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
- **1분마다** BTC/ETH/SOL/XRP/DOGE/ADA/AVAX/DOT/LINK/TRX 순회 — 변동성 필터 통과 시에만 GPT 분석
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
