# 트레일링 스탑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고정 익절%를 트레일링 스탑으로 대체 — 최고가 기준 -stop_loss% 하락 시 매도하여 강한 추세에서 수익을 극대화

**Architecture:** `positions` 테이블에 `highest_price` 컬럼 추가. 매 사이클 `_check_profit_stop()`에서 최고가 갱신 후 트레일링 조건 체크. 손절은 기존 entry_price 기준 그대로 유지.

**Tech Stack:** Python, psycopg3, pyupbit, PostgreSQL

---

## 파일 구조

| 파일 | 변경 내용 |
|------|----------|
| `backend/database.py` | `positions` 테이블에 `highest_price` 컬럼 추가 마이그레이션 |
| `backend/orchestrator.py` | `_check_profit_stop()` 트레일링 로직으로 교체 |
| `backend/execution/coin_executor.py` | `_save_position()` INSERT/UPDATE에 `highest_price` 추가 |
| `tests/test_trailing_stop.py` | 트레일링 스탑 단위 테스트 (신규 생성) |

---

## Task 1: DB 마이그레이션 — `highest_price` 컬럼 추가

**Files:**
- Modify: `backend/database.py`

- [ ] **Step 1: `create_tables()`의 positions 테이블 생성 쿼리에 `highest_price` 컬럼 추가**

`backend/database.py`의 positions 테이블 CREATE 쿼리를 아래처럼 수정:

```python
cur.execute("""
    CREATE TABLE IF NOT EXISTS positions (
        id SERIAL PRIMARY KEY,
        market VARCHAR(10) NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        entry_price DECIMAL(20, 8),
        quantity DECIMAL(20, 8),
        highest_price DECIMAL(20, 8) DEFAULT 0,
        opened_at TIMESTAMP DEFAULT NOW()
    );
    ALTER TABLE positions ADD COLUMN IF NOT EXISTS highest_price DECIMAL(20, 8) DEFAULT 0;
    UPDATE positions SET highest_price = entry_price WHERE highest_price = 0 OR highest_price IS NULL;
""")
```

`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`는 기존 EC2 DB의 positions 테이블에 컬럼을 추가하고, `UPDATE`는 운영 중인 포지션 6개의 `highest_price`를 `entry_price`로 초기화한다.

- [ ] **Step 2: 로컬에서 마이그레이션 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -c "from backend.database import create_tables; create_tables()"
```

Expected: `✅ 테이블 생성 및 기본 데이터 삽입 완료` 출력, 오류 없음

- [ ] **Step 3: 컬럼 추가 확인**

로컬 psql 또는 Python으로 확인:

```bash
python -c "
from backend.database import get_db
with get_db() as conn:
    cur = conn.cursor()
    cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='positions'\")
    print([r['column_name'] for r in cur.fetchall()])
"
```

Expected: `highest_price` 포함된 컬럼 목록 출력

- [ ] **Step 4: 커밋**

```bash
git add backend/database.py
git commit -m "feat: positions 테이블에 highest_price 컬럼 추가 (트레일링 스탑 준비)"
```

---

## Task 2: 테스트 작성 — 트레일링 스탑 로직

**Files:**
- Create: `tests/test_trailing_stop.py`

- [ ] **Step 1: 테스트 파일 생성**

`tests/test_trailing_stop.py`:

```python
"""트레일링 스탑 로직 단위 테스트"""
from unittest.mock import MagicMock, patch


def make_orchestrator():
    """Orchestrator 인스턴스를 실제 의존성 없이 생성"""
    with patch("backend.orchestrator.get_settings") as mock_settings, \
         patch("backend.orchestrator.CoinExecutor"), \
         patch("backend.orchestrator.AsyncIOScheduler"):
        settings = MagicMock()
        settings.rsi_buy_threshold = 35.0
        settings.rsi_sell_threshold = 55.0
        settings.take_profit_percent = 10.0
        settings.stop_loss_percent = 5.0
        settings.cooldown_minutes = 5
        mock_settings.return_value = settings
        from backend.orchestrator import Orchestrator
        return Orchestrator()


class TestCheckProfitStop:
    """_check_profit_stop 트레일링 스탑 테스트"""

    def setup_method(self):
        self.orc = make_orchestrator()

    def _mock_db_row(self, entry_price, highest_price):
        """DB에서 조회된 포지션 row를 흉내내는 mock"""
        return {"entry_price": entry_price, "highest_price": highest_price}

    # 케이스 1: 손절 조건 — 현재가가 entry_price 기준 -stop_loss% 이하
    def test_stop_loss_triggers(self):
        symbol = "KRW-DOGE"  # stop_loss=5%
        entry_price = 100.0
        highest_price = 102.0
        current_price = 94.0  # -6% (손절 -5% 초과)

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=current_price):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = self._mock_db_row(entry_price, highest_price)
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result == "SELL"

    # 케이스 2: 트레일링 활성화 + 발동 — 최고가 대비 -stop_loss% 하락
    def test_trailing_stop_triggers_when_activated(self):
        symbol = "KRW-DOGE"  # stop_loss=5%
        entry_price = 100.0
        highest_price = 110.0  # 활성화 조건: 100 * (1 + 5/200) = 102.5 → 110 >= 102.5 ✓
        current_price = 104.0  # 110 * (1 - 5/100) = 104.5 → 104 <= 104.5 ✓ 발동

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=current_price):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = self._mock_db_row(entry_price, highest_price)
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result == "SELL"

    # 케이스 3: 트레일링 미활성화 — 최고가가 활성화 임계값 미달
    def test_trailing_not_triggered_before_activation(self):
        symbol = "KRW-DOGE"  # stop_loss=5%, 활성화 임계: +2.5%
        entry_price = 100.0
        highest_price = 101.0  # 101 < 102.5 → 활성화 미충족
        current_price = 99.0   # 손절선(-5%): 95 → 99 > 95 → 손절도 미발동

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=current_price):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = self._mock_db_row(entry_price, highest_price)
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result is None

    # 케이스 4: 포지션 없음 → None 반환
    def test_no_position_returns_none(self):
        symbol = "KRW-SOL"

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=50000.0):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = None
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result is None

    # 케이스 5: LINK 코인별 오버라이드 — stop_loss=10%, 활성화 임계 +5%
    # 주의: Orchestrator._PROFIT_STOP_OVERRIDES는 클래스 변수로 "KRW-LINK": (15, 10) 정의됨
    # mock_settings의 stop_loss_percent=5.0 대신 오버라이드 값(10%) 이 사용되는지 검증
    def test_link_override_trailing_activation(self):
        symbol = "KRW-LINK"  # _PROFIT_STOP_OVERRIDES에서 stop_loss=10%, 활성화: entry * 1.05
        entry_price = 20000.0
        highest_price = 22000.0  # 22000 >= 21000 (20000*1.05) → 활성화 ✓
        current_price = 19700.0  # 22000 * 0.9 = 19800 → 19700 <= 19800 ✓ 발동

        with patch("backend.orchestrator.get_db") as mock_get_db, \
             patch("pyupbit.get_current_price", return_value=current_price):
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = self._mock_db_row(entry_price, highest_price)
            mock_conn.cursor.return_value = mock_cur
            mock_get_db.return_value = mock_conn

            result = self.orc._check_profit_stop(symbol)

        assert result == "SELL"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인 (구현 전이므로 FAIL 예상)**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m pytest tests/test_trailing_stop.py -v
```

Expected: `ImportError` 또는 `AttributeError` — `_check_profit_stop`이 아직 트레일링 로직 없음

- [ ] **Step 3: 커밋 (테스트 파일만)**

```bash
git add tests/test_trailing_stop.py
git commit -m "test: 트레일링 스탑 단위 테스트 추가 (구현 전 RED 상태)"
```

---

## Task 3: 트레일링 스탑 구현 — `orchestrator.py`

**Files:**
- Modify: `backend/orchestrator.py:126-153`

- [ ] **Step 1: `_check_profit_stop()` 전체 교체**

`backend/orchestrator.py`의 `_check_profit_stop()` 메서드를 아래로 교체:

```python
def _check_profit_stop(self, symbol: str) -> str | None:
    """트레일링 스탑 + 손절 체크.
    - 손절: entry_price 기준 -stop_loss% 이하 → SELL
    - 트레일링: highest_price 기준 -stop_loss% 하락 (활성화 조건 충족 시) → SELL
    """
    try:
        import pyupbit
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT entry_price, highest_price FROM positions WHERE market = 'coin' AND symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
        if not row:
            return None

        entry_price = float(row["entry_price"])
        highest_price = float(row["highest_price"] or entry_price)
        current_price = pyupbit.get_current_price(symbol)
        if not current_price:
            return None

        _, stop_loss = self._PROFIT_STOP_OVERRIDES.get(
            symbol,
            (self.settings.take_profit_percent, self.settings.stop_loss_percent)
        )

        # 1. 손절: entry_price 기준
        change_pct = (current_price - entry_price) / entry_price * 100
        if change_pct <= -stop_loss:
            logger.info(f"손절 [{symbol}]: {change_pct:.1f}% (기준: -{stop_loss}%)")
            return "SELL"

        # 2. highest_price 갱신 (예외 발생 시 트레일링 스킵)
        trailing_active = False
        try:
            if current_price > highest_price:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE positions SET highest_price = %s WHERE market = 'coin' AND symbol = %s",
                        (current_price, symbol)
                    )
                    conn.commit()
                highest_price = current_price
            trailing_active = True
        except Exception as e:
            logger.warning(f"highest_price 갱신 실패 [{symbol}] — 트레일링 스킵: {e}")
            return None

        if not trailing_active:
            return None

        # 3. 트레일링 스탑: 활성화 조건 충족 시에만
        activation_threshold = entry_price * (1 + stop_loss / 200)
        if highest_price >= activation_threshold:
            trailing_trigger = highest_price * (1 - stop_loss / 100)
            if current_price <= trailing_trigger:
                trail_pct = (highest_price - current_price) / highest_price * 100
                logger.info(
                    f"트레일링 스탑 [{symbol}]: 최고가 {highest_price:.0f}원 → 현재가 {current_price:.0f}원 "
                    f"(-{trail_pct:.1f}%, 기준: -{stop_loss}%)"
                )
                return "SELL"

    except Exception as e:
        logger.error(f"트레일링/손절 체크 오류: {e}")
    return None
```

- [ ] **Step 2: 트레일링 스탑 발동 시 텔레그램 알림 구분**

`analyze_and_trade()` 메서드에서 익절/손절 발동 알림 부분(약 162~167번 줄)을 아래로 교체:

```python
# 1. 트레일링/손절 먼저 체크
if market == "coin":
    forced_action = self._check_profit_stop(symbol)
    if forced_action:
        # 매도 전 highest_price 조회 (알림용)
        highest_price_for_alert = 0.0
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT highest_price FROM positions WHERE market = 'coin' AND symbol = %s",
                    (symbol,)
                )
                row = cur.fetchone()
                if row:
                    highest_price_for_alert = float(row["highest_price"] or 0)
        except Exception:
            pass

        result = self.coin_executor.sell(symbol, 100.0)
        if result:
            update_cooldown(symbol, "SELL")
            entry_price = result.get("entry_price", 0)
            price = result.get("price", 0)
            pnl_pct = result.get("pnl_pct", 0)
            pnl_krw = result.get("pnl_krw", 0)

            if pnl_pct >= 0:
                # 트레일링 스탑 (수익 실현)
                trail_drop = (highest_price_for_alert - price) / highest_price_for_alert * 100 if highest_price_for_alert > 0 else 0
                await send_message(
                    f"📉 트레일링 스탑 [{name or symbol}]\n"
                    f"최고가: {highest_price_for_alert:,.0f}원 → 현재가: {price:,.0f}원 (-{trail_drop:.1f}%)\n"
                    f"진입가: {entry_price:,.0f}원 | 손익: {pnl_pct:+.2f}% ({pnl_krw:+,.0f}원)"
                )
            else:
                # 손절
                await send_message(
                    f"🛑 손절 [{name or symbol}]\n"
                    f"진입가: {entry_price:,.0f}원 → 체결가: {price:,.0f}원\n"
                    f"손익: {pnl_pct:+.2f}% ({pnl_krw:+,.0f}원)"
                )
        return
```

- [ ] **Step 3: 테스트 실행 — 통과 확인**

```bash
python -m pytest tests/test_trailing_stop.py -v
```

Expected: 5개 테스트 모두 PASS

- [ ] **Step 4: 커밋**

```bash
git add backend/orchestrator.py
git commit -m "feat: 고정 익절 제거 → 트레일링 스탑으로 교체 (최고가 기준 -stop_loss% 발동)"
```

---

## Task 4: `coin_executor.py` — `_save_position()` highest_price 초기화

**Files:**
- Modify: `backend/execution/coin_executor.py:159-184`

- [ ] **Step 1: INSERT 쿼리에 `highest_price` 추가**

`_save_position()` 메서드의 INSERT 구문을 아래로 수정:

```python
def _save_position(self, symbol: str, price: float, quantity: float):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT entry_price, quantity FROM positions WHERE market = 'coin' AND symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
            if row:
                old_price = float(row["entry_price"])
                old_qty = float(row["quantity"])
                new_qty = old_qty + quantity
                new_avg = (old_price * old_qty + price * quantity) / new_qty
                cur.execute(
                    "UPDATE positions SET entry_price = %s, quantity = %s WHERE market = 'coin' AND symbol = %s",
                    (new_avg, new_qty, symbol)
                )
                # highest_price는 변경하지 않음 (추가매수 시 기존 최고가 유지)
                logger.info(f"포지션 추가매수 [{symbol}]: 평균단가 {new_avg:.0f}원, 수량 {new_qty:.6f}")
            else:
                cur.execute(
                    "INSERT INTO positions (market, symbol, entry_price, quantity, highest_price) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    ("coin", symbol, price, quantity, price)  # highest_price = entry_price
                )
            conn.commit()
    except Exception as e:
        logger.error(f"포지션 저장 실패: {e}")
```

- [ ] **Step 2: 전체 테스트 실행**

```bash
python -m pytest tests/test_trailing_stop.py -v
```

Expected: 5개 PASS

- [ ] **Step 3: 커밋**

```bash
git add backend/execution/coin_executor.py
git commit -m "feat: 신규 매수 시 highest_price를 entry_price로 초기화"
```

---

## Task 5: EC2 배포

- [ ] **Step 1: rsync로 코드 전송**

```bash
rsync -av --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='.env' --exclude='backtesting/data' \
  /Users/seodongjin/Documents/GitHub/coin_bot/ ubuntu@43.203.205.237:/home/ubuntu/coin_bot/ \
  -e "ssh -i ~/Desktop/coin-bot-key.pem"
```

- [ ] **Step 2: 서비스 재시작**

```bash
ssh -i ~/Desktop/coin-bot-key.pem ubuntu@43.203.205.237 "sudo systemctl restart coinbot"
```

- [ ] **Step 3: 로그 확인 (30초 관찰)**

```bash
ssh -i ~/Desktop/coin-bot-key.pem ubuntu@43.203.205.237 "sudo journalctl -u coinbot -n 30 --no-pager"
```

Expected: 오류 없이 `✅ 오케스트레이터 시작`, 코인 사이클 정상 동작

- [ ] **Step 4: EC2 DB highest_price 초기화 확인**

```bash
ssh -i ~/Desktop/coin-bot-key.pem ubuntu@43.203.205.237 \
  "psql postgresql://coinbot:1234@localhost:5432/coinbot -c 'SELECT symbol, entry_price, highest_price FROM positions;'"
```

Expected: 기존 포지션 6개 모두 `highest_price = entry_price` (0 아님)

- [ ] **Step 5: PROGRESS.md 업데이트 후 최종 커밋**

`PROGRESS.md` 상단에 오늘 작업 내용 추가:

```markdown
## 2026-04-05: 트레일링 스탑 도입 (고정 익절 제거)

### 변경 내용 (`orchestrator.py`, `coin_executor.py`, `database.py`)
- 기존 고정 익절(+5~25%) 제거 → 트레일링 스탑으로 대체
- positions 테이블에 `highest_price` 컬럼 추가
- 트레일링 로직:
  - 손절: entry_price 기준 -stop_loss% (기존 유지)
  - 트레일링 활성화: highest_price >= entry_price × (1 + stop_loss/200)
  - 트레일링 발동: current_price <= highest_price × (1 - stop_loss/100)
- 트레일링/손절 텔레그램 알림 구분 (📈 트레일링 스탑 / 🛑 손절)
- 기존 운영 포지션 6개 highest_price → entry_price로 자동 초기화
```

```bash
git add PROGRESS.md
git commit -m "docs: PROGRESS.md 트레일링 스탑 도입 내용 추가"
```
