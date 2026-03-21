import asyncio
import logging
import pytz
from datetime import datetime, time as dtime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.config import get_settings
from backend.database import get_db_conn
from backend.ai.llm_engine import LLMEngine
from backend.ai.chart_generator import generate_chart, get_coin_indicators
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
        self.vision = LLMEngine(
            gemini_api_key=self.settings.gemini_api_key,
            anthropic_api_key=self.settings.anthropic_api_key,
            openai_api_key=self.settings.openai_api_key,
            groq_api_key=self.settings.groq_api_key,
        )
        self.stock_executor = StockExecutor()
        self.coin_executor = CoinExecutor()
        self.scheduler = AsyncIOScheduler()
        # 변동성 필터: 코인별 마지막 GPT 분석 시각 (in-memory)
        self._last_analyzed: dict[str, datetime] = {}
        self._max_skip_minutes: int = 30

    def _should_skip_analysis(self, symbol: str, indicators: dict) -> bool:
        """변동성 낮으면 True 반환 → GPT 호출 skip.
        지표 없거나 30분 이상 연속 skip이면 False → 강제 분석.
        """
        if not indicators:
            return False

        last = self._last_analyzed.get(symbol)
        if not last or (datetime.now() - last).total_seconds() > self._max_skip_minutes * 60:
            return False

        rsi = indicators.get("rsi", 50)
        volume_trend = indicators.get("volume_trend", "보합")
        ma5 = indicators.get("ma5", 0)
        ma20 = indicators.get("ma20", 1)
        ma_diff_pct = abs(ma5 - ma20) / ma20 * 100 if ma20 else 0

        tight_coins = ["KRW-BTC", "KRW-ETH"]
        rsi_lo, rsi_hi = (48, 52) if symbol in tight_coins else (45, 55)

        return (rsi_lo <= rsi <= rsi_hi) and (volume_trend == "보합") and (ma_diff_pct < 0.5)

    def _get_dynamic_thresholds(self, indicators: dict) -> tuple[float, float]:
        """RSI 기반 동적 buy_threshold 반환. sell_threshold는 항상 고정.
        RSI < 30 (과매도) → 65%, RSI > 70 (과매수) → 85%, 중립 → config 기본값.
        """
        rsi = indicators.get("rsi", 50)

        if rsi < 30:
            buy_threshold = 65.0
        elif rsi > 70:
            buy_threshold = 85.0
        else:
            buy_threshold = self.settings.signal_buy_threshold

        return buy_threshold, self.settings.signal_sell_threshold

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
            # 1. 익절/손절 먼저 체크 (변경 없음)
            if market == "coin":
                forced_action = self._check_profit_stop(symbol)
                if forced_action:
                    result = self.coin_executor.sell(symbol, 100.0)
                    if result:
                        update_cooldown(symbol, "SELL")
                        await send_trade_alert(market=market, symbol=name or symbol, action="SELL",
                                               confidence=100.0, price=result.get("price", 0), quantity=result.get("quantity", 0))
                    return

            # 2. 지표 먼저 조회 (chart 생성 전에 필터 판단)
            indicators = get_coin_indicators(symbol) if market == "coin" else {}

            # 3. 변동성 필터: 코인만 적용, 낮으면 GPT + 차트 생성 전부 skip
            if self.settings.enable_volatility_filter and market == "coin" and self._should_skip_analysis(symbol, indicators):
                rsi_val = indicators.get('rsi', 'N/A')
                rsi_str = f"{rsi_val:.1f}" if isinstance(rsi_val, (int, float)) else str(rsi_val)
                logger.info(f"SKIP [{symbol}]: RSI={rsi_str} vol={indicators.get('volume_trend')} → GPT 호출 생략")
                return

            # 4. 필터 통과 → 차트 생성 → GPT 호출
            chart_path = generate_chart(market, symbol)
            buy_prob = self.vision.predict(chart_path, indicators=indicators)
            self._last_analyzed[symbol] = datetime.now()  # skip 타이머 리셋

            provider = "OpenAI" if self.settings.openai_api_key else ("Gemini" if self.settings.gemini_api_key else "랜덤")
            logger.info(f"AI 신호 [{symbol}]: {buy_prob:.1f}% ({provider}) RSI={indicators.get('rsi', 'N/A')}")

            # 5. 동적 임계값 적용
            if self.settings.enable_dynamic_threshold and market == "coin":
                buy_threshold, sell_threshold = self._get_dynamic_thresholds(indicators)
                rsi_val = indicators.get('rsi', 'N/A')
                rsi_str = f"{rsi_val:.1f}" if isinstance(rsi_val, (int, float)) else str(rsi_val)
                logger.info(f"동적 임계값 [{symbol}]: RSI={rsi_str} → buy={buy_threshold}% sell={sell_threshold}%")
            else:
                buy_threshold = self.settings.signal_buy_threshold
                sell_threshold = self.settings.signal_sell_threshold

            # 6. 매매 결정
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

            # 7. 실행 (변경 없음)
            result = None
            if market == "stock":
                result = self.stock_executor.buy(symbol, buy_prob) if action == "BUY" else self.stock_executor.sell(symbol, buy_prob)
            elif market == "coin":
                result = self.coin_executor.buy(symbol, buy_prob) if action == "BUY" else self.coin_executor.sell(symbol, buy_prob)

            if result:
                update_cooldown(symbol, action)
                await send_trade_alert(
                    market=market, symbol=name or symbol, action=action,
                    confidence=buy_prob, price=result.get("price", 0), quantity=result.get("quantity", 0)
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
