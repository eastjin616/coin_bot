import logging
import pytz
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.config import get_settings
from backend.database import get_db
from backend.ai.chart_generator import get_coin_indicators, get_coin_signal_indicators
from backend.execution.coin_executor import CoinExecutor
from backend.telegram_bot import send_trade_alert, send_disk_alert, send_weekly_report, send_daily_position_report, send_message
from backend.runtime_params import (
    get_active_buy_symbols,
    rsi_pair,
    runtime_selection_meta,
    take_profit_percent,
    trailing_stop_pair,
)
from backend.risk_limits import count_coin_buys_kst_today, count_open_coin_positions
from backend.runtime_status import get_market_regime, get_order_size_ratio_for_regime, is_risk_off_market

logger = logging.getLogger(__name__)

def is_on_cooldown(symbol: str, action: str, cooldown_minutes: int) -> bool:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT last_executed_at FROM cooldowns WHERE symbol = %s AND action = %s", (symbol, action))
            row = cur.fetchone()
        if not row:
            return False
        last_executed = row["last_executed_at"].replace(tzinfo=pytz.utc)
        elapsed = (datetime.now(pytz.utc) - last_executed).total_seconds() / 60
        return elapsed < cooldown_minutes
    except Exception as e:
        logger.error(f"쿨다운 조회 실패: {e}")
        return False

def update_cooldown(symbol: str, action: str):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO cooldowns (symbol, action, last_executed_at) VALUES (%s, %s, NOW()) ON CONFLICT (symbol, action) DO UPDATE SET last_executed_at = NOW()",
                (symbol, action)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"쿨다운 업데이트 실패: {e}")

def get_watchlist(market: str) -> list:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT symbol, name FROM watchlist WHERE market = %s AND active = TRUE", (market,))
            rows = cur.fetchall()
        return [{"symbol": r["symbol"], "name": r["name"]} for r in rows]
    except Exception as e:
        logger.error(f"감시 종목 조회 실패: {e}")
        return []

class Orchestrator:
    def __init__(self):
        self.settings = get_settings()
        self.coin_executor = CoinExecutor()
        self.scheduler = AsyncIOScheduler()
        self._error_counts: dict[str, int] = {}  # 연속 오류 카운터
        self._last_balance_alert_at: datetime | None = None  # 잔고 부족 알림 마지막 전송 시각

    # 코인별 RSI·트레일링 파라미터는 `backend/runtime_params.json` 단일 소스

    def _is_buy_enabled_symbol(self, symbol: str) -> bool:
        return symbol in get_active_buy_symbols()

    def _get_position_entry_price(self, symbol: str) -> float | None:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT entry_price FROM positions WHERE market = 'coin' AND symbol = %s",
                    (symbol,)
                )
                row = cur.fetchone()
            return float(row["entry_price"]) if row else None
        except Exception:
            return None

    def _should_reduce_deprioritized_position(self, symbol: str, indicators: dict) -> bool:
        """운영 제외 종목은 수익권 또는 약한 매도 구간에서 우선 정리."""
        if self._is_buy_enabled_symbol(symbol):
            return False
        if not self._has_position(symbol):
            return False

        entry_price = self._get_position_entry_price(symbol)
        current_price = float(indicators.get("current_price") or 0)
        if not entry_price or not current_price:
            return False

        pnl_pct = (current_price - entry_price) / entry_price * 100
        rsi = float(indicators.get("rsi") or 50)
        _, sell_th = rsi_pair(
            symbol,
            self.settings.rsi_buy_threshold,
            self.settings.rsi_sell_threshold,
        )
        return pnl_pct >= 1.0 or rsi >= max(sell_th - 5, 55)

    async def _sync_runtime_watchlist(self):
        """운영 허용 종목과 DB watchlist를 동기화."""
        try:
            runtime_symbols = set(get_active_buy_symbols().keys())
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT symbol FROM positions WHERE market = 'coin'")
                held_symbols = {row["symbol"] for row in cur.fetchall()}

            managed_symbols = sorted(runtime_symbols | held_symbols)
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE watchlist
                    SET active = FALSE
                    WHERE market = 'coin' AND symbol <> ALL(%s)
                    """,
                    (managed_symbols,)
                )
                for symbol in managed_symbols:
                    name = get_active_buy_symbols().get(symbol, symbol.split("-")[1])
                    cur.execute(
                        """
                        INSERT INTO watchlist (market, symbol, name, active)
                        VALUES ('coin', %s, %s, TRUE)
                        ON CONFLICT (market, symbol)
                        DO UPDATE SET active = TRUE, name = EXCLUDED.name
                        """,
                        (symbol, name)
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"runtime watchlist 동기화 오류: {e}")

    def _has_position(self, symbol: str) -> bool:
        """DB에 해당 코인 포지션이 있는지 확인"""
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
                return cur.fetchone() is not None
        except Exception:
            return False

    def _coin_position_symbols(self) -> set[str]:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT symbol FROM positions WHERE market = 'coin'")
                return {row["symbol"] for row in cur.fetchall()}
        except Exception as e:
            logger.error("포지션 심볼 조회 실패: %s", e)
            return set()

    def _load_manual_holding_record(self, symbol: str) -> dict | None:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT symbol, quantity, avg_buy_price, status, note, last_alerted_at
                    FROM manual_holdings
                    WHERE symbol = %s
                    """,
                    (symbol,),
                )
                return cur.fetchone()
        except Exception as e:
            logger.warning("수동 보유 추적 조회 실패 [%s]: %s", symbol, e)
            return None

    def _upsert_manual_holding_record(
        self,
        symbol: str,
        *,
        quantity: float,
        avg_buy_price: float,
        status: str,
        note: str | None = None,
        mark_alerted: bool = False,
    ) -> None:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO manual_holdings (
                        symbol, quantity, avg_buy_price, status, note, last_seen_at, last_alerted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, NOW(), CASE WHEN %s THEN NOW() ELSE NULL END)
                    ON CONFLICT (symbol)
                    DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        avg_buy_price = EXCLUDED.avg_buy_price,
                        status = EXCLUDED.status,
                        note = EXCLUDED.note,
                        last_seen_at = NOW(),
                        last_alerted_at = CASE
                            WHEN %s THEN NOW()
                            ELSE manual_holdings.last_alerted_at
                        END
                    """,
                    (symbol, quantity, avg_buy_price, status, note, mark_alerted, mark_alerted),
                )
                conn.commit()
        except Exception as e:
            logger.warning("수동 보유 추적 저장 실패 [%s]: %s", symbol, e)

    def _import_manual_holding(self, symbol: str, *, quantity: float, entry_price: float) -> bool:
        if quantity <= 0:
            return False
        entry_price = float(entry_price or 0.0)
        if entry_price <= 0:
            return False
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO positions (market, symbol, entry_price, quantity, highest_price, source, imported_at)
                    VALUES ('coin', %s, %s, %s, %s, 'manual_import', NOW())
                    ON CONFLICT (market, symbol)
                    DO UPDATE SET
                        entry_price = EXCLUDED.entry_price,
                        quantity = EXCLUDED.quantity,
                        highest_price = GREATEST(
                            COALESCE(positions.highest_price, positions.entry_price, 0),
                            EXCLUDED.highest_price
                        ),
                        source = 'manual_import',
                        imported_at = COALESCE(positions.imported_at, NOW())
                    """,
                    (symbol, entry_price, quantity, entry_price),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error("수동 보유 포지션 편입 실패 [%s]: %s", symbol, e)
            return False

    async def _reconcile_manual_holdings(self):
        """거래소 실보유 자산 중 DB 포지션에 없는 수동 매수 종목을 감지한다."""
        try:
            holdings_ok, exchange_holdings = self.coin_executor.get_all_coin_holdings_snapshot()
            if not holdings_ok:
                logger.warning("수동 보유 종목 정리 스킵: 거래소 잔고 조회 실패")
                return
            exchange_symbols = {row["symbol"] for row in exchange_holdings}
            self._close_missing_manual_holdings(exchange_symbols)
            if not exchange_holdings:
                return

            db_symbols = self._coin_position_symbols()
            policy = str(getattr(self.settings, "manual_holding_policy", "alert_only") or "alert_only").strip().lower()
            if policy not in {"alert_only", "import", "ignore"}:
                policy = "alert_only"
            min_value = float(getattr(self.settings, "manual_holding_min_value_krw", 10000) or 10000)

            for holding in exchange_holdings:
                symbol = holding["symbol"]
                if symbol in db_symbols:
                    continue

                eval_value = float(holding.get("eval_value") or 0.0)
                if eval_value < min_value:
                    continue

                quantity = float(holding.get("quantity") or 0.0)
                avg_buy_price = float(holding.get("avg_buy_price") or 0.0)
                current_price = float(holding.get("current_price") or avg_buy_price or 0.0)
                prior = self._load_manual_holding_record(symbol)
                changed = (
                    prior is None
                    or abs(float(prior.get("quantity") or 0.0) - quantity) > 1e-12
                    or abs(float(prior.get("avg_buy_price") or 0.0) - avg_buy_price) > 1e-12
                    or str(prior.get("status") or "") != policy
                )

                if policy == "ignore":
                    self._upsert_manual_holding_record(
                        symbol,
                        quantity=quantity,
                        avg_buy_price=avg_buy_price,
                        status="ignore",
                        note="manual holding ignored by policy",
                    )
                    continue

                if policy == "import":
                    imported = self._import_manual_holding(
                        symbol,
                        quantity=quantity,
                        entry_price=avg_buy_price or current_price,
                    )
                    self._upsert_manual_holding_record(
                        symbol,
                        quantity=quantity,
                        avg_buy_price=avg_buy_price,
                        status="import" if imported else "alert_only",
                        note="manual holding imported into positions" if imported else "manual holding import failed",
                        mark_alerted=changed,
                    )
                    if imported and changed:
                        await send_message(
                            f"🧩 수동 보유 종목 편입\n\n"
                            f"{symbol} {quantity:.6f}\n"
                            f"평균단가: {avg_buy_price or current_price:,.0f}원\n"
                            f"정책: import"
                        )
                    continue

                self._upsert_manual_holding_record(
                    symbol,
                    quantity=quantity,
                    avg_buy_price=avg_buy_price,
                    status="alert_only",
                    note="manual holding detected outside bot positions",
                    mark_alerted=changed,
                )
                if changed:
                    await send_message(
                        f"👀 수동 보유 종목 감지\n\n"
                        f"{symbol} {quantity:.6f}\n"
                        f"평균단가: {avg_buy_price or current_price:,.0f}원\n"
                        f"평가금액: {eval_value:,.0f}원\n"
                        f"정책: alert_only (자동매매 미편입)"
                    )
        except Exception as e:
            logger.error("수동 보유 종목 감지 오류: %s", e)

    def _close_missing_manual_holdings(self, exchange_symbols: set[str]) -> None:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE manual_holdings
                    SET
                        status = 'closed',
                        note = 'manual holding no longer present on exchange',
                        last_seen_at = NOW()
                    WHERE status <> 'closed'
                      AND symbol <> ALL(%s)
                    """,
                    (sorted(exchange_symbols),),
                )
                conn.commit()
        except Exception as e:
            logger.warning("사라진 수동 보유 정리 실패: %s", e)

    def _estimate_total_equity_krw(self) -> float:
        """KRW 잔고 + 거래소 실보유 평가금액 기준 총자산. 실패 시 DB 원가 기준으로 폴백."""
        krw_balance = self.coin_executor.get_balance_krw()
        holdings = self.coin_executor.get_all_coin_holdings()
        if holdings:
            invested = sum(float(row.get("eval_value") or 0.0) for row in holdings)
            return krw_balance + invested

        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT COALESCE(SUM(entry_price * quantity), 0) AS invested_krw
                    FROM positions
                    WHERE market = 'coin'
                    """
                )
                row = cur.fetchone()
            invested = float(row["invested_krw"] or 0) if row else 0.0
        except Exception:
            invested = 0.0
        return krw_balance + invested

    def _effective_max_open_positions(self) -> int:
        """설정 상한과 시드 기준 집중도 상한을 함께 반영."""
        caps: list[int] = []
        if self.settings.max_open_positions > 0:
            caps.append(self.settings.max_open_positions)

        target_budget = int(getattr(self.settings, "target_position_budget_krw", 0) or 0)
        if target_budget > 0:
            total_equity = self._estimate_total_equity_krw()
            caps.append(max(1, int(total_equity // target_budget)))

        return min(caps) if caps else 0

    def _get_buy_order_ratio(self, market_regime: str) -> float:
        """장세 비중보다 과도하게 잘게 쪼개지지 않도록 남은 슬롯 기준으로 보정."""
        base_ratio = get_order_size_ratio_for_regime(market_regime)
        effective_cap = self._effective_max_open_positions()
        if effective_cap <= 0:
            return base_ratio

        open_positions = count_open_coin_positions()
        remaining_slots = max(effective_cap - open_positions, 1)
        slot_ratio = 1.0 / remaining_slots
        return max(base_ratio, slot_ratio)

    def _entry_score(self, symbol: str, indicators: dict) -> float:
        """소액 시드에서는 더 강한 RSI 신호와 검증 메타가 좋은 종목을 우선."""
        rsi = float(indicators.get("rsi") or 50)
        buy_th = self._effective_buy_threshold(symbol, indicators)
        oversold_depth = max(buy_th - rsi, 0.0)
        meta = runtime_selection_meta().get(symbol, {})
        effective_score = float(meta.get("effective_selection_score") or 0.0)
        return oversold_depth + (effective_score * 0.15)

    def _effective_buy_threshold(self, symbol: str, indicators: dict) -> float:
        buy_th, _ = rsi_pair(
            symbol,
            self.settings.rsi_buy_threshold,
            self.settings.rsi_sell_threshold,
        )
        ma5 = float(indicators.get("ma5") or 0.0)
        ma20 = float(indicators.get("ma20") or 0.0)
        weak_trend_buffer = float(getattr(self.settings, "weak_trend_rsi_buffer", 0.0) or 0.0)
        if weak_trend_buffer > 0 and ma5 and ma20 and ma5 < ma20:
            return max(buy_th - weak_trend_buffer, 0.0)
        return buy_th

    def _should_dca(self, symbol: str, current_rsi: float) -> bool:
        """직전 매수보다 RSI가 dca_step_rsi 이상 더 낮을 때 추가매수 허용."""
        if not getattr(self.settings, "dca_enabled", False):
            return False
        max_dca = int(getattr(self.settings, "max_dca_count", 2))
        step_rsi = float(getattr(self.settings, "dca_step_rsi", 5.0))
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT dca_count, last_buy_rsi FROM positions WHERE market='coin' AND symbol=%s",
                    (symbol,),
                )
                row = cur.fetchone()
            if not row:
                return False
            dca_count = int(row["dca_count"] or 0)
            if dca_count >= max_dca:
                return False
            last_rsi = float(row["last_buy_rsi"] or 100.0)
            return current_rsi <= last_rsi - step_rsi
        except Exception as e:
            logger.warning("DCA 판단 오류 [%s]: %s", symbol, e)
            return False

    def _has_processed_signal(self, market: str, symbol: str, action: str, candle_time) -> bool:
        if candle_time is None:
            return False
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT 1
                    FROM signal_locks
                    WHERE market = %s AND symbol = %s AND action = %s AND candle_time = %s
                    """,
                    (market, symbol, action, candle_time),
                )
                return cur.fetchone() is not None
        except Exception as e:
            logger.warning("signal_locks 조회 실패 [%s %s %s]: %s", market, symbol, action, e)
            return False

    def _mark_signal_processed(self, market: str, symbol: str, action: str, candle_time) -> None:
        if candle_time is None:
            return
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO signal_locks (market, symbol, action, candle_time, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (market, symbol, action)
                    DO UPDATE SET candle_time = EXCLUDED.candle_time, updated_at = NOW()
                    """,
                    (market, symbol, action, candle_time),
                )
                conn.commit()
        except Exception as e:
            logger.warning("signal_locks 저장 실패 [%s %s %s]: %s", market, symbol, action, e)

    def _get_signal(self, symbol: str, indicators: dict) -> str:
        """일봉 RSI 기반 매매 신호 반환.
        매수: RSI < 임계값 (과매도)
        매도: RSI > 임계값 AND 포지션 보유 중일 때만
        그 외: HOLD
        """
        rsi = indicators.get("rsi", 50)
        buy_th = self._effective_buy_threshold(symbol, indicators)
        _, sell_th = rsi_pair(
            symbol,
            self.settings.rsi_buy_threshold,
            self.settings.rsi_sell_threshold,
        )

        if rsi < buy_th:
            return "BUY"

        if rsi > sell_th:
            # 포지션 없으면 매도 시도 자체를 안 함
            if not self._has_position(symbol):
                return "HOLD"
            return "SELL"

        return "HOLD"

    def _check_profit_stop(self, symbol: str) -> tuple[str, str, float] | None:
        """고정 익절 + 트레일링 스탑 + 손절 체크.
        반환: (action, reason, highest_price) 또는 None
        - reason: "takeprofit" | "trailing" | "stoploss"
        - highest_price: 현재 최고가 (알림용)
        """
        try:
            import pyupbit
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT entry_price, highest_price FROM positions WHERE market = 'coin' AND symbol = %s",
                    (symbol,)
                )
                row = cur.fetchone()
            if not row:
                return None

            entry_price = float(row["entry_price"])
            highest_price = float(row["highest_price"] or entry_price)
            current_price = pyupbit.get_current_price(symbol)
            if not current_price:
                return None

            trailing_activation, stop_loss = trailing_stop_pair(
                symbol,
                self.settings.stop_loss_percent / 2,
                self.settings.stop_loss_percent,
            )

            # 1. 손절: entry_price 기준
            change_pct = (current_price - entry_price) / entry_price * 100
            if change_pct <= -stop_loss:
                logger.info(f"손절 [{symbol}]: {change_pct:.1f}% (기준: -{stop_loss}%)")
                return ("SELL", "stoploss", highest_price)

            take_profit = take_profit_percent(
                symbol,
                float(getattr(self.settings, "take_profit_percent", 0.0) or 0.0),
            )
            if take_profit > 0 and change_pct >= take_profit:
                logger.info(f"고정 익절 [{symbol}]: {change_pct:.1f}% (기준: +{take_profit}%)")
                return ("SELL", "takeprofit", highest_price)

            # 2. highest_price 갱신 (예외 발생 시 트레일링 스킵)
            try:
                if current_price > highest_price:
                    with get_db() as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE positions SET highest_price = %s WHERE market = 'coin' AND symbol = %s",
                            (current_price, symbol)
                        )
                        conn.commit()
                    highest_price = current_price
            except Exception as e:
                logger.warning(f"highest_price 갱신 실패 [{symbol}] — 트레일링 스킵: {e}")
                return None

            # 3. 트레일링 스탑: 활성화 조건 충족 시에만
            # 활성화: highest_price >= entry_price * (1 + trailing_activation/100)
            # 발동: current_price <= highest_price * (1 - stop_loss/100)
            activation_threshold = entry_price * (1 + trailing_activation / 100)
            if highest_price >= activation_threshold:
                trailing_trigger = highest_price * (1 - stop_loss / 100)
                if current_price <= trailing_trigger:
                    trail_pct = (highest_price - current_price) / highest_price * 100
                    logger.info(
                        f"트레일링 스탑 [{symbol}]: 최고가 {highest_price:.0f}원 → 현재가 {current_price:.0f}원 "
                        f"(-{trail_pct:.1f}%, 기준: -{stop_loss}%)"
                    )
                    return ("SELL", "trailing", highest_price)

        except Exception as e:
            logger.error(f"트레일링/손절 체크 오류: {e}")
        return None

    def _check_time_stop(self, symbol: str, signal_candle_time) -> tuple[str, str, int, float] | None:
        """보유 기간 초과 + 최소 수익 미달 시 일봉 기준 정리."""
        max_hold_days = int(getattr(self.settings, "max_hold_days", 0) or 0)
        if max_hold_days <= 0 or signal_candle_time is None:
            return None

        try:
            import pyupbit

            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT entry_price, opened_at
                    FROM positions
                    WHERE market = 'coin' AND symbol = %s
                    """,
                    (symbol,),
                )
                row = cur.fetchone()

            if not row or not row.get("opened_at"):
                return None

            opened_at = row["opened_at"]
            held_days = max((signal_candle_time.date() - opened_at.date()).days, 0)
            if held_days < max_hold_days:
                return None

            entry_price = float(row["entry_price"] or 0)
            current_price = pyupbit.get_current_price(symbol)
            if not current_price or not entry_price:
                return None

            pnl_pct = (current_price - entry_price) / entry_price * 100
            min_pnl_pct = float(getattr(self.settings, "time_stop_min_pnl_pct", 0.0) or 0.0)
            if pnl_pct >= min_pnl_pct:
                return None

            logger.info(
                "기간청산 [%s]: %d일 보유, 손익 %.1f%% (기준 %.1f%% 미만)",
                symbol,
                held_days,
                pnl_pct,
                min_pnl_pct,
            )
            return ("SELL", "timestop", held_days, pnl_pct)
        except Exception as e:
            logger.error(f"기간청산 체크 오류: {e}")
        return None

    async def analyze_and_trade(
        self,
        market: str,
        symbol: str,
        name: str,
        bear_market: bool = False,
        market_regime: str = "risk_on",
        indicators: dict | None = None,
    ):
        try:
            # 1. 트레일링/손절 먼저 체크
            if market == "coin":
                stop_result = self._check_profit_stop(symbol)
                if stop_result:
                    action, reason, highest_price_snapshot = stop_result
                    result = self.coin_executor.sell(symbol, 100.0)
                    if result:
                        update_cooldown(symbol, "SELL")
                        entry_price = result.get("entry_price", 0)
                        price = result.get("price", 0)
                        pnl_pct = result.get("pnl_pct", 0)
                        pnl_krw = result.get("pnl_krw", 0)

                        if reason == "trailing":
                            trail_drop = (highest_price_snapshot - price) / highest_price_snapshot * 100 if highest_price_snapshot > 0 else 0
                            await send_message(
                                f"📉 트레일링 스탑 [{name or symbol}]\n"
                                f"최고가: {highest_price_snapshot:,.0f}원 → 현재가: {price:,.0f}원 (-{trail_drop:.1f}%)\n"
                                f"진입가: {entry_price:,.0f}원 | 손익: {pnl_pct:+.2f}% ({pnl_krw:+,.0f}원)"
                            )
                        elif reason == "takeprofit":
                            await send_message(
                                f"💸 소익절 [{name or symbol}]\n"
                                f"진입가: {entry_price:,.0f}원 → 체결가: {price:,.0f}원\n"
                                f"손익: {pnl_pct:+.2f}% ({pnl_krw:+,.0f}원)"
                            )
                        else:  # stoploss
                            await send_message(
                                f"🛑 손절 [{name or symbol}]\n"
                                f"진입가: {entry_price:,.0f}원 → 체결가: {price:,.0f}원\n"
                                f"손익: {pnl_pct:+.2f}% ({pnl_krw:+,.0f}원)"
                            )
                    return

            # 2. 기술적 지표 조회
            indicators = indicators if indicators is not None else (get_coin_signal_indicators(symbol) if market == "coin" else {})
            rsi = indicators.get("rsi", 50)
            ma5 = indicators.get("ma5", 0)
            ma20 = indicators.get("ma20", 0)
            signal_candle_time = indicators.get("signal_candle_time")

            if market == "coin":
                time_stop_result = self._check_time_stop(symbol, signal_candle_time)
                if time_stop_result:
                    action, reason, held_days, snapshot_pnl_pct = time_stop_result
                    result = self.coin_executor.sell(symbol, 100.0)
                    if result:
                        update_cooldown(symbol, action)
                        self._mark_signal_processed(market, symbol, action, signal_candle_time)
                        await send_message(
                            f"⏳ 기간청산 [{name or symbol}]\n"
                            f"보유일: {held_days}일\n"
                            f"신호 시점 손익: {snapshot_pnl_pct:+.2f}%\n"
                            f"체결 손익: {result.get('pnl_pct', 0):+.2f}% ({result.get('pnl_krw', 0):+,.0f}원)"
                        )
                    return

            # 3. RSI 신호 판단
            action = self._get_signal(symbol, indicators)
            if action == "HOLD" and self._should_reduce_deprioritized_position(symbol, indicators):
                action = "SELL"
                logger.info(f"운영 제외 종목 우선 정리: {symbol} | RSI={rsi:.1f}")
            logger.info(f"TA 신호 [{symbol}]: {action} | RSI={rsi:.1f} MA5={ma5:.0f} MA20={ma20:.0f}")

            if action == "HOLD":
                return

            if action in {"BUY", "SELL"} and self._has_processed_signal(market, symbol, action, signal_candle_time):
                logger.debug("이미 처리한 일봉 신호 스킵: %s %s %s", symbol, action, signal_candle_time)
                return

            # 4. 이미 포지션 보유 중이면 DCA 조건 확인 후 차단/허용
            is_dca = False
            if action == "BUY" and self._has_position(symbol):
                if self._should_dca(symbol, rsi):
                    is_dca = True
                    logger.info(f"DCA 추가매수 조건 충족: {symbol} RSI={rsi:.1f}")
                else:
                    logger.debug(f"포지션 보유 중 — 재매수 차단: {symbol}")
                    return

            # 5. 운영 제외 심볼은 신규 매수 차단
            if action == "BUY" and not self._is_buy_enabled_symbol(symbol):
                logger.info(f"운영 제외 심볼 매수 차단: {symbol}")
                return

            # 6. 하락장 필터 — BTC 리스크오프 장세면 알트코인 매수 차단
            if action == "BUY" and bear_market and symbol != "KRW-BTC":
                logger.info(f"하락장 필터: {symbol} 매수 차단 (BTC 리스크오프)")
                return

            # 6b. 운영 리스크 캡 (신규 매수만; 설정 0이면 비활성화)
            if action == "BUY":
                effective_cap = self._effective_max_open_positions()
                if effective_cap > 0 and not self._has_position(symbol):
                    n_pos = count_open_coin_positions()
                    if n_pos >= effective_cap:
                        logger.info(
                            "리스크 캡: 보유 종목 %d/%d — %s 신규 매수 생략",
                            n_pos,
                            effective_cap,
                            symbol,
                        )
                        return
                if self.settings.max_buys_per_day > 0:
                    n_buy = count_coin_buys_kst_today()
                    if n_buy >= self.settings.max_buys_per_day:
                        logger.info(
                            "리스크 캡: 금일 매수 %d/%d회 — %s 매수 생략",
                            n_buy,
                            self.settings.max_buys_per_day,
                            symbol,
                        )
                        return

            if is_on_cooldown(symbol, action, self.settings.cooldown_minutes):
                logger.debug(f"쿨다운 중: {symbol} {action}")
                return

            # 7. 실행
            if action == "BUY":
                krw_balance = self.coin_executor.get_balance_krw()
                if krw_balance < 10000:
                    now = datetime.now(pytz.utc)
                    if self._last_balance_alert_at is None or (now - self._last_balance_alert_at) > timedelta(hours=4):
                        self._last_balance_alert_at = now
                        await send_message(
                            f"💰 잔고 부족 알림\n\n매수 기회 [{name or symbol}] RSI={rsi:.1f}\n"
                            f"현재 KRW 잔고: {krw_balance:,.0f}원 (최소 10,000원 필요)\n입금 후 자동 재개됩니다."
                        )
                    return
            if action == "BUY":
                if is_dca:
                    order_ratio = float(getattr(self.settings, "dca_order_size_ratio", 0.1))
                    result = self.coin_executor.buy(symbol, 100.0, order_size_ratio=order_ratio, dca_rsi=rsi)
                else:
                    order_ratio = self._get_buy_order_ratio(market_regime)
                    result = self.coin_executor.buy(symbol, 100.0, order_size_ratio=order_ratio, dca_rsi=rsi)
            else:
                result = self.coin_executor.sell(symbol, 100.0)

            if result:
                update_cooldown(symbol, action)
                if signal_candle_time is not None:
                    self._mark_signal_processed(market, symbol, action, signal_candle_time)
                if is_dca and action == "BUY":
                    price = result.get("price", 0)
                    entry_price = result.get("entry_price", 0)
                    await send_message(
                        f"➕ DCA 추가매수 [{name or symbol}]\n"
                        f"RSI: {rsi:.1f} | 체결가: {price:,.0f}원\n"
                        f"평균단가: {entry_price:,.0f}원"
                    )
                else:
                    await send_trade_alert(
                        market=market, symbol=name or symbol, action=action,
                        confidence=100.0, price=result.get("price", 0), quantity=result.get("quantity", 0),
                        entry_price=result.get("entry_price", 0), rsi=rsi
                    )
                logger.info(f"✅ {action} 완료: {symbol}")
        except Exception as e:
            logger.error(f"분석/매매 오류 [{symbol}]: {e}")
            err_key = f"{symbol}:{type(e).__name__}"
            self._error_counts[err_key] = self._error_counts.get(err_key, 0) + 1
            if self._error_counts[err_key] == 3:
                await send_message(f"🚨 연속 오류 경고\n\n{symbol} 에서 동일 오류 3회 반복\n{type(e).__name__}: {e}")
        else:
            # 성공 시 해당 심볼 오류 카운터 초기화
            err_key_prefix = f"{symbol}:"
            for k in list(self._error_counts.keys()):
                if k.startswith(err_key_prefix):
                    del self._error_counts[k]

    async def _cleanup_zombie_positions(self):
        """실제 업비트 잔고는 없는데 DB에만 남은 좀비 포지션 자동 정리."""
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT symbol FROM positions WHERE market = 'coin'")
                position_symbols = [r["symbol"] for r in cur.fetchall()]

            for symbol in position_symbols:
                actual_balance = self.coin_executor.get_coin_balance(symbol)
                if actual_balance <= 0:
                    logger.info(f"좀비 포지션 감지 [{symbol}] — 실제 잔고 없음, DB 정리")
                    with get_db() as conn:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
                        conn.commit()
                    await send_message(f"🧹 좀비 포지션 정리\n\n{symbol} — 실제 잔고 없음, DB에서 삭제됨")
        except Exception as e:
            logger.error(f"좀비 포지션 정리 오류: {e}")

    async def _sell_orphaned_positions(self):
        """감시 목록에 없는 포지션(예: ETH) 자동 매도."""
        try:
            watchlist_symbols = {item["symbol"] for item in get_watchlist("coin")}
            if not watchlist_symbols:
                logger.warning("감시 목록 조회 실패 또는 비어있음 — 고아 포지션 처리 건너뜀")
                return
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT symbol FROM positions WHERE market = 'coin'")
                position_symbols = [r["symbol"] for r in cur.fetchall()]

            for symbol in position_symbols:
                if symbol not in watchlist_symbols:
                    logger.info(f"고아 포지션 감지 [{symbol}] — 자동 매도 시도")
                    result = self.coin_executor.sell(symbol, 100.0)
                    if result:
                        update_cooldown(symbol, "SELL")
                        await send_trade_alert(
                            market="coin", symbol=symbol, action="SELL",
                            confidence=100.0, price=result.get("price", 0),
                            quantity=result.get("quantity", 0),
                            entry_price=result.get("entry_price", 0)
                        )
                        logger.info(f"고아 포지션 매도 완료: {symbol}")
        except Exception as e:
            logger.error(f"고아 포지션 처리 오류: {e}")

    async def run_coin_cycle(self):
        try:
            exchange_symbols = {row["symbol"] for row in self.coin_executor.get_all_coin_holdings()}
            backfill_symbols = sorted(exchange_symbols | self._coin_position_symbols() | set(get_active_buy_symbols().keys()))
        except Exception:
            backfill_symbols = sorted(self._coin_position_symbols() | set(get_active_buy_symbols().keys()))
        try:
            backfill_summary = self.coin_executor.backfill_recent_done_orders(backfill_symbols)
            if backfill_summary["seeded"] > 0:
                logger.info("주문 저널 백필 요약: %s", backfill_summary)
        except Exception as e:
            logger.error("주문 저널 백필 오류: %s", e)

        try:
            reconcile_summary = self.coin_executor.reconcile_open_order_journal()
            if reconcile_summary["checked"] > 0:
                logger.info("주문 저널 복구 요약: %s", reconcile_summary)
        except Exception as e:
            logger.error("주문 저널 복구 오류: %s", e)

        await self._reconcile_manual_holdings()
        await self._sync_runtime_watchlist()
        await self._cleanup_zombie_positions()
        await self._sell_orphaned_positions()

        # BTC 기준 장세 판단
        bear_market = False
        market_regime = "risk_on"
        try:
            btc_indicators = get_coin_signal_indicators("KRW-BTC")
            market_regime = get_market_regime(btc_indicators)
            if is_risk_off_market(btc_indicators):
                bear_market = True
                logger.warning(
                    "리스크오프 감지: "
                    f"BTC RSI={btc_indicators.get('rsi', 50):.1f}, "
                    f"MA5={btc_indicators.get('ma5', 0):.0f}, "
                    f"MA20={btc_indicators.get('ma20', 0):.0f} "
                    "— 알트코인 매수 차단"
                )
        except Exception as e:
            logger.error(f"BTC RSI 조회 실패: {e}")

        watchlist = get_watchlist("coin")
        indicators_by_symbol: dict[str, dict] = {}
        for item in watchlist:
            symbol = item["symbol"]
            try:
                indicators_by_symbol[symbol] = get_coin_signal_indicators(symbol)
            except Exception as e:
                logger.error(f"지표 선조회 실패 [{symbol}]: {e}")
                indicators_by_symbol[symbol] = {}

        ordered_watchlist = sorted(
            watchlist,
            key=lambda item: (
                0 if self._has_position(item["symbol"]) else 1,
                -self._entry_score(item["symbol"], indicators_by_symbol.get(item["symbol"], {}))
                if self._is_buy_enabled_symbol(item["symbol"]) else 0,
            ),
        )

        for item in ordered_watchlist:
            await self.analyze_and_trade(
                "coin",
                item["symbol"],
                item["name"] or item["symbol"],
                bear_market=bear_market,
                market_regime=market_regime,
                indicators=indicators_by_symbol.get(item["symbol"], {}),
            )

    def start(self):
        import pytz
        kst = pytz.timezone("Asia/Seoul")
        interval = self.settings.poll_interval_seconds
        self.scheduler.add_job(self.run_coin_cycle, "interval", seconds=interval, id="coin_cycle")
        # 매시간 디스크 체크
        self.scheduler.add_job(send_disk_alert, "interval", hours=1, id="disk_check")
        # 매일 오전 9시 5분 KST 최근 7/14/30일 성과 리포트
        self.scheduler.add_job(send_weekly_report, "cron", hour=9, minute=5, timezone=kst, id="weekly_report")
        # 매일 오전 9시 KST 일일 포지션 현황
        self.scheduler.add_job(send_daily_position_report, "cron", hour=9, minute=0, timezone=kst, id="daily_report")
        self.scheduler.start()
        logger.info(f"✅ 오케스트레이터 시작 (폴링 주기: {interval}초)")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("오케스트레이터 종료")
