import logging
import pytz
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.config import get_settings
from backend.database import get_db
from backend.ai.chart_generator import get_coin_indicators
from backend.execution.coin_executor import CoinExecutor
from backend.telegram_bot import send_trade_alert, send_disk_alert, send_weekly_report, send_daily_position_report, send_message

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

    # 백테스팅 기반 코인별 RSI 임계값 오버라이드 (일봉 ~8년치 그리드서치)
    _RSI_OVERRIDES: dict[str, tuple[float, float]] = {
        "KRW-BTC":  (50, 65),  # +2.6%
        "KRW-LINK": (50, 70),  # +30.5%
        "KRW-HBAR": (45, 70),  # +13.2%
        "KRW-BCH":  (40, 60),  # +17.0%
        "KRW-ATOM": (45, 60),  # +10.3%
        "KRW-AVAX": (45, 70),  # +4.5%
        "KRW-SUI":  (50, 70),  # +7.3%
        "KRW-UNI":  (50, 65),  # +5.3%
        "KRW-SHIB": (50, 60),  # +6.0%
    }

    # 백테스팅 기반 코인별 익절/손절 오버라이드 (take_profit%, stop_loss%)
    _PROFIT_STOP_OVERRIDES: dict[str, tuple[float, float]] = {
        "KRW-BTC":  (5,  3),   # +3.5%
        "KRW-SOL":  (10, 3),   # +5.7%
        "KRW-DOGE": (5,  5),   # +8.9%
        "KRW-DOT":  (5,  3),   # +0.9%
        "KRW-ADA":  (5,  3),   # +3.1%
        "KRW-AVAX": (8,  5),   # +5.8%
        "KRW-LINK": (15, 10),  # +33.0%
        "KRW-TRX":  (5,  10),  # +4.8%
        "KRW-SUI":  (15, 5),   # +8.0%
        "KRW-HBAR": (20, 5),   # +17.9%
        "KRW-ICP":  (5,  3),   # +0.3%
        "KRW-ATOM": (15, 5),   # +11.5%
        "KRW-UNI":  (25, 3),   # +6.4%
        "KRW-SHIB": (8,  5),   # +6.3%
        "KRW-BCH":  (15, 3),   # +18.0%
    }

    def _has_position(self, symbol: str) -> bool:
        """DB에 해당 코인 포지션이 있는지 확인"""
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
                return cur.fetchone() is not None
        except Exception:
            return False

    def _get_signal(self, symbol: str, indicators: dict) -> str:
        """일봉 RSI + MA Cross 기반 매매 신호 반환.
        매수: RSI < 임계값 AND MA5 > MA20 (상승추세 확인)
        매도: RSI > 임계값 AND 포지션 보유 중일 때만
        그 외: HOLD
        """
        rsi = indicators.get("rsi", 50)
        ma5 = indicators.get("ma5", 0)
        ma20 = indicators.get("ma20", 0)
        buy_th, sell_th = self._RSI_OVERRIDES.get(
            symbol,
            (self.settings.rsi_buy_threshold, self.settings.rsi_sell_threshold)
        )

        if rsi < buy_th:
            # MA Cross 확인 — MA5 > MA20이어야 매수 (상승추세)
            if ma5 > 0 and ma20 > 0 and ma5 > ma20:
                return "BUY"
            elif ma5 > 0 and ma20 > 0:
                logger.debug(f"MA Cross 미충족 [{symbol}]: MA5={ma5:.0f} < MA20={ma20:.0f}, 매수 보류")
                return "HOLD"
            return "BUY"  # MA 데이터 없으면 RSI만으로 판단

        if rsi > sell_th:
            # 포지션 없으면 매도 시도 자체를 안 함
            if not self._has_position(symbol):
                return "HOLD"
            return "SELL"

        return "HOLD"

    def _check_profit_stop(self, symbol: str) -> str | None:
        """익절/손절 조건 체크. 해당되면 'SELL' 반환, 아니면 None"""
        try:
            import pyupbit
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT entry_price FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
                row = cur.fetchone()
            if not row:
                return None
            entry_price = float(row["entry_price"])
            current_price = pyupbit.get_current_price(symbol)
            if not current_price:
                return None
            take_profit, stop_loss = self._PROFIT_STOP_OVERRIDES.get(
                symbol,
                (self.settings.take_profit_percent, self.settings.stop_loss_percent)
            )
            change_pct = (current_price - entry_price) / entry_price * 100
            if change_pct >= take_profit:
                logger.info(f"익절 조건 [{symbol}]: +{change_pct:.1f}% (기준: +{take_profit}%)")
                return "SELL"
            if change_pct <= -stop_loss:
                logger.info(f"손절 조건 [{symbol}]: {change_pct:.1f}% (기준: -{stop_loss}%)")
                return "SELL"
        except Exception as e:
            logger.error(f"익절/손절 체크 오류: {e}")
        return None

    async def analyze_and_trade(self, market: str, symbol: str, name: str, bear_market: bool = False):
        try:
            # 1. 익절/손절 먼저 체크
            if market == "coin":
                forced_action = self._check_profit_stop(symbol)
                if forced_action:
                    result = self.coin_executor.sell(symbol, 100.0)
                    if result:
                        update_cooldown(symbol, "SELL")
                        await send_trade_alert(market=market, symbol=name or symbol, action="SELL",
                                               confidence=100.0, price=result.get("price", 0), quantity=result.get("quantity", 0),
                                               entry_price=result.get("entry_price", 0))
                    return

            # 2. 기술적 지표 조회
            indicators = get_coin_indicators(symbol) if market == "coin" else {}
            rsi = indicators.get("rsi", 50)
            ma5 = indicators.get("ma5", 0)
            ma20 = indicators.get("ma20", 0)

            # 3. RSI 신호 판단
            action = self._get_signal(symbol, indicators)
            logger.info(f"TA 신호 [{symbol}]: {action} | RSI={rsi:.1f} MA5={ma5:.0f} MA20={ma20:.0f}")

            if action == "HOLD":
                return

            # 4. 하락장 필터 — BTC RSI < 40이면 알트코인 매수 차단
            if action == "BUY" and bear_market and symbol != "KRW-BTC":
                logger.info(f"하락장 필터: {symbol} 매수 차단 (BTC RSI 기준 하락장)")
                return

            if is_on_cooldown(symbol, action, self.settings.cooldown_minutes):
                logger.debug(f"쿨다운 중: {symbol} {action}")
                return

            # 5. 실행
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
            result = self.coin_executor.buy(symbol, 100.0) if action == "BUY" else self.coin_executor.sell(symbol, 100.0)

            if result:
                update_cooldown(symbol, action)
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
        await self._cleanup_zombie_positions()
        await self._sell_orphaned_positions()

        # BTC RSI로 하락장 여부 판단
        bear_market = False
        try:
            btc_indicators = get_coin_indicators("KRW-BTC")
            btc_rsi = btc_indicators.get("rsi", 50)
            if btc_rsi < 40:
                bear_market = True
                logger.warning(f"하락장 감지: BTC RSI={btc_rsi:.1f} < 40 — 알트코인 매수 차단")
        except Exception as e:
            logger.error(f"BTC RSI 조회 실패: {e}")

        for item in get_watchlist("coin"):
            await self.analyze_and_trade("coin", item["symbol"], item["name"] or item["symbol"], bear_market=bear_market)

    def start(self):
        import pytz
        kst = pytz.timezone("Asia/Seoul")
        interval = self.settings.poll_interval_seconds
        self.scheduler.add_job(self.run_coin_cycle, "interval", seconds=interval, id="coin_cycle")
        # 매시간 디스크 체크
        self.scheduler.add_job(send_disk_alert, "interval", hours=1, id="disk_check")
        # 매주 월요일 오전 9시 KST 주간 리포트
        self.scheduler.add_job(send_weekly_report, "cron", day_of_week="mon", hour=9, minute=0, timezone=kst, id="weekly_report")
        # 매일 오전 9시 KST 일일 포지션 현황
        self.scheduler.add_job(send_daily_position_report, "cron", hour=9, minute=0, timezone=kst, id="daily_report")
        self.scheduler.start()
        logger.info(f"✅ 오케스트레이터 시작 (폴링 주기: {interval}초)")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("오케스트레이터 종료")
