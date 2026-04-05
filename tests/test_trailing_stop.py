"""트레일링 스탑 로직 단위 테스트"""
from unittest.mock import MagicMock, patch


def make_orchestrator():
    """Orchestrator 인스턴스를 실제 의존성 없이 생성"""
    with patch("backend.orchestrator.get_settings") as mock_settings, \
         patch("backend.orchestrator.CoinExecutor"), \
         patch("backend.orchestrator.AsyncIOScheduler"):
        settings = MagicMock()
        settings.rsi_buy_threshold = 35.0
        settings.rsi_sell_threshold = 55.0
        settings.take_profit_percent = 10.0
        settings.stop_loss_percent = 5.0
        settings.cooldown_minutes = 5
        mock_settings.return_value = settings
        from backend.orchestrator import Orchestrator
        return Orchestrator()


class TestCheckProfitStop:
    """_check_profit_stop 트레일링 스탑 테스트"""

    def setup_method(self):
        self.orc = make_orchestrator()

    def _mock_db_row(self, entry_price, highest_price):
        """DB에서 조회된 포지션 row를 흉내내는 mock"""
        return {"entry_price": entry_price, "highest_price": highest_price}

    # 케이스 1: 손절 조건 — 현재가가 entry_price 기준 -stop_loss% 이하
    def test_stop_loss_triggers(self):
        symbol = "KRW-DOGE"  # stop_loss=5%
        entry_price = 100.0
        highest_price = 102.0
        current_price = 94.0  # -6% (손절 -5% 초과)

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=current_price):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = self._mock_db_row(entry_price, highest_price)
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result == "SELL"

    # 케이스 2: 트레일링 활성화 + 발동 — 최고가 대비 -stop_loss% 하락
    def test_trailing_stop_triggers_when_activated(self):
        symbol = "KRW-DOGE"  # stop_loss=5%
        entry_price = 100.0
        highest_price = 110.0  # 활성화 조건: 100 * (1 + 5/200) = 102.5 → 110 >= 102.5 ✓
        current_price = 104.0  # 110 * (1 - 5/100) = 104.5 → 104 <= 104.5 ✓ 발동

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=current_price):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = self._mock_db_row(entry_price, highest_price)
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result == "SELL"

    # 케이스 3: 트레일링 미활성화 — 최고가가 활성화 임계값 미달
    def test_trailing_not_triggered_before_activation(self):
        symbol = "KRW-DOGE"  # stop_loss=5%, 활성화 임계: +2.5%
        entry_price = 100.0
        highest_price = 101.0  # 101 < 102.5 → 활성화 미충족
        current_price = 99.0   # 손절선(-5%): 95 → 99 > 95 → 손절도 미발동

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=current_price):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = self._mock_db_row(entry_price, highest_price)
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result is None

    # 케이스 4: 포지션 없음 → None 반환
    def test_no_position_returns_none(self):
        symbol = "KRW-SOL"

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=50000.0):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = None
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result is None

    # 케이스 5: LINK 코인별 오버라이드 — stop_loss=10%, 활성화 임계 +5%
    # 주의: Orchestrator._PROFIT_STOP_OVERRIDES는 클래스 변수로 "KRW-LINK": (15, 10) 정의됨
    # mock_settings의 stop_loss_percent=5.0 대신 오버라이드 값(10%) 이 사용되는지 검증
    def test_link_override_trailing_activation(self):
        symbol = "KRW-LINK"  # _PROFIT_STOP_OVERRIDES에서 stop_loss=10%, 활성화: entry * 1.05
        entry_price = 20000.0
        highest_price = 22000.0  # 22000 >= 21000 (20000*1.05) → 활성화 ✓
        current_price = 19700.0  # 22000 * 0.9 = 19800 → 19700 <= 19800 ✓ 발동

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=current_price):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = self._mock_db_row(entry_price, highest_price)
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result == "SELL"
