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
