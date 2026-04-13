# coin_bot 구현 현황

## 2026-04-13: 단기 전술 모드 명시 + 종목별 익절 + 전술형 선발 점수

### 종목별 고정 익절을 런타임 단일 소스로 통합 (`backend/runtime_params.json`, `backend/runtime_params.py`, `backend/orchestrator.py`)
- 전역 `take_profit_percent` 의존을 줄이고 종목별 `take_profit_percent` 를 `runtime_params.json` 에 추가
- 실운영 익절 판단은 이제 코인별 설정을 직접 읽음
- 활성 유니버스 전술 기본값:
  - `KRW-LINK`: `+4.0%`
  - `KRW-BCH`: `+2.0%`
  - `KRW-ADA`: `0.0%` (고정 익절 비활성)

### 백테스터/리서치도 익절 축을 함께 최적화 (`backtesting/simulator.py`, `backtesting/optimize.py`)
- `optimize_risk()` 가 이제 `take_profit + trailing_activation + stop_loss` 를 함께 탐색
- 장기 최적화 결과는 활성 3종 기준 대체로 `take_profit=0` 쪽을 선호
- 따라서 현재 런타임 값은 장기 누적 최대화가 아니라 최근 손실 방어를 위한 전술형 절충값임을 명확히 함

### 런타임 유니버스 선발을 전술형으로 재정의 (`backtesting/reselect_runtime.py`)
- `selection_score` 가 장기 현실화 수익보다 최근 OOS, 평균 OOS, 낮은 MDD를 더 강하게 반영하도록 변경
- 최소 선발 기준도 최근 OOS / 평균 OOS 중심으로 강화
- 리포트에 `short-term tactical` 모드 표시 추가

### 문서 방향 정리
- `README.md` 에 현재 전략을 “장기 복리형”이 아니라 “단기 전술형”으로 명시
- 종목별 `take_profit_percent` 가 런타임 핵심 파라미터임을 문서화

### 테스트 / 검증
- `PYTHONPATH=. pytest -q` → **95 passed**

### 남은 작업
- 새 전술형 `selection_score` 공식을 현재 코드에는 반영했지만, `backend/runtime_params.json` 의 점수/사유 스냅샷은 아직 재생성 전이다.
- 다음 세션에서 `recommend_runtime_universe(cache_only=True)` 또는 리포트 재생성 흐름을 다시 돌려 JSON 스냅샷을 갱신해야 한다.

## 2026-04-10: 주문 복구 저널 + 수동 보유 감지/편입 + 현재가 조회 안전화

### 주문 실행 원자화 + 복구 저널 (`backend/database.py`, `backend/execution/coin_executor.py`)
- `trades.order_uuid` 유니크 인덱스 추가
- `positions(market, symbol)` 유니크 인덱스 추가
- 체결 후 `trade` 저장과 `position` upsert/delete를 분리하지 않고 단일 반영 경로로 정리
- `order_journal` 테이블 추가
  - 주문 제출 직후 UUID와 요청 메타를 남김
  - 다음 사이클에서 미완료 주문을 다시 읽어 `trade`/`position` 반영 복구
- 최근 체결 주문 백필 추가
  - local journal/trades에 없는 최근 `done` 주문 UUID를 복구 큐에 자동 적재

### 수동 보유 종목 감지/정책화 (`backend/config.py`, `backend/database.py`, `backend/orchestrator.py`)
- `manual_holdings` 테이블 추가
  - 거래소 실보유인데 DB `positions`에 없는 종목을 추적
- 정책 설정 추가
  - `manual_holding_policy=alert_only|import|ignore`
  - `manual_holding_min_value_krw`
- 기본 정책은 `alert_only`
  - 수동 매수 종목을 감지만 하고 자동매매 포지션으로는 편입하지 않음
- 필요 시 `import` 정책으로 DB 포지션 편입 가능
- 거래소 잔고 조회 실패 시에는 `manual_holdings`를 닫지 않도록 보호 로직 추가

### 수동 편입 포지션 메타 (`backend/database.py`, `backend/orchestrator.py`)
- `positions.source`, `positions.imported_at` 추가
- 수동 편입 포지션은 `source='manual_import'`로 구분 가능
- 중복 포지션이 있으면 병합 후 source/imported_at까지 보존하도록 마이그레이션 보강

### 백필 손익 기준가 보강 (`backend/database.py`, `backend/execution/coin_executor.py`)
- `order_journal.order_created_at` 추가
- sell 백필 시 현재 포지션 가격을 재사용하지 않고
  - 주문 생성 시각 이전 `trades` 이력을 재생해 평균 진입가 복원
  - 그 값을 `entry_price_snapshot`과 손익 계산 기준으로 사용

### 현재가 조회 안전화 (`backend/execution/coin_executor.py`, `backend/routers/portfolio.py`, `backend/ai/agent_tools.py`)
- 지원되지 않는 심볼이 섞여도 전체 현재가 조회가 실패하지 않도록 `get_current_prices_safe()` 추가
- KRW 지원 심볼만 조회하고, 배치 실패 대신 개별 조회로 폴백
- 포트폴리오 API와 agent tool도 같은 helper를 재사용하도록 정리
- EC2 실검증 결과 기존 `Code not found` 경고는 재현되지 않음

### 실서버 검증
- 대상: `ubuntu@43.203.205.237:/home/ubuntu/coin_bot`
- 여러 차례 `rsync` 배포 후 `sudo systemctl restart coinbot`
- 검증:
  - `systemctl is-active coinbot` → `active`
  - 주문 저널/수동 보유/포지션 메타 컬럼 반영 확인
  - `KRW-SAND` 수동 보유 감지 → 이후 거래소 실보유 부재 확인 시 `manual_holdings.status='closed'` 로 정리됨
  - 실보유 현재가 조회 경고(`Code not found`) 제거 확인

### 테스트 / 검증
- `PYTHONPATH=. pytest -q` → **83 passed**
- `python -m compileall backend backtesting tests` 통과

## 2026-04-09: 소액 시드 집중 전략 + 런타임 유니버스 재선정 + EC2 배포

### 일봉 확정봉 기준 신호 정렬 (`backend/ai/chart_generator.py`, `backend/orchestrator.py`, `backend/database.py`)
- 실운영 RSI 신호가 미완성 현재 일봉을 읽지 않도록 수정
  - 전략 신호는 이제 **직전 확정 일봉**만 사용
  - 트레일링/손절은 기존처럼 실시간 현재가 기준 유지
- `signal_locks` 테이블 추가
  - 같은 확정 일봉에서 동일 `BUY`/`SELL`을 한 번만 실행
  - 장중 손절 후 같은 전일 RSI 신호로 재진입하는 문제 방지
- `runtime_status`의 BTC 레짐도 동일하게 확정 일봉 기준으로 맞춤
- 텔레그램 `/status`와 런타임 API도 동일한 확정 일봉 기준 RSI로 정렬

### 백테스터/실운영 정렬 (`backtesting/simulator.py`, `backtesting/optimize.py`)
- 백테스터 매도 조건에서 남아 있던 `MA 데드크로스` 의존을 제거하고, 실운영과 동일하게 **RSI 단독 전략**으로 정렬
- RSI 탐색 범위를 `30`까지 다시 열어 과매도 진입 후보를 재평가
- 최신 캐시 데이터 기준 재최적화 결과:
  - `LINK`: `RSI 50/70`, `trail +5.0%`, `stop -10%`, `+24.5%`
  - `BCH`: `RSI 40/70`, `trail +5.0%`, `stop -7%`, `+22.2%`
  - `TRX`: `RSI 40/70`, `trail +5.0%`, `stop -7%`, `+6.8%`

### 소액 시드 집중 배분 (`backend/config.py`, `backend/orchestrator.py`, `backend/execution/coin_executor.py`)
- `target_position_budget_krw` 도입: 총자산 기준으로 **실효 최대 포지션 수** 계산
- `min_order_amount_krw`, `max_order_amount_krw` 추가
- 여러 BUY 신호가 동시에 떠도
  - 남은 슬롯 수가 적으면 주문 비중을 자동 상향
  - 과매도 강도 + 백테스트 메타가 더 좋은 종목을 먼저 평가
- 효과:
  - 적은 시드가 여러 코인에 잘게 나뉘는 문제 완화
  - 신호가 많아도 핵심 종목에 더 집중

### 런타임 유니버스 재선정 (`backend/runtime_params.json`)
- 기본 신규매수 허용 종목을 `LINK / BCH / ADA` 3개로 재선정
- `BTC`는 장세 필터 전용으로 유지하고 신규 매수는 비활성화
- 나머지 종목은 최신 현실화 수익 / 최근 OOS / walk-forward 특성을 반영해 사유와 파라미터를 갱신

### 점수 기반 유니버스 선발 (`backtesting/reselect_runtime.py`)
- 기존: `realistic > 0`, `recent_oos`, `avg_oos` 임계값 통과 여부로 `enabled` 결정
- 변경: 소액 시드 운영용 **점수 기반 상위 N 선발**
  - 반영 요소: 현실화 수익, walk-forward 평균 OOS, 최근 OOS, 거래 수, walk-forward 윈도우 수, MDD 페널티
  - 최소 기준 통과 종목만 후보군에 넣고, 그중 `top_n=3`만 `enabled=true`
- 최신 자동선정 결과:
  - `KRW-BCH` #1
  - `KRW-LINK` #2
  - `KRW-ADA` #3
  - `KRW-TRX`는 점수 `+7.3`로 근소하게 밀려 후보 4위

### 기간청산(time stop) 추가 (`backend/orchestrator.py`, `backtesting/simulator.py`)
- 장기 미청산 포지션이 자금을 묶는 문제 완화용
- 규칙:
  - `max_hold_days=10`
  - `time_stop_min_pnl_pct=0.0`
- 의미:
  - 보유 기간이 10일 이상이고
  - 현재 손익이 0% 미만이면
  - 다음 확정 일봉 평가 시 `기간청산`
- 실운영과 백테스터에 동일 규칙 반영

### 최근 실전 성과 기반 자동 디레이팅 (`backend/live_performance.py`, `backend/runtime_params.py`, `backend/runtime_status.py`)
- 기본 유니버스는 연구 결과(`runtime_params.json`)로 결정
- 그 위에 최근 30일 실전 성과를 얹어서 신규매수 허용 종목을 한 번 더 거름
- 기본 규칙:
  - `live_derating_lookback_days=30`
  - `live_derating_min_sell_count=3`
  - 최근 실현손익이 음수이고
  - 승률 또는 평균 `pnl_pct`가 기준 미달이면
  - 해당 종목은 **일시적 신규매수 제외**
- 기존 보유 포지션은 그대로 관리하고, 신규 진입만 차단
- `/api/runtime/status`에 최근 종목별 실현 성과 요약 포함
- `/api/runtime/status` `selection` 항목에 `base_enabled`, `live_derated`, `selection_score` 포함
- 텔레그램 `/status`에
  - 현재 선발 종목 점수 요약
  - 실전 성과로 일시 제외된 종목 요약
  표시
- 추가 개선:
  - `/status` 제외 요약에 `live` / `score` 태그 표시
  - 선발 점수는 `effective_selection_score` 기준으로 노출
  - 종목별 `state_label` 기반 상태판 요약 추가

### 실전 피드백 점수 루프 (`backend/live_performance.py`, `backend/runtime_params.py`, `backend/orchestrator.py`)
- 최근 실전 성과를 이진 차단만 하지 않고 **점수 보정치**로 환산
- `live_score_adjustment`
  - 최근 SELL 표본이 충분한 종목만 대상
  - 평균 `pnl_pct`, 최근 승률, 최근 실현손익을 합쳐 계산
- `effective_selection_score = selection_score + live_score_adjustment`
- 오케스트레이터의 진입 우선순위는 이제 `effective_selection_score` 를 반영
  - 같은 과매도 강도면 최근 실전이 더 나았던 종목이 먼저 평가됨

### 연속 손실 쿨다운 (`backend/live_performance.py`, `backend/runtime_params.py`, `backend/runtime_status.py`)
- 최근 SELL 기준 연속 손실 streak 계산 추가
- 기본 규칙:
  - `loss_streak_threshold=2`
  - `loss_streak_cooldown_days=7`
  - `loss_streak_lookback_days=30`
- 최근 2연속 손실 이상이고 마지막 손실이 아직 쿨다운 기간 안이면 신규매수 제외
- `/api/runtime/status`, 텔레그램 `/status` 에 `loss_streak_cooled` / 요약 노출

### 런타임 리포트 자동생성 (`backtesting/reselect_runtime.py`)
- `--write-report` 옵션 추가
- 현재 추천 유니버스를 Markdown으로 저장:
  - 경로: `docs/superpowers/reports/YYYY-MM-DD-runtime-universe.md`
- 리포트 내용:
  - enabled / blocked 종목 구분
  - selection score, 현실화 수익, walk OOS, recent OOS, 이유
- 2026-04-09 기준 리포트 생성 완료:
  - `docs/superpowers/reports/2026-04-09-runtime-universe.md`

### 런타임 리포트 스케줄러 (`deploy/systemd/coinbot-runtime-report.service`, `.timer`)
- EC2에서 리포트 자동생성을 위한 systemd unit 추가
- 매일 `00:15 UTC` (`09:15 KST`) 에 실행
- 실행 명령:
  - `python -m backtesting.reselect_runtime --top-n 3 --write-report --allow-fetch --auto-apply-runtime`

### 안전장치 포함 자동 반영 (`backtesting/reselect_runtime.py`)
- 목표: `리포트 생성 -> 조건 충족 시 runtime_params 자동 반영`
- 안전 게이트:
  - 제안된 enabled 종목 수가 `top_n` 이상이어야 함
  - enabled 종목 변경 수가 `max_symbol_changes` 이하이어야 함 (기본 2)
- 리포트의 `## Auto Apply` 절에
  - applied 여부
  - 기존/제안 enabled 목록
  - 추가/제거 종목
  - 보류 사유
  기록
- EC2 `coinbot-runtime-report.service` 에도 연결 완료
  - `--allow-fetch --auto-apply-runtime`
  - 서버 실검증 결과 `status=0/SUCCESS`

### auto-apply 알림 (`backtesting/reselect_runtime.py`)
- `--notify-telegram` 옵션 추가
- auto-apply 성공/보류 결과를 텔레그램으로 전송
- 리포트 파일명, enabled 집합, 추가/제거 종목, blocked 사유 포함
- EC2 수동 실행 검증:
  - `coinbot-runtime-report.service` 성공 종료
  - 저널에 `📨 sent Telegram notification` 확인

### 문서/환경 예시 갱신
- `README.md`: 최신 파라미터 테이블, 소액 시드 집중 전략, 런타임 유니버스 반영
- `MEMORY.md`: 운영 메모 최신화
- `.env.example`: 현재 설정 키 기준으로 정리 (`RISK_ON_*`, `TARGET_POSITION_BUDGET_KRW`, 주문 min/max 등)

### 테스트 / 검증
- `PYTHONPATH=. pytest -q` → **66 passed**
- `python -m compileall backend backtesting tests` 통과

### EC2 배포
- 대상: `ubuntu@43.203.205.237:/home/ubuntu/coin_bot`
- `rsync`로 코드 동기화 후 `sudo systemctl restart coinbot`
- 검증:
  - `systemctl is-active coinbot` → `active`
  - `journalctl` 에서 `✅ 오케스트레이터 시작`
  - `runtime params loaded (15 symbols) from /home/ubuntu/coin_bot/backend/runtime_params.json`

---

## 2026-04-08: 업비트 주문 안정성 + 운영 리스크 캡

### 주문 재시도·체결 폴링 (`backend/execution/coin_executor.py`)
- 시장가 매수/매도 API: 최대 3회 재시도(짧은 백오프)
- `get_order`: 일시 오류·미체결 대비 지연 재시도(최대 10회), `state==done` 또는 `executed_volume>0` 시 확정
- `state==cancel` 이면 실패 처리

### 리스크 캡 (`backend/config.py`, `backend/risk_limits.py`, `backend/orchestrator.py`)
- `max_open_positions` (기본 12, **0이면 비활성화**): 신규 심볼 매수 시 DB `positions` 개수가 상한 이상이면 매수 생략 (이미 보유 중인 심볼 추가매수는 기존 로직상 차단됨)
- `max_buys_per_day` (기본 48, **0이면 비활성화**): KST 당일 0시 이후 `trades`의 `BUY` 건수가 상한 이상이면 매수 생략
- 환경변수: `MAX_OPEN_POSITIONS`, `MAX_BUYS_PER_DAY`

### 테스트
- `tests/test_coin_executor.py` — 체결 조회 폴링
- `tests/test_orchestrator.py` — 리스크 캡 차단
- `PYTHONPATH=. pytest -q` → 37 passed

---

## 2026-04-08: 런타임 파라미터 단일화 (`runtime_params.json`)

### 목적
- 신규 매수 유니버스·코인별 RSI·트레일링/손절Pct를 **한 파일**에서 관리 (`backend/runtime_params.json`)
- `orchestrator` / `runtime_status`에 흩어져 있던 상수 제거 → 수정 누락·불일치 방지

### 추가·변경 파일
- **신규** `backend/runtime_params.json` — 종목별 `enabled`, `reason`, `realistic_return_pct`, `recent_oos_pct`, `rsi_buy`, `rsi_sell`, `trailing_activation_percent`, `stop_loss_percent`
- **신규** `backend/runtime_params.py` — 로드/검증/캐시, `get_active_buy_symbols()`, `rsi_pair()`, `trailing_stop_pair()` 등
- **수정** `backend/runtime_status.py` — JSON 기반으로 `selection`, 허용/제외 종목 목록 구성
- **수정** `backend/orchestrator.py` — 위 헬퍼만 사용 (클래스 내 `_RSI_OVERRIDES` / `_PROFIT_STOP_OVERRIDES` 제거)
- **수정** `backtesting/reselect_runtime.py` — `--write-backend` 옵션: 연구 결과로 JSON의 `enabled`·`reason`·`realistic_return_pct`·`recent_oos_pct`만 갱신 (RSI·트레일링 키는 유지)

### 운용
- 기본 경로: `backend/runtime_params.json`
- 다른 파일을 쓰려면 환경변수 `RUNTIME_PARAMS_PATH` 설정
- 재선정 + 파일 반영:
  - `PYTHONPATH=. python -m backtesting.reselect_runtime --write-backend`
- 봇 프로세스 재시작 후 JSON 반영 (모듈 캐시). 런타임 핫 리로드가 필요하면 `runtime_params.reload_runtime_params()` 연동 검토

### 테스트
- 이후 리스크 캡·주문 재시도 테스트 추가로 **현재 전체 스위트는 37 passed** (상단 `업비트 주문 안정성 + 운영 리스크 캡` 절 참고)

---

## 2026-04-08: 운영 종목 자동 재선정 도구 + 장세별 포지션 사이징

### 운영 종목 자동 재선정 도구 (`backtesting/reselect_runtime.py`)
- 현실화 백테스트 + walk-forward + 최근 OOS 결과를 종합해서 runtime universe 후보를 다시 뽑는 스크립트 추가
- 실행:
  - `PYTHONPATH=. python -m backtesting.reselect_runtime`
  - 결과를 `backend/runtime_params.json`에 반영: 같은 명령에 `--write-backend` 추가 (상세는 상단 `런타임 파라미터 단일화` 절)
- 목적:
  - 운영 종목·사유·OOS 메타를 리포트 기반으로 재선정 (RSI·트레일링은 JSON에서 별도 유지)

### 장세별 포지션 사이징 (`backend/config.py`, `backend/execution/coin_executor.py`, `backend/orchestrator.py`)
- 장세를 `risk_on / caution / risk_off` 3단계로 확장
- 권장 매수 비중 설정 추가
  - `risk_on_order_size_ratio=0.2`
  - `caution_order_size_ratio=0.1`
  - `risk_off_order_size_ratio=0.05`
- 실제 매수 시 장세별 비중을 사용하도록 연결
- 단, `risk_off`에서는 기존처럼 알트 신규 매수는 차단됨

### 운영 사유 가시성 강화 (`backend/runtime_status.py`)
- 각 종목별 `enabled`, `reason`, `realistic_return_pct`, `recent_oos_pct` 포함
- `/api/runtime/status`에서 허용/제외 사유를 바로 확인 가능

---

## 2026-04-08: 보유 포지션 보호 + 운영 제외 종목 완화형 우선 청산

### 보유 포지션 보호 (`backend/orchestrator.py`)
- watchlist 자동 동기화가 현재 보유 포지션을 orphan으로 만들지 않도록 수정
- active watchlist는 이제
  - 런타임 신규 매수 허용 종목
  - 현재 실제 보유 포지션
  를 합친 집합으로 유지
- 의미:
  - 운영 제외 종목을 들고 있어도 즉시 orphan 매도로 쓸려나가지 않음
  - 기존 포지션은 계속 관리되고, 출구 로직도 정상 유지

### 운영 제외 종목 완화형 우선 청산 (`backend/orchestrator.py`)
- 신규 매수는 여전히 차단
- 이미 보유 중인 운영 제외 종목은 아래 조건에서 우선 청산
  - 평가손익 `+1.0%` 이상 수익권 진입
  - 또는 RSI가 약한 매도 구간 진입
- 즉시 강제 청산 대신 “수익권 또는 약한 출구 신호에서 정리” 방식 채택

### 테스트
- held symbol watchlist 보존 테스트 추가
- 운영 제외 종목 완화형 청산 기준 테스트 추가

---

## 2026-04-08: watchlist 자동 동기화 + 런타임 상태 노출

### watchlist 자동 동기화 (`backend/orchestrator.py`, `backend/runtime_status.py`)
- 런타임 허용 종목 집합을 `ACTIVE_BUY_SYMBOLS`로 단일화
- 매 사이클 시작 시 DB watchlist를 런타임 허용 종목 기준으로 자동 동기화
  - 허용 종목: `active = TRUE`
  - 비허용 종목: `active = FALSE`
- 의미:
  - 코드상 운영 종목과 DB watchlist 상태가 계속 일치
  - 운영자가 별도로 수동 정리하지 않아도 됨

### 런타임 상태 API / 텔레그램 확장 (`backend/routers/runtime.py`, `backend/telegram_bot.py`)
- 신규 API 추가: `/api/runtime/status`
- 반환 정보:
  - 현재 `risk_off` 여부
  - BTC RSI / MA5 / MA20 / 현재가
  - 신규 매수 허용 종목 목록
  - 현재 active watchlist 목록
  - 최근 30일 실현손익 / 승률 / 매도 횟수
- 텔레그램 `/status`에도 장세, 허용 종목, 최근 30일 실현손익 추가

### 테스트
- runtime router 테스트 추가
- watchlist 동기화 테스트 추가
- 검증 결과: `PYTHONPATH=. pytest -q` 통과

---

## 2026-04-08: 운영 대상 축소 + 레짐 필터 강화

### 운영 대상 축소 (`backend/orchestrator.py`)
- 최근 현실화 백테스트/OOS 기준으로 신규 매수 허용 종목을 축소
- 현재 신규 매수 허용:
  - `KRW-SOL`
  - `KRW-DOGE`
  - `KRW-LINK`
  - `KRW-HBAR`
  - `KRW-UNI`
  - `KRW-BCH`
  - `KRW-BTC`는 예외적으로 유지
- 의미:
  - watchlist에 남아 있어도 비우호 성능 종목은 신규 진입 차단
  - 기존 보유 포지션은 매도/정리 로직은 그대로 유지

### 레짐 필터 강화 (`backend/orchestrator.py`)
- 기존: `BTC RSI < 40` 단일 조건
- 변경: 아래 3개 중 2개 이상 충족 시 리스크오프 판정
  - BTC RSI < 45
  - BTC `MA5 < MA20`
  - BTC 현재가 < `MA20`
- 리스크오프 장세에서는 BTC 제외 알트코인 신규 매수 차단
- 효과:
  - 횡보/약세장에서 매수 빈도 감소
  - 비용 반영 후 edge가 약한 구간 진입 억제

### 테스트/문서
- 운영 제외 심볼 차단 테스트 추가
- 리스크오프 판정 테스트 추가
- README와 PROGRESS에 운영 대상 축소 / 강화된 레짐 필터 반영

---

## 2026-04-08: 비용 반영 백테스트 + Walk-Forward + 최근 OOS 검증

### 현실화 백테스트 반영 (`backtesting/simulator.py`, `backtesting/optimize.py`, `backtesting/data_fetcher.py`)
- 백테스터에 업비트 기준 보수적 비용 가정 추가
  - 수수료: `0.05%`
  - 슬리피지: `0.05%`
- 매수/매도 체결가를 비용 반영 체결가로 계산하도록 수정
- 보유 포지션 평가도 마지막 봉 종가가 아니라 비용 반영 청산가 기준으로 계산하도록 변경
- `fetch_ohlcv(..., cache_only=True)` 지원 추가
  - 최신 캐시 파일이 있으면 네트워크 없이도 연구 리포트 재실행 가능

### Walk-Forward / 최근 OOS 검증 (`backtesting/optimize.py`)
- 학습 구간 720일 / 검증 구간 180일 / 180일 step 기준 walk-forward 검증 추가
- 최신 180일 구간 별도 OOS 성능 체크 추가
- 전체 전수탐색 대신 실무형 2단계 탐색으로 조정
  - 1단계: RSI 매수/매도 최적화
  - 2단계: 트레일링 활성화% / 손절% 최적화
- 캐시 데이터 기준 연구 명령:
  - `PYTHONPATH=. python -m backtesting.optimize`

### 현실화 백테스트 결과 요약 (캐시 데이터 기준)
- 양수 유지: LINK `+21.2%`, BCH `+6.8%`, UNI `+5.3%`, HBAR `+4.2%`, DOGE `+3.7%`, SOL `+2.6%`
- 거의 0 근처: SUI `+0.0%`, ICP `+0.2%`, ATOM `-0.3%`, TRX `-1.0%`, SHIB `-1.4%`
- 음수 심화: BTC `-10.1%`, ADA `-5.7%`, DOT `-4.7%`, AVAX `-3.4%`
- 의미:
  - 비용 반영 후에도 일부 코인만 확실한 edge 유지
  - 기존 “전부 양수처럼 보이던” 기대수익은 보수적으로 재평가됨

### Walk-Forward / 최근 OOS 해석
- Walk-forward 평균 OOS가 일관되게 강한 코인은 많지 않음
- 최근 180일 OOS에서는 BCH `-1.0%`, LINK `-2.5%`, SOL `-4.8%`, BTC `-3.5%` 등으로 최근장 적응력이 약한 편
- DOGE `+0.1%`, DOT `+0.4%` 정도만 최근 구간 방어
- 결론:
  - 현재 전략은 “장기 인샘플 최적화” 대비 “최근 실전 적응력”이 강하지 않음
  - 다음 단계는 신규 파라미터 추가보다 레짐 필터, 거래 빈도 축소, 코인 셀렉션 축소가 우선

### 운영 파라미터 재산출 반영 (`backend/orchestrator.py`)
- `_RSI_OVERRIDES`를 비용 반영 백테스트 기준으로 재산출
- `_PROFIT_STOP_OVERRIDES`를 `(trailing_activation_percent, stop_loss_percent)` 구조로 재정의
- 런타임 트레일링 활성화 조건도 코인별 activation 값을 직접 사용하도록 수정
- LINK는 `+5.0%` 활성화 / `-5%` 손절 조합이 가장 우수하게 확인됨

---

## 2026-04-08: 백테스터-실운영 정합성 확보 + AI 분리 + 테스트 체계 정리

### 백테스터 실운영 정합성 확보 (`backtesting/simulator.py`, `backtesting/optimize.py`)
- 백테스터에 `use_trailing_stop` 옵션 추가
- 실운영과 동일한 트레일링 스탑 규칙 반영
  - 손절: `entry_price` 기준 `-stop_loss%`
  - 트레일링 활성화: `highest_price >= entry_price × (1 + stop_loss/200)`
  - 트레일링 발동: `current_price <= highest_price × (1 - stop_loss/100)`
- `python -m backtesting.optimize`와 `python -m backtesting.optimize risk`가 기본적으로 트레일링 기준 결과를 계산하도록 변경
- 짧은 샘플/비정상 데이터로 `df.empty`가 되는 경우에도 백테스터가 예외 없이 종료되도록 방어 로직 추가

### 거래 코어와 AI/chat 결합도 완화 (`backend/routers/chat.py`, `backend/ai/chat_agent.py`, `backend/ai/chart_generator.py`)
- `/chat` 요청 시점에만 AI agent import 하도록 변경
- `langchain_groq`, `langchain` 관련 import를 `ask_agent()` 내부로 이동
- `mplfinance`, `yfinance` import를 실제 차트 생성 함수 내부로 이동
- 결과: FastAPI 앱 import 시 AI/차트 의존성 때문에 서버 전체가 죽는 구조 제거
- 로컬 검증 기준 `from backend.main import app` 정상 통과 확인

### 테스트 체계 정리 (`pytest.ini`, `backend/routers/test_trade.py`, `tests/`)
- `pytest.ini` 추가: 테스트 수집 경로를 `tests/`로 고정
- `backend/routers/test_trade.py`에 `__test__ = False` 추가해 라우터 파일이 테스트로 오인 수집되지 않도록 수정
- 예전 AI 기반 오케스트레이터 테스트를 현재 RSI/포지션 기반 신호 테스트로 교체
- 트레일링 스탑 백테스터 회귀 테스트 추가
- 검증 결과: `PYTHONPATH=. pytest -q` → `23 passed`

### 다음 고도화 후보
- 수수료/슬리피지 백테스터 반영
- walk-forward / 구간별 OOS 검증 추가
- `_PROFIT_STOP_OVERRIDES` 재산출 후 운영 파라미터 재동기화

---

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
