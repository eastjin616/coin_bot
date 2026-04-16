"""orchestrator.py 현재 로직 단위 테스트"""
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

from backend.runtime_status import is_risk_off_market

def make_orchestrator():
    """실제 외부 의존성 없이 Orchestrator 생성"""
    with patch("backend.orchestrator.get_settings") as mock_settings, \
         patch("backend.orchestrator.CoinExecutor"), \
         patch("backend.orchestrator.AsyncIOScheduler"):
        settings = MagicMock()
        settings.rsi_buy_threshold = 35.0
        settings.rsi_sell_threshold = 55.0
        settings.take_profit_percent = 3.0
        settings.stop_loss_percent = 5.0
        settings.cooldown_minutes = 5
        settings.max_open_positions = 12
        settings.max_buys_per_day = 48
        settings.target_position_budget_krw = 0
        settings.min_order_amount_krw = 10000
        settings.max_order_amount_krw = 50000
        settings.max_hold_days = 10
        settings.time_stop_min_pnl_pct = 0.0
        settings.weak_trend_rsi_buffer = 7.0
        settings.manual_holding_policy = "alert_only"
        settings.manual_holding_min_value_krw = 10000
        mock_settings.return_value = settings
        from backend.orchestrator import Orchestrator
        return Orchestrator()


class TestGetSignal:
    def setup_method(self):
        self.orc = make_orchestrator()

    def test_buy_signal_when_rsi_below_threshold(self):
        assert self.orc._get_signal("KRW-SOL", {"rsi": 29}) == "BUY"

    def test_sell_signal_when_rsi_above_threshold_and_position_exists(self):
        with patch.object(self.orc, "_has_position", return_value=True):
            assert self.orc._get_signal("KRW-SOL", {"rsi": 75}) == "SELL"

    def test_hold_signal_when_rsi_above_threshold_without_position(self):
        with patch.object(self.orc, "_has_position", return_value=False):
            assert self.orc._get_signal("KRW-SOL", {"rsi": 60}) == "HOLD"

    def test_coin_override_thresholds_apply(self):
        with patch.object(self.orc, "_has_position", return_value=True):
            assert self.orc._get_signal("KRW-BTC", {"rsi": 34}) == "BUY"
            assert self.orc._get_signal("KRW-BTC", {"rsi": 66}) == "SELL"

    def test_buy_requires_deeper_oversold_when_short_ma_is_below_long_ma(self):
        assert self.orc._get_signal("KRW-SOL", {"rsi": 33, "ma5": 95, "ma20": 100}) == "HOLD"
        assert self.orc._get_signal("KRW-SOL", {"rsi": 22, "ma5": 95, "ma20": 100}) == "BUY"


class TestRuntimeFilters:
    def setup_method(self):
        self.orc = make_orchestrator()

    def test_buy_enabled_symbols_are_limited(self):
        assert self.orc._is_buy_enabled_symbol("KRW-BCH") is True
        assert self.orc._is_buy_enabled_symbol("KRW-ADA") is True
        assert self.orc._is_buy_enabled_symbol("KRW-LINK") is True
        assert self.orc._is_buy_enabled_symbol("KRW-BTC") is False
        assert self.orc._is_buy_enabled_symbol("KRW-TRX") is False

    def test_risk_off_requires_multiple_bearish_signals(self):
        indicators = {
            "rsi": 42,
            "ma5": 95,
            "ma20": 100,
            "current_price": 97,
        }
        assert is_risk_off_market(indicators) is True

    def test_risk_off_is_false_with_single_signal(self):
        indicators = {
            "rsi": 44,
            "ma5": 101,
            "ma20": 100,
            "current_price": 101,
        }
        assert is_risk_off_market(indicators) is False

    def test_sync_runtime_watchlist_deactivates_and_upserts_symbols(self):
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        with patch("backend.orchestrator.get_db", return_value=mock_conn):
            asyncio.run(self.orc._sync_runtime_watchlist())

        executed = mock_cur.execute.call_args_list
        assert len(executed) >= 2
        first_query = executed[0].args[0]
        assert "SELECT symbol FROM positions" in first_query
        assert any("UPDATE watchlist" in call.args[0] for call in executed[1:])
        assert any("INSERT INTO watchlist" in call.args[0] for call in executed[1:])

    def test_sync_runtime_watchlist_keeps_held_symbols_active(self):
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = [{"symbol": "KRW-ADA"}]

        with patch("backend.orchestrator.get_db", return_value=mock_conn):
            asyncio.run(self.orc._sync_runtime_watchlist())

        insert_calls = [call for call in mock_cur.execute.call_args_list if "INSERT INTO watchlist" in call.args[0]]
        inserted_symbols = [call.args[1][0] for call in insert_calls]
        assert "KRW-ADA" in inserted_symbols

    def test_reduce_deprioritized_position_when_in_profit(self):
        indicators = {"current_price": 101.5, "rsi": 40}
        with patch.object(self.orc, "_is_buy_enabled_symbol", return_value=False), \
             patch.object(self.orc, "_has_position", return_value=True), \
             patch.object(self.orc, "_get_position_entry_price", return_value=100.0):
            assert self.orc._should_reduce_deprioritized_position("KRW-ADA", indicators) is True

    def test_do_not_reduce_deprioritized_position_when_underwater(self):
        indicators = {"current_price": 98.0, "rsi": 40}
        with patch.object(self.orc, "_is_buy_enabled_symbol", return_value=False), \
             patch.object(self.orc, "_has_position", return_value=True), \
             patch.object(self.orc, "_get_position_entry_price", return_value=100.0):
            assert self.orc._should_reduce_deprioritized_position("KRW-ADA", indicators) is False


class TestRiskCaps:
    def test_effective_max_open_positions_respects_seed_budget(self):
        orc = make_orchestrator()
        orc.settings.max_open_positions = 12
        orc.settings.target_position_budget_krw = 50000

        with patch.object(orc, "_estimate_total_equity_krw", return_value=90000):
            assert orc._effective_max_open_positions() == 1

    def test_estimate_total_equity_prefers_mark_to_market_holdings(self):
        orc = make_orchestrator()
        with patch.object(orc.coin_executor, "get_balance_krw", return_value=20000.0), \
             patch.object(orc.coin_executor, "get_all_coin_holdings", return_value=[
                 {"symbol": "KRW-LINK", "eval_value": 45000.0},
                 {"symbol": "KRW-SAND", "eval_value": 55000.0},
             ]):
            assert orc._estimate_total_equity_krw() == 120000.0

    def test_buy_order_ratio_concentrates_when_slots_are_limited(self):
        orc = make_orchestrator()
        orc.settings.target_position_budget_krw = 50000

        with patch.object(orc, "_effective_max_open_positions", return_value=2), \
             patch("backend.orchestrator.count_open_coin_positions", return_value=0):
            assert orc._get_buy_order_ratio("risk_on") == 0.5

    def test_max_open_positions_blocks_new_buy(self):
        orc = make_orchestrator()
        orc.settings.max_open_positions = 2

        async def run():
            with patch.object(orc, "_check_profit_stop", return_value=None), \
                 patch("backend.orchestrator.get_coin_signal_indicators", return_value={"rsi": 30, "ma5": 100, "ma20": 100}), \
                 patch.object(orc, "_has_position", return_value=False), \
                 patch("backend.orchestrator.count_open_coin_positions", return_value=2), \
                 patch("backend.orchestrator.count_coin_buys_kst_today", return_value=0), \
                 patch("backend.orchestrator.is_on_cooldown", return_value=False), \
                 patch.object(orc.coin_executor, "buy") as mock_buy:
                await orc.analyze_and_trade("coin", "KRW-SOL", "SOL", bear_market=False, market_regime="risk_on")
            mock_buy.assert_not_called()

        asyncio.run(run())


class TestRunCycle:
    def test_run_coin_cycle_reconciles_order_journal_first(self):
        orc = make_orchestrator()

        async def run():
            with patch.object(orc.coin_executor, "reconcile_open_order_journal", return_value={"checked": 0, "completed": 0, "canceled": 0, "pending": 0, "errors": 0}) as mock_reconcile, \
                 patch.object(orc, "_sync_runtime_watchlist") as mock_sync, \
                 patch.object(orc, "_cleanup_zombie_positions") as mock_cleanup, \
                 patch.object(orc, "_sell_orphaned_positions") as mock_orphan, \
                 patch("backend.orchestrator.get_coin_signal_indicators", return_value={"rsi": 50, "ma5": 100, "ma20": 100, "current_price": 100}), \
                 patch("backend.orchestrator.get_watchlist", return_value=[]):
                mock_sync.return_value = None
                mock_cleanup.return_value = None
                mock_orphan.return_value = None
                await orc.run_coin_cycle()
            mock_reconcile.assert_called_once()

        asyncio.run(run())

    def test_max_buys_per_day_blocks_buy(self):
        orc = make_orchestrator()
        orc.settings.max_buys_per_day = 1

        async def run():
            with patch.object(orc, "_check_profit_stop", return_value=None), \
                 patch("backend.orchestrator.get_coin_signal_indicators", return_value={"rsi": 30, "ma5": 100, "ma20": 100}), \
                 patch.object(orc, "_has_position", return_value=False), \
                 patch("backend.orchestrator.count_open_coin_positions", return_value=0), \
                 patch("backend.orchestrator.count_coin_buys_kst_today", return_value=1), \
                 patch("backend.orchestrator.is_on_cooldown", return_value=False), \
                 patch.object(orc.coin_executor, "buy") as mock_buy:
                await orc.analyze_and_trade("coin", "KRW-SOL", "SOL", bear_market=False, market_regime="risk_on")
            mock_buy.assert_not_called()

        asyncio.run(run())

    def test_processed_signal_blocks_duplicate_buy_on_same_candle(self):
        orc = make_orchestrator()
        candle_time = datetime(2026, 4, 9, 9, 0, 0)

        async def run():
            with patch.object(orc, "_check_profit_stop", return_value=None), \
                 patch.object(orc, "_has_position", return_value=False), \
                 patch.object(orc, "_has_processed_signal", return_value=True), \
                 patch("backend.orchestrator.count_open_coin_positions", return_value=0), \
                 patch("backend.orchestrator.count_coin_buys_kst_today", return_value=0), \
                 patch("backend.orchestrator.is_on_cooldown", return_value=False), \
                 patch.object(orc.coin_executor, "buy") as mock_buy:
                await orc.analyze_and_trade(
                    "coin",
                    "KRW-LINK",
                    "LINK",
                    bear_market=False,
                    market_regime="risk_on",
                    indicators={"rsi": 44.0, "ma5": 1, "ma20": 1, "signal_candle_time": candle_time},
                )
            mock_buy.assert_not_called()

        asyncio.run(run())


class TestManualHoldings:
    def test_reconcile_manual_holdings_skips_closing_when_exchange_lookup_fails(self):
        orc = make_orchestrator()

        async def run():
            with patch.object(orc.coin_executor, "get_all_coin_holdings_snapshot", return_value=(False, [])), \
                 patch.object(orc, "_close_missing_manual_holdings") as mock_close, \
                 patch.object(orc, "_upsert_manual_holding_record") as mock_upsert, \
                 patch("backend.orchestrator.send_message") as mock_send:
                await orc._reconcile_manual_holdings()

            mock_close.assert_not_called()
            mock_upsert.assert_not_called()
            mock_send.assert_not_called()

        asyncio.run(run())

    def test_reconcile_manual_holdings_alerts_only_for_untracked_exchange_asset(self):
        orc = make_orchestrator()
        orc.settings.manual_holding_policy = "alert_only"

        async def run():
            with patch.object(orc.coin_executor, "get_all_coin_holdings_snapshot", return_value=(True, [
                {
                    "symbol": "KRW-SAND",
                    "quantity": 100.0,
                    "avg_buy_price": 1000.0,
                    "current_price": 1100.0,
                    "eval_value": 110000.0,
                }
            ])), \
                 patch.object(orc, "_coin_position_symbols", return_value=set()), \
                 patch.object(orc, "_load_manual_holding_record", return_value=None), \
                 patch.object(orc, "_upsert_manual_holding_record") as mock_upsert, \
                 patch.object(orc, "_import_manual_holding") as mock_import, \
                 patch("backend.orchestrator.send_message") as mock_send:
                await orc._reconcile_manual_holdings()

            mock_import.assert_not_called()
            mock_upsert.assert_called_once()
            mock_send.assert_called_once()
            assert "KRW-SAND" in mock_send.await_args.args[0]
            assert "alert_only" in mock_send.await_args.args[0]

        asyncio.run(run())

    def test_reconcile_manual_holdings_imports_when_policy_is_import(self):
        orc = make_orchestrator()
        orc.settings.manual_holding_policy = "import"

        async def run():
            with patch.object(orc.coin_executor, "get_all_coin_holdings_snapshot", return_value=(True, [
                {
                    "symbol": "KRW-SAND",
                    "quantity": 100.0,
                    "avg_buy_price": 1000.0,
                    "current_price": 1100.0,
                    "eval_value": 110000.0,
                }
            ])), \
                 patch.object(orc, "_coin_position_symbols", return_value=set()), \
                 patch.object(orc, "_load_manual_holding_record", return_value=None), \
                 patch.object(orc, "_upsert_manual_holding_record") as mock_upsert, \
                 patch.object(orc, "_import_manual_holding", return_value=True) as mock_import, \
                 patch("backend.orchestrator.send_message") as mock_send:
                await orc._reconcile_manual_holdings()

            mock_import.assert_called_once_with("KRW-SAND", quantity=100.0, entry_price=1000.0)
            mock_upsert.assert_called_once()
            assert mock_upsert.call_args.kwargs["status"] == "import"
            mock_send.assert_called_once()
            assert "편입" in mock_send.await_args.args[0]

        asyncio.run(run())

    def test_close_missing_manual_holdings_marks_closed(self):
        orc = make_orchestrator()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        with patch("backend.orchestrator.get_db", return_value=mock_conn):
            orc._close_missing_manual_holdings({"KRW-LINK"})

        sql = mock_cur.execute.call_args.args[0]
        params = mock_cur.execute.call_args.args[1]
        assert "UPDATE manual_holdings" in sql
        assert params == (["KRW-LINK"],)
        assert mock_conn.commit.call_count == 1
