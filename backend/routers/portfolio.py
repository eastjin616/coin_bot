import logging
import pyupbit
from fastapi import APIRouter
from backend.execution.coin_executor import CoinExecutor
from backend.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/portfolio")
def get_portfolio():
    """현재 보유 코인 + KRW 잔고 + 평가금액 반환"""
    settings = get_settings()
    executor = CoinExecutor()

    krw_balance = executor.get_balance_krw()
    holdings = []
    total_value = krw_balance

    try:
        upbit = pyupbit.Upbit(settings.upbit_access_key, settings.upbit_secret_key)
        balances = upbit.get_balances() or []
    except Exception as e:
        logger.error(f"업비트 잔고 조회 실패: {e}")
        balances = []

    coin_symbols = [
        f"KRW-{b['currency']}"
        for b in balances
        if b.get("currency") != "KRW" and float(b.get("balance", 0)) > 0
    ]

    if coin_symbols:
        try:
            prices = pyupbit.get_current_price(coin_symbols) or {}
        except Exception as e:
            logger.error(f"현재가 조회 실패: {e}")
            prices = {}
    else:
        prices = {}

    for b in balances:
        currency = b.get("currency", "")
        if currency == "KRW":
            continue
        quantity = float(b.get("balance", 0))
        if quantity <= 0:
            continue
        symbol = f"KRW-{currency}"
        avg_price = float(b.get("avg_buy_price", 0))
        current_price = float(prices.get(symbol, avg_price) or avg_price)
        eval_value = quantity * current_price
        profit_rate = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
        total_value += eval_value
        holdings.append({
            "symbol": symbol,
            "quantity": quantity,
            "avg_price": avg_price,
            "current_price": current_price,
            "eval_value": eval_value,
            "profit_rate": round(profit_rate, 2),
        })

    return {
        "krw_balance": krw_balance,
        "holdings": holdings,
        "total_value": round(total_value, 0),
    }
