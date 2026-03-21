from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import get_db_conn

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

class WatchlistItem(BaseModel):
    market: str  # "stock" or "coin"
    symbol: str
    name: str = ""

@router.get("")
def get_watchlist():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, market, symbol, name, active FROM watchlist ORDER BY market, symbol")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "market": r[1], "symbol": r[2], "name": r[3], "active": r[4]} for r in rows]

@router.post("")
def add_watchlist(item: WatchlistItem):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO watchlist (market, symbol, name) VALUES (%s, %s, %s) ON CONFLICT (market, symbol) DO UPDATE SET active = TRUE",
            (item.market, item.symbol, item.name)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
    return {"status": "ok"}

@router.delete("/{market}/{symbol}")
def remove_watchlist(market: str, symbol: str):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("UPDATE watchlist SET active = FALSE WHERE market = %s AND symbol = %s", (market, symbol))
    conn.commit()
    conn.close()
    return {"status": "ok"}
