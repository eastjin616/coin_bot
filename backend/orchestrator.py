import asyncio
import logging
import pytz
from datetime import datetime, time as dtime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.config import get_settings
from backend.database import get_db_conn
from backend.ai.vision_engine import VisionEngine
from backend.ai.chart_generator import generate_chart
from backend.execution.stock_executor import StockExecutor
from backend.execution.coin_executor import CoinExecutor
from backend.telegram_bot import send_trade_alert

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

def is_stock_market_open() -> bool:
    now_kst = datetime.now(KST)
    if now_kst.weekday() >= 5:
        return False
    market_open = dtime(9, 0)
    market_close = dtime(15, 30)
    return market_open <= now_kst.time() <= market_close

def is_on_cooldown(symbol: str, action: str, cooldown_minutes: int) -> bool:
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT last_executed_at FROM cooldowns WHERE symbol = %s AND action = %s", (symbol, action))
        row = cur.fetchone()
        conn.close()
        if not row:
            return False
        last_executed = row[0].replace(tzinfo=pytz.utc)
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
        return [{"symbol": r[0], "name": r[1]} for r in rows]
    except Exception as e:
        logger.error(f"감시 종목 조회 실패: {e}")
        return []

class Orchestrator:
    def __init__(self):
        self.settings = get_settings()
        model_path = self.settings.vision_model_path or None
        self.vision = VisionEngine(model_path=model_path)
        self.stock_executor = StockExecutor()
        self.coin_executor = CoinExecutor()
        self.scheduler = AsyncIOScheduler()

    async def analyze_and_trade(self, market: str, symbol: str, name: str):
        try:
            chart_path = generate_chart(market, symbol)
            buy_prob = self.vision.predict(chart_path)

            buy_threshold = self.settings.signal_buy_threshold
            sell_threshold = self.settings.signal_sell_threshold

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

            result = None
            if market == "stock":
                result = self.stock_executor.buy(symbol, buy_prob) if action == "BUY" else self.stock_executor.sell(symbol, buy_prob)
            elif market == "coin":
                result = self.coin_executor.buy(symbol, buy_prob) if action == "BUY" else self.coin_executor.sell(symbol, buy_prob)

            if result:
                update_cooldown(symbol, action)
                await send_trade_alert(
                    market=market,
                    symbol=name or symbol,
                    action=action,
                    confidence=buy_prob,
                    price=result.get("price", 0),
                    quantity=result.get("quantity", 0)
                )
                logger.info(f"✅ {action} 완료: {symbol} ({buy_prob:.1f}%)")
        except Exception as e:
            logger.error(f"분석/매매 오류 [{symbol}]: {e}")

    async def run_stock_cycle(self):
        if not is_stock_market_open():
            return
        for item in get_watchlist("stock"):
            await self.analyze_and_trade("stock", item["symbol"], item["name"] or item["symbol"])

    async def run_coin_cycle(self):
        for item in get_watchlist("coin"):
            await self.analyze_and_trade("coin", item["symbol"], item["name"] or item["symbol"])

    def start(self):
        interval = self.settings.poll_interval_seconds
        self.scheduler.add_job(self.run_stock_cycle, "interval", seconds=interval, id="stock_cycle")
        self.scheduler.add_job(self.run_coin_cycle, "interval", seconds=interval, id="coin_cycle")
        self.scheduler.start()
        logger.info(f"✅ 오케스트레이터 시작 (폴링 주기: {interval}초)")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("오케스트레이터 종료")
