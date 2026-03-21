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
        {"id": r[0], "market": r[1], "symbol": r[2], "action": r[3],
         "confidence": r[4], "price": float(r[5] or 0), "quantity": float(r[6] or 0),
         "executed_at": r[7].isoformat() if r[7] else None}
        for r in rows
    ]
