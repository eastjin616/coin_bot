from fastapi import APIRouter
from backend.database import get_db_conn

router = APIRouter(prefix="/api/signals", tags=["signals"])

@router.get("")
def get_signals(market: str = None):
    conn = get_db_conn()
    cur = conn.cursor()
    if market:
        cur.execute(
            "SELECT id, market, symbol, action, confidence, executed_at FROM trades WHERE market = %s ORDER BY executed_at DESC LIMIT 20",
            (market,)
        )
    else:
        cur.execute(
            "SELECT id, market, symbol, action, confidence, executed_at FROM trades ORDER BY executed_at DESC LIMIT 20"
        )
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "market": r[1], "symbol": r[2], "action": r[3],
         "confidence": r[4], "executed_at": r[5].isoformat() if r[5] else None}
        for r in rows
    ]
