# 2026-04-09 Live Feedback Loop

상태: `completed`

## 목표

최근 실전 성과를 단순 디레이팅에만 쓰지 않고, 런타임 우선순위 점수에도 반영한다.

## 체크리스트

- [x] 최근 실전 성과 기반 `live_score_adjustment` 계산 추가
- [x] `runtime_selection_meta` 에 `effective_selection_score` 노출
- [x] 오케스트레이터 진입 우선순위가 `effective_selection_score` 를 반영하도록 수정
- [x] 문서/메모 업데이트
