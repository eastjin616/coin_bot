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
