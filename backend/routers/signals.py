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
        {"id": r["id"], "market": r["market"], "symbol": r["symbol"], "action": r["action"],
         "confidence": r["confidence"], "executed_at": r["executed_at"].isoformat() if r["executed_at"] else None}
        for r in rows
    ]
