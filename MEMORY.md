# coin_bot — 작업 메모 (에이전트/인간 공용)

최종 정리: **2026-04-09**

## 프로젝트 한 줄

업비트 일봉 RSI 자동매매 봇(FastAPI, PostgreSQL, 텔레그램). EC2에서 60초 루프.

## 최근에 바뀐 중요 사항

### 소액 시드 집중 전략

- 백테스터와 실운영을 **RSI 단독 진입/청산** 기준으로 다시 정렬.
- `backtesting/simulator.py`의 MA 데드크로스 매도를 제거해서 실운영 로직과 맞춤.
- 실운영 RSI 신호는 **현재 진행 중인 일봉이 아니라 마지막 확정 일봉**만 사용.
- `signal_locks` 테이블로 같은 확정 일봉의 중복 BUY/SELL을 막음.
- 텔레그램 `/status`와 런타임 상태도 같은 확정 일봉 RSI를 표시.
- 자동선정 로직 적용 후 현재 기본 유니버스는 **BCH / LINK / ADA**.
- `backend/config.py`
  - `target_position_budget_krw` (기본 50,000)
  - `min_order_amount_krw`, `max_order_amount_krw`
- `backend/orchestrator.py`
  - 총자산 기준 **실효 포지션 수 상한** 계산
  - 여러 BUY 신호 동시 발생 시 **과매도 강도 + 백테스트 메타** 기준 우선순위
  - 남은 슬롯이 적으면 매수 비중을 자동으로 높여서 시드 분산 완화
  - 같은 확정 일봉에서 재진입/재청산 방지
- `backtesting/reselect_runtime.py`
  - 조건 통과식이 아니라 **점수 기반 상위 N 선발**
  - 현재 `top_n=3`
- `time stop`
  - `max_hold_days=10`
  - `time_stop_min_pnl_pct=0.0`
  - 오래 묶였는데 수익 전환 못 한 포지션 정리용
- `live derating`
  - 최근 30일 SELL 실적 기준 신규매수 일시 차단
  - 기본 유니버스 위에 실전 성과 오버레이를 얹는 구조
  - `/status`와 runtime API에서 `selection_score`, `live_derated` 상태를 바로 볼 수 있음
- `live feedback loop`
  - 최근 실전 성과를 `live_score_adjustment` 로 환산
  - `effective_selection_score` 로 진입 우선순위까지 반영
- `/status`
  - 선발 종목은 `effective_selection_score`
  - 제외 종목은 `live` / `score` 이유 요약
- `loss streak cooldown`
  - 최근 연속 손실 2회 이상이면 7일 신규매수 차단
  - runtime/API/텔레그램에 `loss_streak_cooled` 로 노출
- `runtime report automation`
  - `python -m backtesting.reselect_runtime --write-report`
  - `docs/superpowers/reports/YYYY-MM-DD-runtime-universe.md` 생성
- `runtime report scheduler`
  - EC2 systemd timer로 매일 `09:15 KST` 자동 생성
  - 현재는 `--auto-apply-runtime` 포함
  - 안전 게이트 통과 시 `runtime_params.json` 자동 갱신
  - `runtime_params.py` 는 mtime 변경 감지로 자동 재로드
  - auto-apply 결과는 텔레그램으로도 알림
  - EC2 수동 실행에서 `📨 sent Telegram notification` 확인
- 현재 기본 생각:
  - BTC는 **장세 필터 전용**
  - 소액 시드일수록 종목 수를 늘리기보다 **소수 핵심 종목 집중**이 우선

### EC2 반영 상태

- 서버: `43.203.205.237`
- 배포 경로: `/home/ubuntu/coin_bot`
- 확인:
  - `systemctl is-active coinbot` → `active`
  - 로그에 `runtime params loaded ... /home/ubuntu/coin_bot/backend/runtime_params.json`

### 런타임 파라미터 단일 소스

- 파일: `backend/runtime_params.json`
- 코드: `backend/runtime_params.py` (`RUNTIME_PARAMS_PATH`로 경로 오버라이드 가능)
- 종목별 **신규 매수 허용**, 사유, OOS 메타, **RSI 매수/매도**, **트레일링 활성화% / 손절%** 를 이 JSON에서만 관리.
- 연구 후 유니버스·OOS 필드만 갱신:  
  `PYTHONPATH=. python -m backtesting.reselect_runtime --write-backend`  
  (RSI·트레일링 키는 스크립트가 덮어쓰지 않음)
- JSON 수정 후 **프로세스 재시작** 필요 (모듈 캐시).

### 업비트 주문 안정성

- `backend/execution/coin_executor.py`: 시장가 주문 **3회 재시도**, `get_order` **폴링**(최대 10회)으로 체결 확인.

### 운영 리스크 캡

- `backend/risk_limits.py` + `backend/config.py`
- `max_open_positions` (기본 12): 신규 심볼 매수 시 DB 포지션 개수 상한. **0 = 비활성화**
- `max_buys_per_day` (기본 48): KST 당일 `trades`의 BUY 건수 상한. **0 = 비활성화**
- 환경변수: `MAX_OPEN_POSITIONS`, `MAX_BUYS_PER_DAY`
- 추가:
  - `TARGET_POSITION_BUDGET_KRW`
  - `MIN_ORDER_AMOUNT_KRW`
  - `MAX_ORDER_AMOUNT_KRW`

## 자주 쓰는 명령

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m backtesting.optimize
PYTHONPATH=. python -m backtesting.reselect_runtime
PYTHONPATH=. python -m backtesting.reselect_runtime --write-backend
uvicorn backend.main:app --port 8002
```

## 상세 이력

구현 날짜별 상세·맥락은 **`PROGRESS.md`** 가 정본.

## 다음 후보 고도화 (미구현)

- 최근 OOS 기준 자동 유니버스 컷오프 규칙 정교화
- 설정 정리(`config` 레거시 플래그 / 미사용 env 키)
- 관측성(메트릭·구조화 로그)
