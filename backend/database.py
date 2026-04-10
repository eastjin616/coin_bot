import psycopg
from contextlib import contextmanager

from backend.config import get_settings


def get_db_conn():
    """PostgreSQL 연결 객체를 반환합니다."""
    settings = get_settings()
    conn = psycopg.connect(settings.database_url, row_factory=psycopg.rows.dict_row)
    return conn


@contextmanager
def get_db():
    """DB 연결 컨텍스트 매니저 — 예외 발생 시에도 반드시 연결 해제."""
    conn = get_db_conn()
    try:
        yield conn
    finally:
        conn.close()


def create_tables() -> None:
    """필요한 테이블을 생성합니다 (존재하지 않을 경우에만)."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # 매매 내역
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    market VARCHAR(10) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    action VARCHAR(4) NOT NULL,
                    order_uuid VARCHAR(100),
                    confidence FLOAT NOT NULL,
                    price DECIMAL(20, 8),
                    quantity DECIMAL(20, 8),
                    pnl_krw DECIMAL(20, 2) DEFAULT 0,
                    pnl_pct DECIMAL(10, 4) DEFAULT 0,
                    executed_at TIMESTAMP DEFAULT NOW()
                );
                ALTER TABLE trades ADD COLUMN IF NOT EXISTS order_uuid VARCHAR(100);
                ALTER TABLE trades ADD COLUMN IF NOT EXISTS pnl_krw DECIMAL(20, 2) DEFAULT 0;
                ALTER TABLE trades ADD COLUMN IF NOT EXISTS pnl_pct DECIMAL(10, 4) DEFAULT 0;
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_order_uuid
                ON trades(order_uuid);
            """)

            # 주문 실행 저널 (거래소 체결 ↔ 로컬 DB 반영 사이 복구용)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS order_journal (
                    order_uuid VARCHAR(100) PRIMARY KEY,
                    market VARCHAR(10) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    action VARCHAR(4) NOT NULL,
                    requested_amount_krw DECIMAL(20, 2),
                    requested_quantity DECIMAL(20, 8),
                    entry_price_snapshot DECIMAL(20, 8),
                    order_created_at TIMESTAMP,
                    status VARCHAR(20) NOT NULL DEFAULT 'submitted',
                    last_error TEXT,
                    reconciled_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS requested_amount_krw DECIMAL(20, 2);
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS requested_quantity DECIMAL(20, 8);
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS entry_price_snapshot DECIMAL(20, 8);
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS order_created_at TIMESTAMP;
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'submitted';
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS last_error TEXT;
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS reconciled_at TIMESTAMP;
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
                ALTER TABLE order_journal ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();
            """)

            # 수동 보유 종목 추적 (거래소 실보유 but DB 포지션 미편입)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS manual_holdings (
                    symbol VARCHAR(20) PRIMARY KEY,
                    quantity DECIMAL(20, 8) NOT NULL,
                    avg_buy_price DECIMAL(20, 8) DEFAULT 0,
                    status VARCHAR(20) NOT NULL DEFAULT 'alert_only',
                    note TEXT,
                    first_detected_at TIMESTAMP DEFAULT NOW(),
                    last_seen_at TIMESTAMP DEFAULT NOW(),
                    last_alerted_at TIMESTAMP
                );
                ALTER TABLE manual_holdings ADD COLUMN IF NOT EXISTS quantity DECIMAL(20, 8) NOT NULL DEFAULT 0;
                ALTER TABLE manual_holdings ADD COLUMN IF NOT EXISTS avg_buy_price DECIMAL(20, 8) DEFAULT 0;
                ALTER TABLE manual_holdings ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'alert_only';
                ALTER TABLE manual_holdings ADD COLUMN IF NOT EXISTS note TEXT;
                ALTER TABLE manual_holdings ADD COLUMN IF NOT EXISTS first_detected_at TIMESTAMP DEFAULT NOW();
                ALTER TABLE manual_holdings ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP DEFAULT NOW();
                ALTER TABLE manual_holdings ADD COLUMN IF NOT EXISTS last_alerted_at TIMESTAMP;
            """)

            # 감시 종목
            cur.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id SERIAL PRIMARY KEY,
                    market VARCHAR(10) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    name VARCHAR(50),
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(market, symbol)
                );
            """)

            # 쿨다운 상태
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cooldowns (
                    symbol VARCHAR(20) NOT NULL,
                    action VARCHAR(4) NOT NULL,
                    last_executed_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (symbol, action)
                );
            """)

            # 현재 포지션
            cur.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id SERIAL PRIMARY KEY,
                    market VARCHAR(10) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    entry_price DECIMAL(20, 8),
                    quantity DECIMAL(20, 8),
                    highest_price DECIMAL(20, 8) DEFAULT 0,
                    source VARCHAR(20) NOT NULL DEFAULT 'bot',
                    imported_at TIMESTAMP,
                    opened_at TIMESTAMP DEFAULT NOW()
                );
                ALTER TABLE positions ADD COLUMN IF NOT EXISTS highest_price DECIMAL(20, 8) DEFAULT 0;
                ALTER TABLE positions ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'bot';
                ALTER TABLE positions ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP;
                UPDATE positions SET highest_price = entry_price WHERE highest_price = 0 OR highest_price IS NULL;
            """)
            cur.execute("""
                WITH dupes AS (
                    SELECT
                        market,
                        symbol,
                        MIN(ctid) AS keep_ctid,
                        SUM(COALESCE(quantity, 0)) AS total_quantity,
                        CASE
                            WHEN SUM(COALESCE(quantity, 0)) = 0 THEN MAX(COALESCE(entry_price, 0))
                            ELSE SUM(COALESCE(entry_price, 0) * COALESCE(quantity, 0)) / SUM(COALESCE(quantity, 0))
                        END AS merged_entry_price,
                        GREATEST(
                            MAX(COALESCE(highest_price, 0)),
                            MAX(COALESCE(entry_price, 0))
                        ) AS merged_highest_price,
                        CASE
                            WHEN BOOL_OR(source = 'manual_import') THEN 'manual_import'
                            ELSE 'bot'
                        END AS merged_source,
                        MIN(imported_at) FILTER (WHERE imported_at IS NOT NULL) AS first_imported_at,
                        MIN(opened_at) AS first_opened_at
                    FROM positions
                    GROUP BY market, symbol
                    HAVING COUNT(*) > 1
                )
                UPDATE positions AS p
                SET
                    entry_price = d.merged_entry_price,
                    quantity = d.total_quantity,
                    highest_price = d.merged_highest_price,
                    source = d.merged_source,
                    imported_at = d.first_imported_at,
                    opened_at = d.first_opened_at
                FROM dupes AS d
                WHERE p.ctid = d.keep_ctid;
            """)
            cur.execute("""
                WITH dupes AS (
                    SELECT market, symbol, MIN(ctid) AS keep_ctid
                    FROM positions
                    GROUP BY market, symbol
                    HAVING COUNT(*) > 1
                )
                DELETE FROM positions AS p
                USING dupes AS d
                WHERE p.market = d.market
                  AND p.symbol = d.symbol
                  AND p.ctid <> d.keep_ctid;
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_positions_market_symbol
                ON positions(market, symbol);
            """)

            # 일봉 신호 중복 실행 방지
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signal_locks (
                    market VARCHAR(10) NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    action VARCHAR(4) NOT NULL,
                    candle_time TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (market, symbol, action)
                );
            """)

            # 기본 감시 종목 삽입 (이미 존재하면 무시)
            cur.execute("""
                INSERT INTO watchlist (market, symbol, name)
                VALUES
                    ('coin', 'KRW-BTC', '비트코인')
                ON CONFLICT (market, symbol) DO NOTHING;
            """)

            conn.commit()
            print("✅ 테이블 생성 및 기본 데이터 삽입 완료")
    except Exception as e:
        conn.rollback()
        print(f"❌ 테이블 생성 실패: {e}")
        raise
    finally:
        conn.close()
