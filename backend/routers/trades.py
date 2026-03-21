from fastapi import APIRouter
from backend.database import get_db_conn

router = APIRouter(prefix="/api/trades", tags=["trades"])

@router.get("")
def get_trades(limit: int = 50):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, market, symbol, action, confidence, price, quantity, executed_at FROM trades ORDER BY executed_at DESC LIMIT %s",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r["id"], "market": r["market"], "symbol": r["symbol"], "action": r["action"],
         "confidence": r["confidence"], "price": float(r["price"] or 0), "quantity": float(r["quantity"] or 0),
         "executed_at": r["executed_at"].isoformat() if r["executed_at"] else None}
        for r in rows
    ]
