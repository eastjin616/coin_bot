import logging
import pytz
from datetime import datetime
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

    # 백테스팅 기반 코인별 RSI 임계값 오버라이드
    _RSI_OVERRIDES: dict[str, tuple[float, float]] = {
        "KRW-BTC": (50, 65),  # BTC: 50/65 최적 (+2.6%)
    }

    def _get_signal(self, symbol: str, indicators: dict) -> str:
        """일봉 RSI 기반 매매 신호 반환.
        매수: RSI < rsi_buy_threshold (과매도)
        매도: RSI > rsi_sell_threshold (과매수)
        그 외: HOLD
        """
        rsi = indicators.get("rsi", 50)
        buy_th, sell_th = self._RSI_OVERRIDES.get(
            symbol,
            (self.settings.rsi_buy_threshold, self.settings.rsi_sell_threshold)
        )

        if rsi < buy_th:
            return "BUY"
        if rsi > sell_th:
            return "SELL"
        return "HOLD"

    def _check_profit_stop(self, symbol: str) -> str | None:
        """익절/손절 조건 체크. 해당되면 'SELL' 반환, 아니면 None"""
        try:
            import pyupbit
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT entry_price FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            entry_price = float(row["entry_price"])
            current_price = pyupbit.get_current_price(symbol)
            if not current_price:
                return None
            change_pct = (current_price - entry_price) / entry_price * 100
            if change_pct >= self.settings.take_profit_percent:
                logger.info(f"익절 조건 [{symbol}]: +{change_pct:.1f}% (기준: +{self.settings.take_profit_percent}%)")
                return "SELL"
            if change_pct <= -self.settings.stop_loss_percent:
                logger.info(f"손절 조건 [{symbol}]: {change_pct:.1f}% (기준: -{self.settings.stop_loss_percent}%)")
                return "SELL"
        except Exception as e:
            logger.error(f"익절/손절 체크 오류: {e}")
        return None

    async def analyze_and_trade(self, market: str, symbol: str, name: str):
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

            # 3. RSI + MA 크로스 신호 판단
            action = self._get_signal(symbol, indicators)
            logger.info(f"TA 신호 [{symbol}]: {action} | RSI={rsi:.1f} MA5={ma5:.0f} MA20={ma20:.0f}")

            if action == "HOLD":
                return

            if is_on_cooldown(symbol, action, self.settings.cooldown_minutes):
                logger.debug(f"쿨다운 중: {symbol} {action}")
                return

            # 4. 실행
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

    async def _sell_orphaned_positions(self):
        """감시 목록에 없는 포지션(예: ETH) 자동 매도."""
        try:
            watchlist_symbols = {item["symbol"] for item in get_watchlist("coin")}
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
        await self._sell_orphaned_positions()
        for item in get_watchlist("coin"):
            await self.analyze_and_trade("coin", item["symbol"], item["name"] or item["symbol"])

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
