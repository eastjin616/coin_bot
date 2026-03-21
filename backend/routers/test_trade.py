from fastapi import APIRouter
from backend.execution.coin_executor import CoinExecutor

router = APIRouter(prefix="/api/test", tags=["test"])

@router.post("/buy/{symbol}")
def test_buy(symbol: str, amount: float = 10000):
    """테스트 매수 — 금액 직접 지정 (기본 10,000원)"""
    executor = CoinExecutor()
    result = executor.buy_fixed_amount(symbol, confidence=99.0, amount_krw=amount)
    if result:
        return {"status": "매수 완료", "result": result}
    return {"status": "매수 실패"}

@router.post("/sell/{symbol}")
def test_sell(symbol: str):
    """테스트 매도 — 실제 업비트 API 호출"""
    executor = CoinExecutor()
    result = executor.sell(symbol, confidence=1.0)
    if result:
        return {"status": "매도 완료", "result": result}
    return {"status": "매도 실패 (보유 수량 없음)"}
