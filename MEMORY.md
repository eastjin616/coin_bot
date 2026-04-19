# coin_bot — 작업 메모 (에이전트/인간 공용)

최종 정리: **2026-04-19**

## 프로젝트 한 줄

업비트 일봉 RSI 자동매매 봇(FastAPI, PostgreSQL, 텔레그램). EC2에서 60초 순회하며, 실운영은 단기 전술형 코어 유니버스 중심으로 굴린다.

## 지금 중요한 운영 상태

### 전략 / 유니버스

- 실운영 신호는 **현재 진행 중인 일봉이 아니라 마지막 확정 일봉**만 사용.
- `signal_locks`로 같은 확정 일봉의 중복 BUY/SELL을 방지.
- BTC는 기본적으로 **장세 필터 전용**이며 신규매수 기본 대상은 아님.
- 현재 전술 코어 스냅샷은 **BCH / ADA / LINK / TRX** 4종.
- 자동 재선정 기본값도 이제 `top_n=4`로 정렬되어, live snapshot과 auto-apply 기본 경로가 맞는다.
- 다만 실제 신규매수 허용 심볼은 `live_derated`, `loss_streak_cooled`, `manual_override` 같은 실전 오버레이 때문에 더 좁아질 수 있다.

### 리스크 / 주문 / 포지션

- 소액 시드는 분산보다 **집중 배분** 우선.
- `target_position_budget_krw` 기반으로 총자산 대비 **실효 최대 포지션 수**를 계산.
- 여러 BUY 신호가 동시에 뜨면 **과매도 강도 + selection 메타** 기준으로 우선순위를 정함.
- `max_open_positions`, `max_buys_per_day`로 운영 리스크 캡 적용 가능.
- 주문 실행은 `order_journal`과 `trades.order_uuid` 기반으로 복구 가능하게 되어 있음.
- 수동 보유 종목은 `manual_holdings`에서 추적하고, 정책은 `alert_only|import|ignore`.
- imported 수동 포지션은 `positions.source='manual_import'`.

### 추가 실행 경로

- **DCA 분할매수**
  - 기본 비활성화 (`DCA_ENABLED=false`)
  - 직전 매수 RSI보다 `DCA_STEP_RSI` 이상 더 빠지면 추가매수
  - `MAX_DCA_COUNT`, `DCA_ORDER_SIZE_RATIO` 사용
- **분할 매도**
  - 기본 비활성화 (`PARTIAL_SELL_ENABLED=false`)
  - RSI가 `sell_threshold - PARTIAL_SELL_RSI_OFFSET` 구간에 들어오면 `PARTIAL_SELL_PCT`만큼 1회 부분 청산
  - 상태는 `positions.partial_sell_done`

### 런타임 파라미터 단일 소스

- 파일: `backend/runtime_params.json`
- 코드: `backend/runtime_params.py`
- `RUNTIME_PARAMS_PATH`로 경로 오버라이드 가능
- 종목별 신규매수 허용, 사유, OOS 메타, RSI, 익절/트레일링/손절 파라미터를 이 JSON에서 관리
- 일반적인 파일 수정은 `runtime_params.py`가 mtime 감지로 **자동 재로드**하므로 보통 재시작이 필요 없다
- 텔레그램 watchlist 명령도 write 후 즉시 reload를 강제한다

## 텔레그램 / 상태면

- 운영 명령:
  - `/status`
  - `/performance`
  - `/watchlist`
  - `/watchlist_remove <symbol>`
  - `/watchlist_add <symbol>`
  - `/list`
  - `/dca`
- `/status`는 `effective_selection_score`, blocked summary, 상태판, 최근 실현 성과 요약까지 보여준다.
- `/performance`는 최근 `7/14/30일` 실현 성과를 요약한다.

## EC2 상태

- 서버: `43.203.205.237`
- 배포 경로: `/home/ubuntu/coin_bot`
- 2026-04-19 기준:
  - repo 동기화 완료
  - `coinbot` restart 완료
  - `coinbot-runtime-report.service` / `.timer`를 systemd에 재설치
  - installed unit과 실제 실행 중인 one-shot 프로세스 모두 `--top-n 4`
  - `/api/runtime/status` 응답 정상
- 주의:
  - full research 기반 `coinbot-runtime-report.service`는 오래 걸리는 배치다
  - 그래서 특정 시점에는 unit/proc는 새 값(`--top-n 4`)인데, 기존 날짜 report 본문은 이전 실행 결과를 잠시 유지할 수 있다
  - 이 경우 snapshot-only 검증 (`--refresh-from-backend-snapshot`)으로 새 렌더링 결과를 먼저 확인할 수 있다

## 자주 쓰는 명령

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m backtesting.optimize
PYTHONPATH=. python -m backtesting.reselect_runtime
PYTHONPATH=. python -m backtesting.reselect_runtime --write-backend
PYTHONPATH=. python -m backtesting.reselect_runtime --refresh-from-backend-snapshot --top-n 4
uvicorn backend.main:app --port 8002
```

## 문서 정본

- 상세 구현/배포 이력: `PROGRESS.md`
- 사용자/운영 안내: `README.md`
- 텔레그램 운영 안내: `docs/superpowers/telegram-commands.md`

## 남은 관찰 포인트

- EC2 full runtime-report one-shot 완료 후 해당 날짜 report 본문이 실제로 `Top-N setting: 4`로 다시 써졌는지 추후 확인
- Claude CLI는 현재 로그인 안 된 상태라 교차 리뷰가 막혀 있음 (`claude /login` 필요)
