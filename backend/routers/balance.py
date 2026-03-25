from fastapi import APIRouter

router = APIRouter(prefix="/api/balance", tags=["balance"])

@router.get("")
def get_balance():
    from backend.execution.coin_executor import CoinExecutor
    coin = CoinExecutor()
    return {
        "coin_krw": coin.get_balance_krw(),
    }
