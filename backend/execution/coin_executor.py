import logging
import pyupbit
from backend.config import get_settings
from backend.database import get_db_conn

logger = logging.getLogger(__name__)

class CoinExecutor:
    def __init__(self):
        settings = get_settings()
        if settings.upbit_access_key and settings.upbit_secret_key:
            self.upbit = pyupbit.Upbit(
                access=settings.upbit_access_key,
                secret=settings.upbit_secret_key
            )
            logger.info("업비트 API 연결 완료")
        else:
            self.upbit = None
            logger.warning("업비트 API 키 없음 — 모의 모드로 동작")
        self.settings = settings

    def get_balance_krw(self) -> float:
        """KRW 잔고 조회"""
        if not self.upbit:
            return self.settings.coin_budget_krw
        try:
            return float(self.upbit.get_balance("KRW") or 0)
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            return 0.0

    def get_coin_balance(self, symbol: str) -> float:
        """코인 잔고 조회 (예: KRW-BTC → BTC 잔고)"""
        if not self.upbit:
            return 0.0
        try:
            ticker = symbol.split("-")[1]  # KRW-BTC → BTC
            return float(self.upbit.get_balance(ticker) or 0)
        except Exception as e:
            logger.error(f"코인 잔고 조회 실패: {e}")
            return 0.0

    def buy_fixed_amount(self, symbol: str, confidence: float, amount_krw: float) -> dict | None:
        """시장가 매수 — 금액 직접 지정"""
        return self._execute_buy(symbol, confidence, amount_krw)

    def buy(self, symbol: str, confidence: float) -> dict | None:
        """시장가 매수. 잔고가 충분하면 고정 10,000원 매수."""
        krw_balance = self.get_balance_krw()
        if krw_balance < 10000:
            logger.warning(f"잔고 부족: {krw_balance:.0f}원 (최소 10,000원 필요)")
            return None
        return self._execute_buy(symbol, confidence, 10000)

    def _execute_buy(self, symbol: str, confidence: float, order_amount: float) -> dict | None:
        """실제 매수 실행"""
        if order_amount < 5000:
            logger.warning(f"주문 금액 부족: {order_amount:.0f}원 (최소 5,000원)")
            return None

        if not self.upbit:
            logger.info(f"[모의] {symbol} 매수 {order_amount:.0f}원")
            return {"symbol": symbol, "action": "BUY", "amount": order_amount, "price": 0, "quantity": 0}

        try:
            result = self.upbit.buy_market_order(symbol, order_amount)
            if result and "uuid" in result:
                # 체결 정보 조회
                import time
                time.sleep(0.5)
                order_detail = self.upbit.get_order(result["uuid"])
                price = float(order_detail.get("price") or order_detail.get("avg_price") or 0)
                quantity = float(order_detail.get("executed_volume") or 0)

                self._save_trade(symbol, "BUY", confidence, price, quantity)
                self._save_position(symbol, price, quantity)
                logger.info(f"매수 완료: {symbol} {quantity:.6f} @ {price:.0f}원")
                return {"symbol": symbol, "action": "BUY", "price": price, "quantity": quantity}
        except Exception as e:
            logger.error(f"매수 실패: {e}")
        return None

    def sell(self, symbol: str, confidence: float) -> dict | None:
        """시장가 매도. 보유 수량 전체 매도."""
        coin_balance = self.get_coin_balance(symbol)
        if coin_balance <= 0:
            logger.warning(f"보유 수량 없음: {symbol}")
            return None

        if not self.upbit:
            logger.info(f"[모의] {symbol} 매도 {coin_balance:.6f}")
            return {"symbol": symbol, "action": "SELL", "price": 0, "quantity": coin_balance}

        try:
            result = self.upbit.sell_market_order(symbol, coin_balance)
            if result and "uuid" in result:
                import time
                time.sleep(0.5)
                order_detail = self.upbit.get_order(result["uuid"])
                price = float(order_detail.get("price") or order_detail.get("avg_price") or 0)
                quantity = float(order_detail.get("executed_volume") or coin_balance)

                self._save_trade(symbol, "SELL", confidence, price, quantity)
                self._remove_position(symbol)
                logger.info(f"매도 완료: {symbol} {quantity:.6f} @ {price:.0f}원")
                return {"symbol": symbol, "action": "SELL", "price": price, "quantity": quantity}
        except Exception as e:
            logger.error(f"매도 실패: {e}")
        return None

    def _save_trade(self, symbol: str, action: str, confidence: float, price: float, quantity: float):
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO trades (market, symbol, action, confidence, price, quantity) VALUES (%s, %s, %s, %s, %s, %s)",
                ("coin", symbol, action, confidence, price, quantity)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"거래 저장 실패: {e}")

    def _save_position(self, symbol: str, price: float, quantity: float):
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT entry_price, quantity FROM positions WHERE market = 'coin' AND symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
            if row:
                old_price = float(row["entry_price"])
                old_qty = float(row["quantity"])
                new_qty = old_qty + quantity
                new_avg = (old_price * old_qty + price * quantity) / new_qty
                cur.execute(
                    "UPDATE positions SET entry_price = %s, quantity = %s WHERE market = 'coin' AND symbol = %s",
                    (new_avg, new_qty, symbol)
                )
                logger.info(f"포지션 추가매수 [{symbol}]: 평균단가 {new_avg:.0f}원, 수량 {new_qty:.6f}")
            else:
                cur.execute(
                    "INSERT INTO positions (market, symbol, entry_price, quantity) VALUES (%s, %s, %s, %s)",
                    ("coin", symbol, price, quantity)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"포지션 저장 실패: {e}")

    def _remove_position(self, symbol: str):
        try:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"포지션 삭제 실패: {e}")
