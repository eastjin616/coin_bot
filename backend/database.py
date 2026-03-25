import psycopg

from backend.config import get_settings


def get_db_conn():
    """PostgreSQL 연결 객체를 반환합니다."""
    settings = get_settings()
    conn = psycopg.connect(settings.database_url, row_factory=psycopg.rows.dict_row)
    return conn


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
                    confidence FLOAT NOT NULL,
                    price DECIMAL(20, 8),
                    quantity DECIMAL(20, 8),
                    executed_at TIMESTAMP DEFAULT NOW()
                );
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
                    opened_at TIMESTAMP DEFAULT NOW()
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
