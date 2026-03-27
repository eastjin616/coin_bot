# backend/ai/agent_tools.py
import logging
import pyupbit
from langchain_core.tools import tool
from backend.database import get_db_conn
from backend.execution.coin_executor import CoinExecutor
from backend.config import get_settings

logger = logging.getLogger(__name__)


@tool
def get_portfolio_tool(query: str) -> str:
    """현재 보유 코인과 KRW 잔고, 평가금액을 조회한다. 포트폴리오 관련 질문에 사용."""
    settings = get_settings()
    executor = CoinExecutor()
    krw = executor.get_balance_krw()

    try:
        upbit = pyupbit.Upbit(settings.upbit_access_key, settings.upbit_secret_key)
        balances = upbit.get_balances() or []
    except Exception:
        balances = []

    coin_symbols = [
        f"KRW-{b['currency']}"
        for b in balances
        if b.get("currency") != "KRW" and float(b.get("balance", 0)) > 0
    ]
    prices = {}
    if coin_symbols:
        try:
            result = pyupbit.get_current_price(coin_symbols)
            prices = result if isinstance(result, dict) else {coin_symbols[0]: result}
        except Exception:
            pass

    lines = [f"KRW 잔고: {krw:,.0f}원"]
    total = krw
    for b in balances:
        currency = b.get("currency", "")
        if currency == "KRW":
            continue
        qty = float(b.get("balance", 0))
        if qty <= 0:
            continue
        symbol = f"KRW-{currency}"
        avg = float(b.get("avg_buy_price", 0))
        cur = float(prices.get(symbol, avg) or avg)
        val = qty * cur
        rate = ((cur - avg) / avg * 100) if avg > 0 else 0
        total += val
        lines.append(
            f"{symbol}: {qty:.6f}개, 평균단가 {avg:,.0f}원, 현재가 {cur:,.0f}원, "
            f"평가금액 {val:,.0f}원, 수익률 {rate:.1f}%"
        )

    lines.append(f"총 평가금액: {total:,.0f}원")
    return "\n".join(lines)


@tool
def get_trade_history_tool(days: str) -> str:
    """최근 N일간의 매매 내역과 실현 수익을 조회한다. 수익/손실 관련 질문에 사용. days 파라미터는 숫자 문자열."""
    try:
        n = int(days)
    except ValueError:
        n = 7

    try:
        conn = get_db_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, action, price, quantity, confidence, executed_at
                FROM trades
                WHERE market = 'coin' AND executed_at >= NOW() - INTERVAL '1 day' * %s
                ORDER BY executed_at ASC
                """,
                (n,),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return f"DB 조회 실패: {e}"

    if not rows:
        return f"최근 {n}일간 매매 내역이 없습니다."

    buys: dict[str, dict] = {}
    realized = []
    total_profit = 0.0
    for row in rows:
        sym = row["symbol"]
        if row["action"] == "BUY":
            buys[sym] = row
        elif row["action"] == "SELL" and sym in buys:
            buy = buys.pop(sym)
            profit = (float(row["price"]) - float(buy["price"])) * float(row["quantity"])
            total_profit += profit
            realized.append(
                f"{sym}: 매수 {float(buy['price']):,.0f}원 → 매도 {float(row['price']):,.0f}원, "
                f"수익 {profit:+,.0f}원"
            )

    lines = [f"최근 {n}일간 매매 내역 ({len(rows)}건):"]
    for row in sorted(rows, key=lambda r: r["executed_at"], reverse=True)[:10]:
        lines.append(
            f"  {row['executed_at'].strftime('%m/%d %H:%M')} "
            f"{row['symbol']} {row['action']} @ {float(row['price']):,.0f}원 "
            f"(AI확률: {row['confidence']:.0f}%)"
        )

    if realized:
        lines.append(f"\n실현 수익 합계: {total_profit:+,.0f}원")
        lines.append("상세:")
        lines.extend(f"  {r}" for r in realized)

    return "\n".join(lines)


@tool
def get_market_signal_tool(coin: str) -> str:
    """특정 코인의 현재 가격과 가장 최근 AI 분석 신호를 조회한다. 매매 판단 질문에 사용. coin은 'KRW-BTC' 또는 'BTC' 형식."""
    symbol = coin.upper().strip()
    if not symbol.startswith("KRW-"):
        symbol = f"KRW-{symbol}"

    try:
        price_data = pyupbit.get_current_price(symbol)
        current_price = float(price_data) if isinstance(price_data, (int, float)) else float((price_data or {}).get(symbol, 0))
    except Exception:
        current_price = 0

    try:
        conn = get_db_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT action, confidence, executed_at FROM trades
                WHERE symbol = %s AND market = 'coin'
                ORDER BY executed_at DESC LIMIT 1
                """,
                (symbol,),
            )
            row = cur.fetchone()
        conn.close()
    except Exception:
        row = None

    lines = [f"{symbol} 현재가: {current_price:,.0f}원"]
    if row:
        lines.append(
            f"최근 AI 분석 ({row['executed_at'].strftime('%m/%d %H:%M')}): "
            f"{row['action']} 신호, 확률 {row['confidence']:.0f}%"
        )
        if row["confidence"] >= 70:
            lines.append("→ AI 판단: 매수 고려 구간")
        elif row["confidence"] <= 20:
            lines.append("→ AI 판단: 매도/관망 구간")
        else:
            lines.append("→ AI 판단: 중립, 관망 권장")
    else:
        lines.append("최근 AI 분석 기록 없음")

    return "\n".join(lines)
