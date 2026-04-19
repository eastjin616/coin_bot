# Telegram Commands

coin_bot 운영용 텔레그램 명령어와 자동 알림 정리.

## 전제

- 봇 토큰: `.env`의 `TELEGRAM_BOT_TOKEN`
- 허용 사용자: `.env`의 `TELEGRAM_ALLOWED_CHAT_IDS`
- 허용되지 않은 chat_id 에서는 운영 명령 사용 불가

## 명령어

### `/start`

봇 소개와 사용 가능한 기본 명령어를 보여준다.

### `/balance`

현재 업비트 KRW 잔고와 DB 기준 보유 포지션을 보여준다.

포함 내용:
- KRW 잔고
- 보유 심볼
- 수량
- 평균 진입가

### `/status`

현재 운영 상태를 한 번에 보여주는 핵심 명령어.

포함 내용:
- 보유 포지션별 미실현 손익
- 각 보유 포지션의 확정 일봉 기준 RSI
- 장세 (`risk_on` / `caution` / `risk_off`)
- 신호 기준 시각
  - 마지막 확정 일봉 시각
- 권장 매수 비중
- 현재 허용 종목
- 선발 점수 요약
  - `effective_selection_score` 기준
- 제외 요약
  - `live` = 실전 성과 기반 일시 제외
  - `score` = 연구/실전 종합 점수에서 밀림
- 실전 성과로 일시 제외된 종목
- 연속 손실 쿨다운 종목
- 최근 30일 실현손익 / 승률 / 매도 횟수
- KRW 잔고

### `/performance`

최근 실현 성과를 기간별로 요약해서 보여준다.

포함 내용:
- 최근 `7/14/30일` 실현손익
- 승률
- 평균 실현 손익률
- 매수/매도 횟수
- `runtime_params.json` 등록 종목 전체 기준 최고/최저 종목
- 현재 `base-enabled` 코어 기준 최고/최저 종목

### `/watchlist`

현재 신규매수 허용 종목, 보유 종목, 수동 override 상태를 함께 보여준다.

### `/watchlist_remove <symbol>`

해당 심볼의 신규매수를 막는다.

- watchlist row를 지우는 방식이 아니라 `runtime_params`에 `manual_override=disabled`를 기록
- 이미 보유 중인 포지션의 청산 관리까지 끊지는 않음

예:
- `/watchlist_remove BTC`
- `/watchlist_remove TRX`

### `/watchlist_add <symbol>`

해당 심볼의 신규매수 허용을 다시 켠다.

- `runtime_params`에 `manual_override=enabled`를 기록

예:
- `/watchlist_add BTC`
- `/watchlist_add TRX`

### `/list`

운영용 명령어 요약을 다시 출력한다.

### `/dca`

현재 보유 포지션별 DCA 상태를 보여준다.

포함 내용:
- 현재 DCA 활성 여부
- 심볼별 `dca_count / max_dca_count`
- 직전 매수 RSI
- 다음 DCA 발동 RSI
- 남은 DCA 가능 횟수

## 자동 알림

### 매수/매도 체결 알림

자동매매가 체결되면 즉시 전송된다.

포함 내용:
- 종목
- 체결가
- 수량
- 금액
- RSI
- 매도 시 손익

### 잔고 부족 알림

매수 신호가 나왔지만 최소 주문금액이 부족하면 전송된다.

### 디스크 경고

서버 디스크 사용량이 높아지면 전송된다.

### 일일 포지션 리포트

매일 오전 `09:00 KST` 전송.

포함 내용:
- 보유 포지션별 미실현 손익
- 합산 미실현 손익
- KRW 잔고

### 실현 성과 리포트

매일 오전 `09:05 KST` 전송.

포함 내용:
- 최근 `7/14/30일` 실현 손익
- 승률 / 평균 실현 손익률
- 매수/매도 횟수
- runtime-managed / base-enabled 기준 최고·최저 종목

### runtime auto-apply 결과 알림

`coinbot-runtime-report.timer` 실행 시 전송된다.

포함 내용:
- auto-apply 성공/보류 여부
- enabled 종목 집합
- 추가/제거 종목
- 변경 수
- 보류 사유
- 생성된 리포트 파일명

### DCA 추가매수 알림

DCA 조건 충족 후 추가매수가 체결되면 전송된다.

포함 내용:
- 심볼
- 체결가
- 현재 RSI
- 갱신된 평균단가

### 분할 매도 알림

부분 청산이 체결되면 전송된다.

포함 내용:
- 심볼
- 매도 비율
- 현재 RSI
- 체결가
- 손익

## 운영 메모

- `/status`의 RSI는 **현재 진행 중인 일봉이 아니라 마지막 확정 일봉 기준**이다.
- `/performance`와 실현 성과 리포트는 `runtime_params` 전체와 현재 `base-enabled` 코어를 각각 따로 요약한다.
- `/watchlist_remove` / `/watchlist_add` 는 DB watchlist 삭제가 아니라 `runtime_params`의 durable `manual_override`를 갱신하는 방식이다.
- `/dca` 는 포지션의 `dca_count`, `last_buy_rsi` 를 읽어서 다음 발동 가능 RSI를 계산한다.
- runtime auto-apply는 안전 게이트를 통과한 경우에만 `runtime_params.json`을 자동 갱신한다.
- 텔레그램 알림이 안 오면 먼저 `TELEGRAM_ALLOWED_CHAT_IDS` 설정과 서버 로그를 확인한다.
