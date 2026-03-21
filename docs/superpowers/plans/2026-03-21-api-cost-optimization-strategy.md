# API 비용 최적화 + 매매 전략 업그레이드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GPT 호출을 평균 37% 줄이는 변동성 필터와, RSI 기반 동적 임계값으로 매매 전략을 개선한다.

**Architecture:** `orchestrator.py`에 두 개의 메서드(`_should_skip_analysis`, `_get_dynamic_thresholds`)를 추가하고, `analyze_and_trade`의 호출 순서를 바꿔 필터를 통과한 경우에만 차트 생성 → GPT 호출로 이어지게 한다. 롤백 플래그는 `config.py`로 제어한다.

**Tech Stack:** Python 3.11, FastAPI, APScheduler, pyupbit, pytest, unittest.mock

---

## 수정/생성 파일 목록

| 파일 | 역할 |
|------|------|
| `backend/config.py` | 롤백 플래그 2개 추가 |
| `backend/orchestrator.py` | `__init__`, `_should_skip_analysis`, `_get_dynamic_thresholds`, `analyze_and_trade` 수정 |
| `tests/__init__.py` | 테스트 패키지 초기화 (신규) |
| `tests/test_orchestrator.py` | 두 메서드 단위 테스트 (신규) |

---

## Task 1: 롤백 플래그 추가 (config.py)

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: config.py에 롤백 플래그 2개 추가**

`signal_sell_threshold` 바로 아래에 삽입:

```python
    # 기능 플래그 (false로 설정하면 해당 기능 비활성화)
    enable_volatility_filter: bool = True
    enable_dynamic_threshold: bool = True
```

- [ ] **Step 2: 동작 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -c "from backend.config import get_settings; s = get_settings(); print(s.enable_volatility_filter, s.enable_dynamic_threshold)"
```

Expected output: `True True`

- [ ] **Step 3: 커밋**

```bash
git add backend/config.py
git commit -m "feat: 변동성 필터 및 동적 임계값 롤백 플래그 추가 (config.py)"
```

---

## Task 2: 테스트 환경 세팅

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: tests 디렉토리 및 `__init__.py` 생성**

```bash
mkdir -p /Users/seodongjin/Documents/GitHub/coin_bot/tests
touch /Users/seodongjin/Documents/GitHub/coin_bot/tests/__init__.py
```

- [ ] **Step 2: pytest 설치 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
pip show pytest || pip install pytest
```

- [ ] **Step 3: 테스트 파일 기본 구조 생성**

`tests/test_orchestrator.py` 파일 생성:

```python
"""orchestrator.py 단위 테스트"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


def make_orchestrator():
    """Orchestrator 인스턴스를 실제 의존성 없이 생성하는 헬퍼"""
    with patch("backend.orchestrator.get_settings") as mock_settings, \
         patch("backend.orchestrator.LLMEngine"), \
         patch("backend.orchestrator.StockExecutor"), \
         patch("backend.orchestrator.CoinExecutor"), \
         patch("backend.orchestrator.AsyncIOScheduler"):
        settings = MagicMock()
        settings.signal_buy_threshold = 80.0
        settings.signal_sell_threshold = 20.0
        settings.enable_volatility_filter = True
        settings.enable_dynamic_threshold = True
        mock_settings.return_value = settings
        from backend.orchestrator import Orchestrator
        return Orchestrator()
```

- [ ] **Step 4: 테스트 파일이 임포트 오류 없이 로드되는지 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -c "import tests.test_orchestrator; print('OK')"
```

Expected output: `OK`

- [ ] **Step 5: 커밋**

```bash
git add tests/__init__.py tests/test_orchestrator.py
git commit -m "test: 오케스트레이터 테스트 환경 세팅 (pytest + mock 헬퍼)"
```

---

## Task 3: `_should_skip_analysis` 구현 (TDD)

**Files:**
- Modify: `tests/test_orchestrator.py` (테스트 추가)
- Modify: `backend/orchestrator.py` (메서드 추가)

### 3-1. 실패 테스트 먼저 작성

- [ ] **Step 1: `tests/test_orchestrator.py`에 테스트 추가**

`make_orchestrator` 함수 아래에 추가:

```python
class TestShouldSkipAnalysis:
    """_should_skip_analysis 변동성 필터 테스트"""

    def setup_method(self):
        self.orc = make_orchestrator()

    # 케이스 1: RSI 중립 + 거래량 보합 + MA 평탄 → skip
    def test_skip_when_all_neutral(self):
        indicators = {"rsi": 50, "volume_trend": "보합", "ma5": 100.0, "ma20": 100.3}
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is True

    # 케이스 2: indicators 빈 dict → skip 안 함 (데이터 오류 = 분석 시도)
    def test_no_skip_when_empty_indicators(self):
        assert self.orc._should_skip_analysis("KRW-XRP", {}) is False

    # 케이스 3: RSI 과매도 → skip 안 함
    def test_no_skip_when_rsi_oversold(self):
        indicators = {"rsi": 25, "volume_trend": "보합", "ma5": 100.0, "ma20": 100.1}
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is False

    # 케이스 4: RSI 과매수 → skip 안 함
    def test_no_skip_when_rsi_overbought(self):
        indicators = {"rsi": 75, "volume_trend": "보합", "ma5": 100.0, "ma20": 100.1}
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is False

    # 케이스 5: 거래량 증가 → skip 안 함
    def test_no_skip_when_volume_increasing(self):
        indicators = {"rsi": 50, "volume_trend": "증가", "ma5": 100.0, "ma20": 100.1}
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is False

    # 케이스 6: MA 차이 큼 → skip 안 함
    def test_no_skip_when_ma_diverged(self):
        indicators = {"rsi": 50, "volume_trend": "보합", "ma5": 100.0, "ma20": 101.5}
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is False

    # 케이스 7: BTC는 더 좁은 중립 범위 — RSI 47이면 skip 안 함 (XRP는 skip)
    def test_btc_uses_tight_rsi_range(self):
        indicators = {"rsi": 47, "volume_trend": "보합", "ma5": 100.0, "ma20": 100.1}
        assert self.orc._should_skip_analysis("KRW-BTC", indicators) is False
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is True

    # 케이스 8: 30분 이상 스킵됐으면 강제 분석 (skip 안 함)
    def test_force_analysis_after_max_skip_duration(self):
        indicators = {"rsi": 50, "volume_trend": "보합", "ma5": 100.0, "ma20": 100.1}
        # last_analyzed를 31분 전으로 설정
        self.orc._last_analyzed["KRW-XRP"] = datetime.now() - timedelta(minutes=31)
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is False

    # 케이스 9: 29분 전이면 아직 skip 가능
    def test_skip_within_max_skip_duration(self):
        indicators = {"rsi": 50, "volume_trend": "보합", "ma5": 100.0, "ma20": 100.1}
        self.orc._last_analyzed["KRW-XRP"] = datetime.now() - timedelta(minutes=29)
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is True
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m pytest tests/test_orchestrator.py::TestShouldSkipAnalysis -v
```

Expected: `AttributeError: '_should_skip_analysis' not defined` 등 실패

### 3-2. 구현

- [ ] **Step 3: `orchestrator.py`의 `Orchestrator.__init__`에 추가**

`self.scheduler = AsyncIOScheduler()` 바로 아래에 삽입:

```python
        # 변동성 필터: 코인별 마지막 GPT 분석 시각 (in-memory)
        self._last_analyzed: dict[str, datetime] = {}
        self._max_skip_minutes: int = 30
```

- [ ] **Step 4: `orchestrator.py`에 `_should_skip_analysis` 메서드 추가**

`_check_profit_stop` 메서드 바로 위에 삽입:

```python
    def _should_skip_analysis(self, symbol: str, indicators: dict) -> bool:
        """변동성 낮으면 True 반환 → GPT 호출 skip.
        지표 없거나 30분 이상 연속 skip이면 False → 강제 분석.
        """
        if not indicators:
            return False

        last = self._last_analyzed.get(symbol)
        if last and (datetime.now() - last).total_seconds() > self._max_skip_minutes * 60:
            return False

        rsi = indicators.get("rsi", 50)
        volume_trend = indicators.get("volume_trend", "보합")
        ma5 = indicators.get("ma5", 0)
        ma20 = indicators.get("ma20", 1)
        ma_diff_pct = abs(ma5 - ma20) / ma20 * 100 if ma20 else 0

        tight_coins = ["KRW-BTC", "KRW-ETH"]
        rsi_lo, rsi_hi = (48, 52) if symbol in tight_coins else (45, 55)

        return (rsi_lo <= rsi <= rsi_hi) and (volume_trend == "보합") and (ma_diff_pct < 0.5)
```

> **주의:** 파일 상단 import에 `datetime`이 이미 있는지 확인. 있으면 추가 불필요.

- [ ] **Step 5: 테스트 실행 → 통과 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m pytest tests/test_orchestrator.py::TestShouldSkipAnalysis -v
```

Expected: 9개 모두 PASSED

- [ ] **Step 6: 커밋**

```bash
git add backend/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: 변동성 필터 _should_skip_analysis 구현 및 테스트 (TDD)"
```

---

## Task 4: `_get_dynamic_thresholds` 구현 (TDD)

**Files:**
- Modify: `tests/test_orchestrator.py` (테스트 추가)
- Modify: `backend/orchestrator.py` (메서드 추가)

### 4-1. 실패 테스트 먼저 작성

- [ ] **Step 1: `tests/test_orchestrator.py`에 테스트 추가**

`TestShouldSkipAnalysis` 클래스 아래에 추가:

```python
class TestGetDynamicThresholds:
    """_get_dynamic_thresholds RSI 기반 동적 임계값 테스트"""

    def setup_method(self):
        self.orc = make_orchestrator()

    # RSI < 30 → 과매도 → 낮은 buy threshold (더 쉽게 매수)
    def test_oversold_rsi_lowers_buy_threshold(self):
        buy_t, sell_t = self.orc._get_dynamic_thresholds({"rsi": 25})
        assert buy_t == 65.0
        assert sell_t == 20.0

    # RSI > 70 → 과매수 → 높은 buy threshold (더 어렵게 매수)
    def test_overbought_rsi_raises_buy_threshold(self):
        buy_t, sell_t = self.orc._get_dynamic_thresholds({"rsi": 75})
        assert buy_t == 85.0
        assert sell_t == 20.0

    # RSI 중립 → config 기본값 사용
    def test_neutral_rsi_uses_config_default(self):
        buy_t, sell_t = self.orc._get_dynamic_thresholds({"rsi": 50})
        assert buy_t == 80.0  # mock settings 기본값
        assert sell_t == 20.0

    # RSI 경계값: 정확히 30 → 중립으로 처리
    def test_rsi_exactly_30_is_neutral(self):
        buy_t, _ = self.orc._get_dynamic_thresholds({"rsi": 30})
        assert buy_t == 80.0

    # RSI 경계값: 정확히 70 → 중립으로 처리
    def test_rsi_exactly_70_is_neutral(self):
        buy_t, _ = self.orc._get_dynamic_thresholds({"rsi": 70})
        assert buy_t == 80.0

    # indicators 빈 dict → rsi 기본값 50 사용 → 중립
    def test_empty_indicators_uses_neutral(self):
        buy_t, sell_t = self.orc._get_dynamic_thresholds({})
        assert buy_t == 80.0
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m pytest tests/test_orchestrator.py::TestGetDynamicThresholds -v
```

Expected: `AttributeError: '_get_dynamic_thresholds' not defined`

### 4-2. 구현

- [ ] **Step 3: `orchestrator.py`에 `_get_dynamic_thresholds` 메서드 추가**

`_should_skip_analysis` 메서드 바로 아래에 삽입:

```python
    def _get_dynamic_thresholds(self, indicators: dict) -> tuple[float, float]:
        """RSI 기반 동적 buy_threshold 반환. sell_threshold는 항상 고정.
        RSI < 30 (과매도) → 65%, RSI > 70 (과매수) → 85%, 중립 → config 기본값.
        """
        rsi = indicators.get("rsi", 50)

        if rsi < 30:
            buy_threshold = 65.0
        elif rsi > 70:
            buy_threshold = 85.0
        else:
            buy_threshold = self.settings.signal_buy_threshold

        return buy_threshold, self.settings.signal_sell_threshold
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m pytest tests/test_orchestrator.py::TestGetDynamicThresholds -v
```

Expected: 6개 모두 PASSED

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m pytest tests/ -v
```

Expected: 15개 모두 PASSED

- [ ] **Step 6: 커밋**

```bash
git add backend/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: RSI 기반 동적 임계값 _get_dynamic_thresholds 구현 및 테스트 (TDD)"
```

---

## Task 5: `analyze_and_trade` 통합 (필터 + 동적 임계값 적용)

**Files:**
- Modify: `backend/orchestrator.py` (`analyze_and_trade` 메서드 교체)

- [ ] **Step 1: `analyze_and_trade` 메서드 전체 교체**

기존 `analyze_and_trade` (lines 105-157)를 아래로 교체:

```python
    async def analyze_and_trade(self, market: str, symbol: str, name: str):
        try:
            # 1. 익절/손절 먼저 체크 (변경 없음)
            if market == "coin":
                forced_action = self._check_profit_stop(symbol)
                if forced_action:
                    result = self.coin_executor.sell(symbol, 100.0)
                    if result:
                        update_cooldown(symbol, "SELL")
                        await send_trade_alert(market=market, symbol=name or symbol, action="SELL",
                                               confidence=100.0, price=result.get("price", 0), quantity=result.get("quantity", 0))
                    return

            # 2. 지표 먼저 조회 (chart 생성 전에 필터 판단)
            indicators = get_coin_indicators(symbol) if market == "coin" else {}

            # 3. 변동성 필터: 코인만 적용, 낮으면 GPT + 차트 생성 전부 skip
            if self.settings.enable_volatility_filter and market == "coin" and self._should_skip_analysis(symbol, indicators):
                rsi_val = indicators.get('rsi', 'N/A')
                rsi_str = f"{rsi_val:.1f}" if isinstance(rsi_val, (int, float)) else str(rsi_val)
                logger.info(f"SKIP [{symbol}]: RSI={rsi_str} vol={indicators.get('volume_trend')} → GPT 호출 생략")
                return

            # 4. 필터 통과 → 차트 생성 → GPT 호출
            chart_path = generate_chart(market, symbol)
            buy_prob = self.vision.predict(chart_path, indicators=indicators)
            self._last_analyzed[symbol] = datetime.now()  # skip 타이머 리셋

            provider = "OpenAI" if self.settings.openai_api_key else ("Gemini" if self.settings.gemini_api_key else "랜덤")
            logger.info(f"AI 신호 [{symbol}]: {buy_prob:.1f}% ({provider}) RSI={indicators.get('rsi', 'N/A')}")

            # 5. 동적 임계값 적용
            if self.settings.enable_dynamic_threshold and market == "coin":
                buy_threshold, sell_threshold = self._get_dynamic_thresholds(indicators)
                rsi_val = indicators.get('rsi', 'N/A')
                rsi_str = f"{rsi_val:.1f}" if isinstance(rsi_val, (int, float)) else str(rsi_val)
                logger.info(f"동적 임계값 [{symbol}]: RSI={rsi_str} → buy={buy_threshold}% sell={sell_threshold}%")
            else:
                buy_threshold = self.settings.signal_buy_threshold
                sell_threshold = self.settings.signal_sell_threshold

            # 6. 매매 결정
            if buy_prob >= buy_threshold:
                action = "BUY"
            elif buy_prob < sell_threshold:
                action = "SELL"
            else:
                logger.debug(f"HOLD: {symbol} ({buy_prob:.1f}%)")
                return

            if is_on_cooldown(symbol, action, self.settings.cooldown_minutes):
                logger.debug(f"쿨다운 중: {symbol} {action}")
                return

            # 7. 실행 (변경 없음)
            result = None
            if market == "stock":
                result = self.stock_executor.buy(symbol, buy_prob) if action == "BUY" else self.stock_executor.sell(symbol, buy_prob)
            elif market == "coin":
                result = self.coin_executor.buy(symbol, buy_prob) if action == "BUY" else self.coin_executor.sell(symbol, buy_prob)

            if result:
                update_cooldown(symbol, action)
                await send_trade_alert(
                    market=market, symbol=name or symbol, action=action,
                    confidence=buy_prob, price=result.get("price", 0), quantity=result.get("quantity", 0)
                )
                logger.info(f"✅ {action} 완료: {symbol} ({buy_prob:.1f}%)")
        except Exception as e:
            logger.error(f"분석/매매 오류 [{symbol}]: {e}")
```

> **참고:** RSI 포맷은 위 코드에서 이미 안전하게 처리됨 (`isinstance` 체크 적용).

- [ ] **Step 2: 전체 테스트 통과 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m pytest tests/ -v
```

Expected: 15개 모두 PASSED

- [ ] **Step 3: 서버 문법 오류 없는지 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -c "from backend.orchestrator import Orchestrator; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 커밋**

```bash
git add backend/orchestrator.py
git commit -m "feat: analyze_and_trade에 변동성 필터 + 동적 임계값 통합 적용"
```

---

## Task 6: EC2 배포

**Files:** 없음 (배포만)

- [ ] **Step 1: EC2에 코드 동기화**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
  -e "ssh -i ~/Downloads/coin-bot-key.pem" \
  . ubuntu@43.203.227.201:/home/ubuntu/coin_bot/
```

- [ ] **Step 2: 서비스 재시작**

```bash
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201 "sudo systemctl restart coinbot"
```

- [ ] **Step 3: 로그 확인 (30초 관찰)**

```bash
ssh -i ~/Downloads/coin-bot-key.pem ubuntu@43.203.227.201 "sudo journalctl -u coinbot -f -n 30"
```

Expected 로그 패턴 (정상):
```
SKIP [KRW-XRP]: RSI=50.3 vol=보합 → GPT 호출 생략
AI 신호 [KRW-BTC]: 72.3% (OpenAI) RSI=68.1
동적 임계값 [KRW-BTC]: RSI=68.1 → buy=80.0% sell=20.0%
```

- [ ] **Step 4: PROGRESS.md 업데이트 후 커밋**

`PROGRESS.md`에 아래 내용 추가:

```markdown
## 2026-03-21: API 비용 최적화 + 매매 전략 업그레이드

### 변경 내용
- **변동성 필터 추가**: RSI 중립(45~55) + 거래량 보합 + MA 차이 0.5% 미만이면 GPT 호출 skip
  - BTC/ETH: 더 좁은 중립 범위(48~52) → 더 자주 분석
  - 최대 30분 연속 skip 방지 (기회 완전 누락 차단)
- **RSI 기반 동적 임계값**: RSI<30 → 65%, 중립 → 80%, RSI>70 → 85%
- **호출 순서 개선**: indicators 먼저 → 필터 → chart 생성 → GPT (불필요한 pyupbit 호출 제거)
- **롤백 플래그**: .env에서 `ENABLE_VOLATILITY_FILTER=false` / `ENABLE_DYNAMIC_THRESHOLD=false` 설정 후 서비스 재시작으로 비활성화 가능

### 예상 효과
- GPT 호출 평균 37% 감소 (횡보장 최대 50%)
- 과매도 구간 매수 기회 확대, 과매수 추격 매수 방지
```

```bash
git add PROGRESS.md
git commit -m "docs: API 비용 최적화 + 전략 업그레이드 PROGRESS.md 업데이트"
```
