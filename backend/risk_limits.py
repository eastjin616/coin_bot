"""운영 리스크 캡 조회 (포지션 수, KST 기준 일일 매수 횟수)."""

import logging
from datetime import datetime

import pytz

from backend.database import get_db

logger = logging.getLogger(__name__)


def count_open_coin_positions() -> int:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM positions WHERE market = 'coin'")
            return int(cur.fetchone()["c"])
    except Exception as e:
        logger.error(f"포지션 수 조회 실패: {e}")
        return 0


def count_coin_buys_kst_today() -> int:
    """오늘 00:00 KST 이후 `trades` 기준 매수 건수."""
    try:
        kst = pytz.timezone("Asia/Seoul")
        start_kst = datetime.now(kst).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_kst.astimezone(pytz.UTC)
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM trades
                WHERE market = 'coin' AND action = 'BUY' AND executed_at >= %s
                """,
                (start_utc,),
            )
            return int(cur.fetchone()["c"])
    except Exception as e:
        logger.error(f"일일 매수 횟수 조회 실패: {e}")
        return 0
