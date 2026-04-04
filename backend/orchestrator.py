import logging
import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.config import get_settings
from backend.database import get_db_conn
from backend.ai.chart_generator import get_coin_indicators
from backend.execution.coin_executor import CoinExecutor
from backend.telegram_bot import send_trade_alert, send_disk_alert, send_weekly_report

logger = logging.getLogger(__name__)

def is_on_cooldown(symbol: str, action: str, cooldown_minutes: int) -> bool:
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT last_executed_at FROM cooldowns WHERE symbol = %s AND action = %s", (symbol, action))
        row = cur.fetchone()
        conn.close()
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
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cooldowns (symbol, action, last_executed_at) VALUES (%s, %s, NOW()) ON CONFLICT (symbol, action) DO UPDATE SET last_executed_at = NOW()",
            (symbol, action)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"쿨다운 업데이트 실패: {e}")

def get_watchlist(market: str) -> list:
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT symbol, name FROM watchlist WHERE market = %s AND active = TRUE", (market,))
        rows = cur.fetchall()
        conn.close()
        return [{"symbol": r["symbol"], "name": r["name"]} for r in rows]
    except Exception as e:
        logger.error(f"감시 종목 조회 실패: {e}")
        return []

class Orchestrator:
    def __init__(self):
        self.settings = get_settings()
        self.coin_executor = CoinExecutor()
        self.scheduler = AsyncIOScheduler()

    def _get_signal(self, indicators: dict) -> str:
        """일봉 RSI 기반 매매 신호 반환.
        매수: RSI < rsi_buy_threshold (과매도)
        매도: RSI > rsi_sell_threshold (과매수)
        그 외: HOLD
        """
        rsi = indicators.get("rsi", 50)

        if rsi < self.settings.rsi_buy_threshold:
            return "BUY"
        if rsi > self.settings.rsi_sell_threshold:
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
            action = self._get_signal(indicators)
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
                    entry_price=result.get("entry_price", 0)
                )
                logger.info(f"✅ {action} 완료: {symbol}")
        except Exception as e:
            logger.error(f"분석/매매 오류 [{symbol}]: {e}")

    async def run_coin_cycle(self):
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
        self.scheduler.start()
        logger.info(f"✅ 오케스트레이터 시작 (폴링 주기: {interval}초)")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("오케스트레이터 종료")
