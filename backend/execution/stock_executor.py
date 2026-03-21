import logging
import yfinance as yf
from backend.config import get_settings
from backend.database import get_db_conn

logger = logging.getLogger(__name__)

class StockExecutor:
    def __init__(self):
        self.settings = get_settings()
        self.has_api = bool(
            self.settings.mirae_asset_app_key and
            self.settings.mirae_asset_app_secret and
            self.settings.mirae_asset_account
        )
        if self.has_api:
            logger.info("미래에셋 API 연결 완료")
        else:
            logger.warning("미래에셋 API 키 없음 — 모의 모드로 동작")

    def get_current_price(self, symbol: str) -> float:
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            if data.empty:
                return 0.0
            return float(data["Close"].iloc[-1])
        except Exception as e:
            logger.error(f"현재가 조회 실패 {symbol}: {e}")
            return 0.0

    def get_balance_krw(self) -> float:
        if not self.has_api:
            return self.settings.stock_budget_krw
        return self.settings.stock_budget_krw

    def buy(self, symbol: str, confidence: float) -> dict | None:
        price = self.get_current_price(symbol)
        if price <= 0:
            logger.error(f"현재가 조회 실패: {symbol}")
            return None
        balance = self.get_balance_krw()
        order_amount = balance * self.settings.order_size_ratio
        quantity = order_amount / price
        logger.info(f"[{'미래에셋' if self.has_api else '모의'}] {symbol} 매수 {quantity:.4f}주 @ {price:.0f}원")
        self._save_trade(symbol, "BUY", confidence, price, quantity)
        self._save_position(symbol, price, quantity)
        return {"symbol": symbol, "action": "BUY", "price": price, "quantity": quantity}

    def sell(self, symbol: str, confidence: float) -> dict | None:
        price = self.get_current_price(symbol)
        if price <= 0:
            return None
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("SELECT quantity FROM positions WHERE market = 'stock' AND symbol = %s", (symbol,))
            row = cur.fetchone()
            conn.close()
            if not row:
                logger.warning(f"보유 수량 없음: {symbol}")
                return None
            quantity = float(row["quantity"])
        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            return None
        logger.info(f"[{'미래에셋' if self.has_api else '모의'}] {symbol} 매도 {quantity:.4f}주 @ {price:.0f}원")
        self._save_trade(symbol, "SELL", confidence, price, quantity)
        self._remove_position(symbol)
        return {"symbol": symbol, "action": "SELL", "price": price, "quantity": quantity}

    def _save_trade(self, symbol, action, confidence, price, quantity):
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO trades (market, symbol, action, confidence, price, quantity) VALUES (%s,%s,%s,%s,%s,%s)",
                ("stock", symbol, action, confidence, price, quantity)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"거래 저장 실패: {e}")

    def _save_position(self, symbol, price, quantity):
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO positions (market, symbol, entry_price, quantity) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                ("stock", symbol, price, quantity)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"포지션 저장 실패: {e}")

    def _remove_position(self, symbol):
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM positions WHERE market = 'stock' AND symbol = %s", (symbol,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"포지션 삭제 실패: {e}")
