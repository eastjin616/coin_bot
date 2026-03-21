# API 비용 최적화 + 매매 전략 업그레이드 설계 문서

**날짜:** 2026-03-21
**프로젝트:** coin_bot
**목표:** GPT 호출 비용 절감 + RSI 기반 동적 임계값으로 매매 성과 개선

---

## 배경 및 문제

- 현재 5분마다 5개 코인 무조건 GPT 분석 → 시간당 60회 호출
- OpenAI 잔액 $6.64 (약 13일치) — 비용 소진 속도 빠름
- 매수/매도 임계값 70%/20% 고정 — RSI 상태 무관하게 동일 기준 적용
- 결과: 변동성 없는 횡보 구간에서도 API 낭비, 과매도/과매수 신호를 제대로 활용 못함

---

## 설계 개요

### A. 스마트 변동성 필터 (비용 최적화)

GPT 호출 전에 이미 계산된 RSI/거래량 데이터로 "분석할 가치가 있는지" 판단.
가치 없으면 skip → GPT 호출 안 함.

**변동성 점수 계산 로직** (`orchestrator.py` 수정):

```
skip 조건 (모두 해당하면 GPT 호출 안 함):
  - RSI가 45~55 사이 (중립 구간)
  - 거래량 추세가 "보합" (volume_trend == "보합")
  - MA5와 MA20 차이가 0.5% 미만
```

**코인별 차별화**:
- BTC, ETH: skip 기준 강화 (RSI 48~52, 거래량 보합) → 더 자주 분석
- SOL, XRP, DOGE: skip 기준 완화 (RSI 45~55, 거래량 보합) → 더 많이 스킵

**예상 효과**: GPT 호출 약 30~50% 감소 (횡보장 기준 최대 50%)

---

### B. RSI 기반 동적 임계값 (전략 개선)

RSI 상태에 따라 매수/매도 임계값을 실시간으로 조정.

```
RSI < 30 (과매도 구간) → buy_threshold = 65%   (더 쉽게 매수)
RSI 30~70 (중립 구간) → buy_threshold = 기본값 유지 (현재 config 기준 80%)
RSI > 70 (과매수 구간) → buy_threshold = 85%   (더 어렵게 매수, 손실 방지)

sell_threshold는 항상 20% 고정 (변경 없음)
```

> **주의:** `config.py`의 `signal_buy_threshold` 기본값은 80.0. RSI > 70 구간에서는 85%로 올려야 의미 있음 (80% 그대로면 효과 없음).

**적용 위치**: `orchestrator.py`의 `analyze_and_trade()` 메서드

**예상 효과**:
- 과매도 구간에서 매수 기회 확대
- 과매수 구간에서 무분별한 추격 매수 방지

---

## 구현 범위

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `backend/orchestrator.py` | GPT 호출 전 변동성 필터 추가 + 동적 임계값 로직 |
| `backend/config.py` | 코인별 skip 기준값 설정 추가 (선택) |

### 추가 파일 없음
- 새 파일 생성 불필요
- DB 스키마 변경 불필요
- 텔레그램 알림 변경 불필요

---

## 구현 상세

### 1. 변동성 필터 (`orchestrator.py`)

**호출 순서 변경 (중요):** 기존 `generate_chart() → get_coin_indicators() → GPT` 순서를
`get_coin_indicators() → 필터 체크 → generate_chart() → GPT` 로 바꿈.
→ 필터 통과 못하면 차트 생성(pyupbit 네트워크 호출 + 디스크 쓰기)도 생략

**강제 분석 주기:** 코인별 `last_analyzed_at` 딕셔너리 (in-memory) 관리.
연속 스킵이 30분 이상이면 강제로 GPT 분석 실행 (기회 완전 누락 방지).

```python
# Orchestrator.__init__에 추가
self._last_analyzed: dict[str, datetime] = {}
self._max_skip_minutes = 30  # 최대 30분 연속 skip 허용

def _should_skip_analysis(self, symbol: str, indicators: dict) -> bool:
    """변동성 낮으면 True (GPT 호출 skip)"""
    # 지표 없으면 skip 안 함 (데이터 오류 시 분석 시도)
    if not indicators:
        return False

    # 30분 이상 스킵됐으면 강제 분석
    last = self._last_analyzed.get(symbol)
    if last and (datetime.now() - last).seconds > self._max_skip_minutes * 60:
        return False

    rsi = indicators.get("rsi", 50)
    volume_trend = indicators.get("volume_trend", "보합")
    ma5 = indicators.get("ma5", 0)
    ma20 = indicators.get("ma20", 1)

    ma_diff_pct = abs(ma5 - ma20) / ma20 * 100 if ma20 else 0

    # 코인별 RSI 중립 범위 (유동성 높은 코인은 더 좁게 잡아 더 자주 분석)
    tight_coins = ["KRW-BTC", "KRW-ETH"]
    rsi_neutral = (48, 52) if symbol in tight_coins else (45, 55)

    is_rsi_neutral = rsi_neutral[0] <= rsi <= rsi_neutral[1]
    is_volume_flat = volume_trend == "보합"
    is_ma_flat = ma_diff_pct < 0.5

    return is_rsi_neutral and is_volume_flat and is_ma_flat
```

### 2. 동적 임계값 (`orchestrator.py`)

```python
def _get_dynamic_thresholds(self, indicators: dict) -> tuple[float, float]:
    """RSI 상태에 따라 동적 임계값 반환 (buy_threshold, sell_threshold)"""
    rsi = indicators.get("rsi", 50)

    if rsi < 30:      # 과매도
        buy_threshold = 65.0
    elif rsi > 70:    # 과매수
        buy_threshold = 85.0
    else:             # 중립
        buy_threshold = self.settings.signal_buy_threshold  # config 기본값 (현재 80%)

    sell_threshold = self.settings.signal_sell_threshold  # 항상 20% 고정
    return buy_threshold, sell_threshold
```

---

## 예상 비용 절감

| 시나리오 | 현재 호출/일 | 개선 후 호출/일 | 절감률 |
|---------|------------|--------------|--------|
| 횡보장 (변동성 낮음) | 1,440회 | ~720회 | ~50% |
| 트렌드장 (변동성 높음) | 1,440회 | ~1,000회 | ~30% |
| 평균 | 1,440회 | ~900회 | ~37% |

현재 하루 약 $0.51 소진 → 개선 후 약 $0.32 소진 예상

---

## 성공 기준

1. GPT 호출 횟수 30% 이상 감소 (로그로 확인)
2. skip된 코인에 대한 로그 남김 (`SKIP: {symbol} - RSI neutral, volume flat`)
3. 동적 임계값이 적용될 때 로그 남김 (`RSI={rsi}, buy_threshold={threshold}`)
4. 기존 매매 로직 (익절/손절/쿨다운) 변경 없음

---

## 롤백 계획

- 변동성 필터: `.env`에 `ENABLE_VOLATILITY_FILTER=false` 추가로 비활성화 가능
- 동적 임계값: `.env`에 `ENABLE_DYNAMIC_THRESHOLD=false` 추가로 비활성화 가능
- 언제든지 기존 고정 임계값 방식으로 복귀 가능
