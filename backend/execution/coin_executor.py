import logging
import time
from datetime import datetime

import pyupbit
from backend.config import get_settings
from backend.database import get_db

logger = logging.getLogger(__name__)


def get_current_prices_safe(symbols: list[str]) -> dict[str, float]:
    """지원하지 않는 심볼이 섞여도 가능한 가격만 안전하게 조회한다."""
    wanted = [symbol for symbol in symbols if symbol]
    if not wanted:
        return {}

    try:
        supported = set(pyupbit.get_tickers("KRW"))
    except Exception as e:
        logger.warning("지원 KRW 심볼 조회 실패, 개별 현재가 조회로 폴백: %s", e)
        supported = set(wanted)

    prices: dict[str, float] = {}
    query_symbols = [symbol for symbol in wanted if symbol in supported]
    unsupported = sorted(set(wanted) - set(query_symbols))
    if unsupported:
        logger.info("현재가 조회 제외 심볼: %s", ", ".join(unsupported))

    for symbol in query_symbols:
        try:
            price = pyupbit.get_current_price(symbol)
            if isinstance(price, dict):
                price = price.get(symbol, 0.0)
            prices[symbol] = float(price or 0.0)
        except Exception as e:
            logger.warning("개별 현재가 조회 실패 (%s): %s", symbol, e)

    return prices

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

    def _fetch_order_snapshot(self, order_uuid: str) -> dict | None:
        """복구 루프용 단일 주문 조회."""
        try:
            return self.upbit.get_order(order_uuid)
        except Exception as e:
            logger.warning("주문 스냅샷 조회 실패 (%s): %s", order_uuid, e)
            return None

    def _fetch_recent_done_orders(self, symbol: str, limit: int = 5) -> list[dict]:
        """심볼별 최근 체결 주문 조회. pyupbit 반환 형태 차이를 흡수한다."""
        if not self.upbit:
            return []
        try:
            result = self.upbit.get_order(symbol, state="done", limit=limit, contain_req=True)
        except Exception as e:
            logger.warning("최근 체결 주문 조회 실패 (%s): %s", symbol, e)
            return []

        payload = result[0] if isinstance(result, tuple) else result
        if payload is None:
            return []
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []

    def _load_pending_order_journal(self, limit: int = 20) -> list[dict]:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT order_uuid, market, symbol, action, requested_amount_krw,
                           requested_quantity, entry_price_snapshot, order_created_at, status
                    FROM order_journal
                    WHERE status IN ('submitted', 'persist_failed', 'reconciling')
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return list(cur.fetchall())
        except Exception as e:
            logger.error("미완료 주문 저널 조회 실패: %s", e)
            return []

    def _trade_already_recorded(self, order_uuid: str) -> bool:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM trades WHERE order_uuid = %s", (order_uuid,))
                return cur.fetchone() is not None
        except Exception as e:
            logger.warning("기존 주문 기록 확인 실패 (%s): %s", order_uuid, e)
            return False

    def _order_journal_exists(self, order_uuid: str) -> bool:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM order_journal WHERE order_uuid = %s", (order_uuid,))
                return cur.fetchone() is not None
        except Exception as e:
            logger.warning("주문 저널 존재 확인 실패 (%s): %s", order_uuid, e)
            return False

    def _position_entry_price(self, symbol: str) -> float:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT entry_price FROM positions WHERE market = 'coin' AND symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
            return float(row["entry_price"] or 0.0) if row else 0.0
        except Exception as e:
            logger.warning("포지션 진입가 조회 실패 (%s): %s", symbol, e)
            return 0.0

    def _reconstruct_entry_price_from_trades(self, symbol: str, cutoff_ts: datetime | None = None) -> float:
        """체결 이력으로 해당 시점 직전의 평균 진입가를 재구성한다."""
        try:
            with get_db() as conn:
                cur = conn.cursor()
                if cutoff_ts is None:
                    cur.execute(
                        """
                        SELECT action, price, quantity
                        FROM trades
                        WHERE market = 'coin' AND symbol = %s
                        ORDER BY executed_at ASC, id ASC
                        """,
                        (symbol,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT action, price, quantity
                        FROM trades
                        WHERE market = 'coin' AND symbol = %s AND executed_at < %s
                        ORDER BY executed_at ASC, id ASC
                        """,
                        (symbol, cutoff_ts),
                    )
                rows = cur.fetchall()
        except Exception as e:
            logger.warning("체결 이력 기반 진입가 복원 실패 (%s): %s", symbol, e)
            return 0.0

        open_qty = 0.0
        avg_entry = 0.0
        for row in rows:
            action = str(row.get("action") or "").upper()
            qty = float(row.get("quantity") or 0.0)
            price = float(row.get("price") or 0.0)
            if qty <= 0 or price < 0:
                continue
            if action == "BUY":
                new_qty = open_qty + qty
                if new_qty <= 0:
                    open_qty = 0.0
                    avg_entry = 0.0
                elif open_qty <= 0:
                    open_qty = qty
                    avg_entry = price
                else:
                    avg_entry = ((avg_entry * open_qty) + (price * qty)) / new_qty
                    open_qty = new_qty
            elif action == "SELL":
                if qty >= open_qty:
                    open_qty = 0.0
                    avg_entry = 0.0
                else:
                    open_qty -= qty
        return avg_entry if open_qty > 0 else 0.0

    def _parse_exchange_created_at(self, value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _record_order_submission(
        self,
        *,
        symbol: str,
        action: str,
        order_uuid: str,
        requested_amount_krw: float | None = None,
        requested_quantity: float | None = None,
        entry_price_snapshot: float | None = None,
        order_created_at: datetime | None = None,
    ) -> None:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO order_journal (
                        order_uuid, market, symbol, action, requested_amount_krw,
                        requested_quantity, entry_price_snapshot, order_created_at, status, updated_at
                    )
                    VALUES (%s, 'coin', %s, %s, %s, %s, %s, COALESCE(%s, NOW()), 'submitted', NOW())
                    ON CONFLICT (order_uuid)
                    DO UPDATE SET
                        requested_amount_krw = COALESCE(EXCLUDED.requested_amount_krw, order_journal.requested_amount_krw),
                        requested_quantity = COALESCE(EXCLUDED.requested_quantity, order_journal.requested_quantity),
                        entry_price_snapshot = COALESCE(EXCLUDED.entry_price_snapshot, order_journal.entry_price_snapshot),
                        order_created_at = COALESCE(order_journal.order_created_at, EXCLUDED.order_created_at),
                        updated_at = NOW(),
                        last_error = NULL,
                        status = CASE
                            WHEN order_journal.status = 'completed' THEN order_journal.status
                            ELSE 'submitted'
                        END
                    """,
                    (
                        order_uuid,
                        symbol,
                        action,
                        requested_amount_krw,
                        requested_quantity,
                        entry_price_snapshot,
                        order_created_at,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error("주문 제출 저널 기록 실패 [%s %s %s]: %s", symbol, action, order_uuid, e)

    def _mark_order_journal_status(self, order_uuid: str, status: str, *, last_error: str | None = None) -> None:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE order_journal
                    SET
                        status = %s,
                        last_error = %s,
                        updated_at = NOW(),
                        reconciled_at = CASE
                            WHEN %s IN ('completed', 'canceled') THEN NOW()
                            ELSE reconciled_at
                        END
                    WHERE order_uuid = %s
                    """,
                    (status, last_error, status, order_uuid),
                )
                conn.commit()
        except Exception as e:
            logger.warning("주문 저널 상태 갱신 실패 (%s -> %s): %s", order_uuid, status, e)

    def reconcile_open_order_journal(self, limit: int = 20) -> dict[str, int]:
        summary = {"checked": 0, "completed": 0, "canceled": 0, "pending": 0, "errors": 0}
        if not self.upbit:
            return summary

        for row in self._load_pending_order_journal(limit=limit):
            order_uuid = row["order_uuid"]
            symbol = row["symbol"]
            action = row["action"]
            summary["checked"] += 1

            if self._trade_already_recorded(order_uuid):
                self._mark_order_journal_status(order_uuid, "completed")
                summary["completed"] += 1
                continue

            self._mark_order_journal_status(order_uuid, "reconciling")
            detail = self._fetch_order_snapshot(order_uuid)
            if not detail:
                self._mark_order_journal_status(order_uuid, "persist_failed", last_error="snapshot lookup failed")
                summary["errors"] += 1
                continue

            if detail.get("state") == "cancel":
                self._mark_order_journal_status(order_uuid, "canceled")
                summary["canceled"] += 1
                continue

            quantity = float(detail.get("executed_volume") or 0.0)
            if not (detail.get("state") == "done" or quantity > 0):
                self._mark_order_journal_status(order_uuid, "submitted")
                summary["pending"] += 1
                continue

            price = float(detail.get("avg_price") or detail.get("price") or 0.0)
            if action == "BUY" and price == 0 and quantity > 0:
                requested_amount = float(row.get("requested_amount_krw") or 0.0)
                if requested_amount > 0:
                    price = requested_amount / quantity

            if action == "BUY":
                ok = self._record_buy_fill(symbol, order_uuid, 100.0, price, quantity)
            else:
                entry_price = float(row.get("entry_price_snapshot") or 0.0)
                if entry_price <= 0:
                    entry_price = self._reconstruct_entry_price_from_trades(symbol, row.get("order_created_at"))
                pnl_krw = (price - entry_price) * quantity if entry_price > 0 else 0.0
                pnl_pct = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0
                ok = self._record_sell_fill(
                    symbol,
                    order_uuid,
                    100.0,
                    price,
                    quantity,
                    pnl_krw=pnl_krw,
                    pnl_pct=pnl_pct,
                )

            if ok:
                self._mark_order_journal_status(order_uuid, "completed")
                summary["completed"] += 1
            else:
                self._mark_order_journal_status(order_uuid, "persist_failed", last_error="fill persistence failed")
                summary["errors"] += 1

        return summary

    def backfill_recent_done_orders(self, symbols: list[str], *, per_symbol_limit: int = 5) -> dict[str, int]:
        """최근 체결 주문 중 local journal/trades에 없는 UUID를 복구 큐에 넣는다."""
        summary = {"symbols": 0, "orders_seen": 0, "seeded": 0}
        if not self.upbit:
            return summary

        seen_symbols: set[str] = set()
        for symbol in symbols:
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            summary["symbols"] += 1
            for order in self._fetch_recent_done_orders(symbol, limit=per_symbol_limit):
                summary["orders_seen"] += 1
                order_uuid = order.get("uuid")
                if not order_uuid:
                    continue
                if self._trade_already_recorded(order_uuid) or self._order_journal_exists(order_uuid):
                    continue

                side = str(order.get("side") or "").lower()
                action = "BUY" if side == "bid" else "SELL" if side == "ask" else ""
                if not action:
                    continue

                executed_volume = float(order.get("executed_volume") or order.get("volume") or 0.0)
                avg_price = float(order.get("avg_price") or order.get("price") or 0.0)
                requested_amount = avg_price * executed_volume if action == "BUY" and avg_price and executed_volume else None
                created_at = self._parse_exchange_created_at(order.get("created_at"))
                if action == "SELL":
                    entry_price_snapshot = self._position_entry_price(symbol)
                    if entry_price_snapshot <= 0:
                        entry_price_snapshot = self._reconstruct_entry_price_from_trades(symbol, created_at)
                else:
                    entry_price_snapshot = None
                self._record_order_submission(
                    symbol=symbol,
                    action=action,
                    order_uuid=order_uuid,
                    requested_amount_krw=requested_amount,
                    requested_quantity=executed_volume if action == "SELL" else None,
                    entry_price_snapshot=entry_price_snapshot,
                    order_created_at=created_at,
                )
                summary["seeded"] += 1

        return summary

    def get_all_coin_holdings_snapshot(self) -> tuple[bool, list[dict]]:
        """거래소 실보유 코인 목록과 조회 성공 여부를 함께 반환한다."""
        if not self.upbit:
            logger.warning("업비트 API 미연결 — 거래소 실보유 조회 불가")
            return False, []

        try:
            balances = self.upbit.get_balances() or []
        except Exception as e:
            logger.error(f"전체 코인 잔고 조회 실패: {e}")
            return False, []

        balances = [row for row in balances if isinstance(row, dict)]
        holdings = []
        symbols = []
        for row in balances:
            currency = str(row.get("currency") or "").upper()
            if currency == "KRW":
                continue
            quantity = float(row.get("balance") or 0.0)
            if quantity <= 0:
                continue
            symbol = f"KRW-{currency}"
            symbols.append(symbol)
            holdings.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "avg_buy_price": float(row.get("avg_buy_price") or 0.0),
                }
            )

        prices = get_current_prices_safe(symbols)
        missing = [s for s in symbols if s not in prices]
        if missing:
            logger.warning(f"현재가 조회 부분 실패: {', '.join(missing)} → 평균매입가 대체")

        for row in holdings:
            current_price = prices.get(row["symbol"], row["avg_buy_price"])
            row["current_price"] = current_price
            row["eval_value"] = row["quantity"] * current_price

        return True, holdings

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

    def get_all_coin_holdings(self) -> list[dict]:
        return self.get_all_coin_holdings_snapshot()[1]

    def buy_fixed_amount(self, symbol: str, confidence: float, amount_krw: float) -> dict | None:
        """시장가 매수 — 금액 직접 지정"""
        return self._execute_buy(symbol, confidence, amount_krw)

    def buy(self, symbol: str, confidence: float, order_size_ratio: float | None = None, *, dca_rsi: float | None = None) -> dict | None:
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
        return self._execute_buy(symbol, confidence, order_amount, dca_rsi=dca_rsi)

    def _execute_buy(self, symbol: str, confidence: float, order_amount: float, *, dca_rsi: float | None = None) -> dict | None:
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
            self._record_order_submission(
                symbol=symbol,
                action="BUY",
                order_uuid=result["uuid"],
                requested_amount_krw=order_amount,
            )
            order_detail = self._fetch_order_detail(result["uuid"])
            if not order_detail:
                return None
            quantity = float(order_detail.get("executed_volume") or 0)
            price = float(order_detail.get("avg_price") or 0)
            if price == 0 and quantity > 0:
                price = order_amount / quantity

            if not self._record_buy_fill(
                symbol,
                result["uuid"],
                confidence,
                price,
                quantity,
                dca_rsi=dca_rsi,
            ):
                return None
            self._mark_order_journal_status(result["uuid"], "completed")
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
                self._record_order_submission(
                    symbol=symbol,
                    action="SELL",
                    order_uuid=result["uuid"],
                    requested_quantity=coin_balance,
                    entry_price_snapshot=entry_price,
                )
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
                if not self._record_sell_fill(
                    symbol,
                    result["uuid"],
                    confidence,
                    price,
                    quantity,
                    pnl_krw=pnl_krw,
                    pnl_pct=pnl_pct,
                ):
                    return None
                self._mark_order_journal_status(result["uuid"], "completed")
                logger.info(f"매도 완료: {symbol} {quantity:.6f} @ {price:.0f}원 | 손익 {pnl_pct:+.2f}% ({pnl_krw:+,.0f}원)")
                return {"symbol": symbol, "action": "SELL", "price": price, "quantity": quantity, "entry_price": entry_price, "pnl_pct": pnl_pct, "pnl_krw": pnl_krw}
            else:
                logger.error(f"매도 응답 오류: {symbol} → {result}")
        except Exception as e:
            logger.error(f"매도 실패: {e}")
        return None

    def _insert_trade_row(
        self,
        cur,
        *,
        symbol: str,
        order_uuid: str | None,
        action: str,
        confidence: float,
        price: float,
        quantity: float,
        pnl_krw: float = 0.0,
        pnl_pct: float = 0.0,
    ) -> bool:
        cur.execute(
            """
            INSERT INTO trades (
                market, symbol, action, order_uuid, confidence, price, quantity, pnl_krw, pnl_pct
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (order_uuid) DO NOTHING
            RETURNING id
            """,
            ("coin", symbol, action, order_uuid, confidence, price, quantity, pnl_krw, pnl_pct),
        )
        inserted = cur.fetchone() is not None
        if not inserted and order_uuid:
            logger.warning("이미 기록된 주문 UUID 스킵: %s %s", symbol, order_uuid)
        return inserted

    def _record_buy_fill(
        self,
        symbol: str,
        order_uuid: str | None,
        confidence: float,
        price: float,
        quantity: float,
        *,
        dca_rsi: float | None = None,
    ) -> bool:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                inserted = self._insert_trade_row(
                    cur,
                    symbol=symbol,
                    order_uuid=order_uuid,
                    action="BUY",
                    confidence=confidence,
                    price=price,
                    quantity=quantity,
                )
                if inserted:
                    cur.execute(
                        """
                        INSERT INTO positions (market, symbol, entry_price, quantity, highest_price, source, dca_count, last_buy_rsi)
                        VALUES (%s, %s, %s, %s, %s, 'bot', 0, %s)
                        ON CONFLICT (market, symbol)
                        DO UPDATE SET
                            entry_price = CASE
                                WHEN positions.quantity + EXCLUDED.quantity <= 0 THEN EXCLUDED.entry_price
                                ELSE (
                                    (positions.entry_price * positions.quantity)
                                    + (EXCLUDED.entry_price * EXCLUDED.quantity)
                                ) / (positions.quantity + EXCLUDED.quantity)
                            END,
                            quantity = positions.quantity + EXCLUDED.quantity,
                            highest_price = GREATEST(
                                COALESCE(positions.highest_price, positions.entry_price, 0),
                                EXCLUDED.highest_price
                            ),
                            source = positions.source,
                            imported_at = positions.imported_at,
                            opened_at = LEAST(positions.opened_at, EXCLUDED.opened_at),
                            dca_count = CASE
                                WHEN EXCLUDED.last_buy_rsi IS NOT NULL THEN positions.dca_count + 1
                                ELSE positions.dca_count
                            END,
                            last_buy_rsi = COALESCE(EXCLUDED.last_buy_rsi, positions.last_buy_rsi)
                        """,
                        ("coin", symbol, price, quantity, price, dca_rsi),
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"매수 체결 반영 실패: {e}")
        return False

    def _record_sell_fill(
        self,
        symbol: str,
        order_uuid: str | None,
        confidence: float,
        price: float,
        quantity: float,
        *,
        pnl_krw: float = 0.0,
        pnl_pct: float = 0.0,
    ) -> bool:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                inserted = self._insert_trade_row(
                    cur,
                    symbol=symbol,
                    order_uuid=order_uuid,
                    action="SELL",
                    confidence=confidence,
                    price=price,
                    quantity=quantity,
                    pnl_krw=pnl_krw,
                    pnl_pct=pnl_pct,
                )
                if inserted:
                    cur.execute("DELETE FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"매도 체결 반영 실패: {e}")
        return False

    def _record_partial_sell_fill(
        self,
        symbol: str,
        order_uuid: str | None,
        confidence: float,
        price: float,
        quantity: float,
        *,
        pnl_krw: float = 0.0,
        pnl_pct: float = 0.0,
    ) -> bool:
        """부분 매도 체결 기록 — 포지션 삭제 대신 수량 차감 + partial_sell_done=true."""
        try:
            with get_db() as conn:
                cur = conn.cursor()
                inserted = self._insert_trade_row(
                    cur,
                    symbol=symbol,
                    order_uuid=order_uuid,
                    action="SELL",
                    confidence=confidence,
                    price=price,
                    quantity=quantity,
                    pnl_krw=pnl_krw,
                    pnl_pct=pnl_pct,
                )
                if inserted:
                    cur.execute(
                        """
                        UPDATE positions
                        SET quantity = GREATEST(quantity - %s, 0),
                            partial_sell_done = TRUE
                        WHERE market = 'coin' AND symbol = %s
                        """,
                        (quantity, symbol),
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"부분 매도 체결 반영 실패: {e}")
        return False

    def sell_partial(self, symbol: str, confidence: float, sell_pct: float = 50.0) -> dict | None:
        """보유 수량의 sell_pct%만 시장가 매도."""
        coin_balance = self.get_coin_balance(symbol)
        if coin_balance <= 0:
            logger.warning(f"보유 수량 없음: {symbol}")
            return None

        import pyupbit as _pyupbit
        current_price = _pyupbit.get_current_price(symbol) or 0
        quantity_to_sell = coin_balance * sell_pct / 100.0
        estimated_value = quantity_to_sell * current_price

        if estimated_value < 5000:
            logger.warning(f"부분 매도 금액 부족: {symbol} {estimated_value:,.0f}원 (최소 5,000원)")
            return None

        if not self.upbit:
            logger.info(f"[모의] {symbol} 부분 매도 {quantity_to_sell:.6f} ({sell_pct:.0f}%)")
            return {"symbol": symbol, "action": "SELL", "price": 0, "quantity": quantity_to_sell, "partial": True}

        try:
            entry_price = 0.0
            try:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT entry_price FROM positions WHERE market='coin' AND symbol=%s", (symbol,))
                    row = cur.fetchone()
                    if row:
                        entry_price = float(row["entry_price"])
            except Exception:
                pass

            result = self._submit_sell_with_retry(symbol, quantity_to_sell)
            if not result or "uuid" not in result:
                return None

            self._record_order_submission(
                symbol=symbol,
                action="SELL",
                order_uuid=result["uuid"],
                requested_quantity=quantity_to_sell,
                entry_price_snapshot=entry_price,
            )
            order_detail = self._fetch_order_detail(result["uuid"])
            if not order_detail:
                return None

            price = float(order_detail.get("avg_price") or order_detail.get("price") or 0)
            quantity = float(order_detail.get("executed_volume") or quantity_to_sell)
            if price == 0 and quantity > 0:
                price = estimated_value / quantity

            pnl_krw = (price - entry_price) * quantity if entry_price > 0 else 0.0
            pnl_pct = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0

            if not self._record_partial_sell_fill(
                symbol, result["uuid"], confidence, price, quantity,
                pnl_krw=pnl_krw, pnl_pct=pnl_pct,
            ):
                return None

            self._mark_order_journal_status(result["uuid"], "completed")
            logger.info(f"부분 매도 완료: {symbol} {quantity:.6f} @ {price:.0f}원 ({sell_pct:.0f}%)")
            return {
                "symbol": symbol, "action": "SELL", "price": price,
                "quantity": quantity, "entry_price": entry_price,
                "pnl_krw": pnl_krw, "pnl_pct": pnl_pct, "partial": True,
            }
        except Exception as e:
            logger.error(f"부분 매도 실행 오류: {e}")
        return None

    def _remove_position(self, symbol: str):
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM positions WHERE market = 'coin' AND symbol = %s", (symbol,))
                conn.commit()
        except Exception as e:
            logger.error(f"포지션 삭제 실패: {e}")
