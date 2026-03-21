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


class TestShouldSkipAnalysis:
    """_should_skip_analysis 변동성 필터 테스트"""

    def setup_method(self):
        self.orc = make_orchestrator()

    # 케이스 1: RSI 중립 + 거래량 보합 + MA 평탄 → skip
    def test_skip_when_all_neutral(self):
        self.orc._last_analyzed["KRW-XRP"] = datetime.now()  # 방금 분석했다고 설정
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
        self.orc._last_analyzed["KRW-XRP"] = datetime.now()  # XRP는 방금 분석 → skip 가능
        assert self.orc._should_skip_analysis("KRW-BTC", indicators) is False  # BTC: 47 tight range 밖 → False
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is True   # XRP: 47 wide range 안 → True

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

    # 케이스 10: 한 번도 분석 안 된 코인은 skip 안 함 (첫 분석 강제)
    def test_no_skip_when_never_analyzed(self):
        indicators = {"rsi": 50, "volume_trend": "보합", "ma5": 100.0, "ma20": 100.1}
        # _last_analyzed에 항목 없음 (한 번도 분석 안 됨)
        assert self.orc._should_skip_analysis("KRW-XRP", indicators) is False


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
