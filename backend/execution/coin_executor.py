import logging
import time

import pyupbit
from backend.config import get_settings
from backend.database import get_db

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

    def _submit_buy_with_retry(self, symbol: str, order_amount: float) -> dict | None:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                result = self.upbit.buy_market_order(symbol, order_amount)
                if result and result.get("uuid"):
                    return result
                logger.warning("buy_market_order 빈 응답 (%s) %d/3", symbol, attempt + 1)
            except Exception as e:
                last_err = e
                logger.warning("buy_market_order 예외 (%s) %d/3: %s", symbol, attempt + 1, e)
            time.sleep(0.5 * (attempt + 1))
        if last_err:
            logger.error("매수 주문 실패(3회): %s — %s", symbol, last_err)
        return None

    def _submit_sell_with_retry(self, symbol: str, volume: float) -> dict | None:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                result = self.upbit.sell_market_order(symbol, volume)
                if result and result.get("uuid"):
                    return result
                logger.warning("sell_market_order 빈 응답 (%s) %d/3", symbol, attempt + 1)
            except Exception as e:
                last_err = e
                logger.warning("sell_market_order 예외 (%s) %d/3: %s", symbol, attempt + 1, e)
            time.sleep(0.5 * (attempt + 1))
        if last_err:
            logger.error("매도 주문 실패(3회): %s — %s", symbol, last_err)
        return None

    def _fetch_order_detail(self, order_uuid: str) -> dict | None:
        """시장가 체결 확인 — get_order 일시 실패·지연 대비 재시도."""
        delays = (0.4, 0.5, 0.6, 1.0, 1.5, 2.0, 2.5, 3.0, 3.0, 3.0)
        last: dict | None = None
        for i, delay in enumerate(delays):
            if i > 0:
                time.sleep(delay)
            try:
                last = self.upbit.get_order(order_uuid)
            except Exception as e:
                logger.warning("get_order 재시도 %d/%d (%s): %s", i + 1, len(delays), order_uuid, e)
                last = None
                continue
            if not last:
                continue
            if last.get("state") == "cancel":
                logger.error("주문 취소됨: %s", order_uuid)
                return None
            vol = float(last.get("executed_volume") or 0)
            if last.get("state") == "done" or vol > 0:
                return last
        logger.error("체결 조회 타임아웃: %s", order_uuid)
        return None

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
            ticker = symbol.split("-")[1]
            return float(self.upbit.get_balance(ticker) or 0)
        except Exception as e:
            logger.error(f"코인 잔고 조회 실패: {e}")
            return 0.0

    def buy_fixed_amount(self, symbol: str, confidence: float, amount_krw: float) -> dict | None:
        """시장가 매수 — 금액 직접 지정"""
        return self._execute_buy(symbol, confidence, amount_krw)

    def buy(self, symbol: str, confidence: float, order_size_ratio: float | None = None) -> dict | None:
        """시장가 매수. 잔고 비율 기반 (최소 10,000원 / 최대 50,000원) 매수."""
        krw_balance = self.get_balance_krw()
        min_order = self.settings.min_order_amount_krw
        max_order = self.settings.max_order_amount_krw
        ratio = order_size_ratio if order_size_ratio is not None else self.settings.risk_on_order_size_ratio
        raw_amount = int(krw_balance * ratio)
        if max_order > 0:
            order_amount = max(min_order, min(raw_amount, max_order))
        else:
            order_amount = max(min_order, raw_amount)
        if krw_balance < min_order:
            logger.warning(f"잔고 부족: {krw_balance:.0f}원 (최소 {min_order:,}원 필요)")
            return None
        logger.info(f"매수 금액 결정: {order_amount:,}원 (잔고 {krw_balance:,.0f}원의 {ratio * 100:.1f}%)")
        return self._execute_buy(symbol, confidence, order_amount)

    def _execute_buy(self, symbol: str, confidence: float, order_amount: float) -> dict | None:
        """실제 매수 실행"""
        if order_amount < 5000:
            logger.warning(f"주문 금액 부족: {order_amount:.0f}원 (최소 5,000원)")
            return None

        if not self.upbit:
            logger.info(f"[모의] {symbol} 매수 {order_amount:.0f}원")
            return {"symbol": symbol, "action": "BUY", "amount": order_amount, "price": 0, "quantity": 0}

        try:
            result = self._submit_buy_with_retry(symbol, order_amount)
            if not result or "uuid" not in result:
                return None
            order_detail = self._fetch_order_detail(result["uuid"])
            if not order_detail:
                return None
            quantity = float(order_detail.get("executed_volume") or 0)
            price = float(order_detail.get("avg_price") or 0)
            if price == 0 and quantity > 0:
                price = order_amount / quantity

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

        # 업비트 최소 주문금액 5,000원 체크
        import pyupbit as _pyupbit
        current_price = _pyupbit.get_current_price(symbol) or 0
        estimated_value = coin_balance * current_price
        if estimated_value < 5000:
            logger.warning(f"매도 금액 부족: {symbol} 평가 {estimated_value:,.0f}원 (최소 5,000원) → 포지션 DB 정리")
            self._remove_position(symbol)
            return None

        if not self.upbit:
            logger.info(f"[모의] {symbol} 매도 {coin_balance:.6f}")
            return {"symbol": symbol, "action": "SELL", "price": 0, "quantity": coin_balance}

        try:
            # 포지션 entry_price 조회 (매도 전에 미리)
            entry_price = 0.0
            try:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT entry_price FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
                    row = cur.fetchone()
                    if row:
                        entry_price = float(row["entry_price"])
            except Exception:
                pass

            result = self._submit_sell_with_retry(symbol, coin_balance)
            if result and "uuid" in result:
                order_detail = self._fetch_order_detail(result["uuid"])
                if not order_detail:
                    return None
                price = float(order_detail.get("avg_price") or order_detail.get("price") or 0)
                quantity = float(order_detail.get("executed_volume") or coin_balance)
                if price == 0 and quantity > 0:
                    estimated_value = coin_balance * current_price
                    price = estimated_value / quantity  # 직접 계산

                pnl_krw = (price - entry_price) * quantity if entry_price > 0 else 0.0
                pnl_pct = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0
                self._save_trade(symbol, "SELL", confidence, price, quantity, pnl_krw=pnl_krw, pnl_pct=pnl_pct)
                self._remove_position(symbol)
                logger.info(f"매도 완료: {symbol} {quantity:.6f} @ {price:.0f}원 | 손익 {pnl_pct:+.2f}% ({pnl_krw:+,.0f}원)")
                return {"symbol": symbol, "action": "SELL", "price": price, "quantity": quantity, "entry_price": entry_price, "pnl_pct": pnl_pct, "pnl_krw": pnl_krw}
            else:
                logger.error(f"매도 응답 오류: {symbol} → {result}")
        except Exception as e:
            logger.error(f"매도 실패: {e}")
        return None

    def _save_trade(self, symbol: str, action: str, confidence: float, price: float, quantity: float,
                    pnl_krw: float = 0.0, pnl_pct: float = 0.0):
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO trades (market, symbol, action, confidence, price, quantity, pnl_krw, pnl_pct) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    ("coin", symbol, action, confidence, price, quantity, pnl_krw, pnl_pct)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"거래 저장 실패: {e}")

    def _save_position(self, symbol: str, price: float, quantity: float):
        try:
            with get_db() as conn:
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
                    # highest_price는 변경하지 않음 (추가매수 시 기존 최고가 유지)
                    logger.info(f"포지션 추가매수 [{symbol}]: 평균단가 {new_avg:.0f}원, 수량 {new_qty:.6f}")
                else:
                    cur.execute(
                        "INSERT INTO positions (market, symbol, entry_price, quantity, highest_price) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        ("coin", symbol, price, quantity, price)  # highest_price = entry_price
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"포지션 저장 실패: {e}")

    def _remove_position(self, symbol: str):
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
                conn.commit()
        except Exception as e:
            logger.error(f"포지션 삭제 실패: {e}")
