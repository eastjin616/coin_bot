# 2026-04-09 Runtime Visibility Improvements

상태: `completed`

## 목표

자동 유니버스 선정과 실전 디레이팅 상태를 운영 화면과 API에서 바로 읽을 수 있게 만든다.

## 체크리스트

- [x] `/api/runtime/status` 의 `selection` 항목에 `base_enabled`, `live_derated`, `selection_score` 노출
- [x] 텔레그램 `/status` 에 실전 디레이팅 종목 요약 노출
- [x] 텔레그램 `/status` 에 상위 선발 종목의 selection score 요약 노출
- [x] 문서/메모 업데이트

## 진행 로그

### 현재 작업

- 현재 단계 완료

### 추가 반영

- 텔레그램 `/status`에 `effective_selection_score` 기준 선발 점수 표시
- 텔레그램 `/status`에 제외 요약 추가
  - `live` = 실전 성과 기반 일시 제외
  - `score` = 연구/실전 종합 점수 순위에서 밀림
