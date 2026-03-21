from fastapi import APIRouter

router = APIRouter(prefix="/api/balance", tags=["balance"])

@router.get("")
def get_balance():
    from backend.execution.stock_executor import StockExecutor
    from backend.execution.coin_executor import CoinExecutor
    stock = StockExecutor()
    coin = CoinExecutor()
    return {
        "stock_krw": stock.get_balance_krw(),
        "coin_krw": coin.get_balance_krw(),
    }
