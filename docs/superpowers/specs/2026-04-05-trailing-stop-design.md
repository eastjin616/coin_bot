# 트레일링 스탑 설계 스펙

**날짜:** 2026-04-05  
**상태:** 승인됨

---

## 목표

기존 고정 익절(%) `_PROFIT_STOP_OVERRIDES`의 `take_profit`을 트레일링 스탑으로 대체.  
추세가 강할 때 수익을 더 끌고 가고, 반전 시 자동 매도.  
손절 로직은 기존 그대로 유지.

---

## 설계

### 1. DB 변경 — `positions` 테이블

`highest_price` 컬럼 추가 후 기존 포지션 초기화:

```sql
ALTER TABLE positions ADD COLUMN IF NOT EXISTS highest_price NUMERIC DEFAULT 0;
-- 기존 포지션 6개: entry_price로 초기화 (0 그대로 두면 첫 사이클 로그 오염)
UPDATE positions SET highest_price = entry_price WHERE highest_price = 0;
```

- 신규 매수 시 초기값: `entry_price`
- 매 사이클마다 `current_price > highest_price`이면 갱신

---

### 2. 트레일링 스탑 로직 (`orchestrator.py`)

#### `_check_profit_stop()` 실행 순서

```
1. entry_price, highest_price 조회 (DB)
2. current_price 조회 (업비트)
3. 손절 체크: (current_price - entry_price) / entry_price <= -stop_loss/100 → SELL
4. highest_price 갱신: current_price > highest_price → UPDATE DB
   - DB 갱신 실패 시 (예외 발생 시에만 실패로 간주, rows affected=0은 정상): 해당 사이클 트레일링 체크 스킵 (손절만 유지)
5. 트레일링 활성화 조건: highest_price >= entry_price * (1 + stop_loss / 200)
6. 트레일링 발동: current_price <= highest_price * (1 - stop_loss / 100) → SELL
```

#### 활성화 전 공백 구간 (의도된 동작)

트레일링 활성화 조건 미충족 구간(최고가가 최소수익에 미달)에서는 손절만 작동.  
예: BTC 활성화 미충족(+1.5% 미만) 상태에서 -3% 손절선 도달 → 손절 발동.  
이는 의도된 동작으로, 수익 미진입 구간에서의 조기 매도를 방지하기 위함.

#### 트레일링 % 값

기존 `_PROFIT_STOP_OVERRIDES`의 `stop_loss` 값 재활용:

| 코인 | stop_loss% | 트레일링% | 활성화 최소수익 (`stop_loss/2`) |
|------|-----------|----------|-----------------------------|
| BTC  | 3% | -3% | +1.5% |
| SOL  | 3% | -3% | +1.5% |
| DOGE | 5% | -5% | +2.5% |
| DOT  | 3% | -3% | +1.5% |
| ADA  | 3% | -3% | +1.5% |
| AVAX | 5% | -5% | +2.5% |
| LINK | 10% | -10% | +5.0% |
| TRX  | 10% | -10% | +5.0% |
| SUI  | 5% | -5% | +2.5% |
| HBAR | 5% | -5% | +2.5% |
| ICP  | 3% | -3% | +1.5% |
| ATOM | 5% | -5% | +2.5% |
| UNI  | 3% | -3% | +1.5% |
| SHIB | 5% | -5% | +2.5% |
| BCH  | 3% | -3% | +1.5% |

활성화 공식: `entry_price * (1 + stop_loss / 200)`  
트레일링 발동 공식: `highest_price * (1 - stop_loss / 100)`

---

### 3. `coin_executor.py` — `_save_position()` 변경

#### INSERT (신규 매수)
```sql
INSERT INTO positions (market, symbol, entry_price, quantity, highest_price)
VALUES (%s, %s, %s, %s, %s)
-- highest_price = entry_price (체결가로 초기화)
```

#### UPDATE (추가매수, 현재 DCA 범위 외 — 향후 확장 대비)
추가매수 시 `highest_price`는 변경하지 않음. 이미 트레일링이 활성화된 상태라면 기존 최고가 그대로 유지 (평균단가 변경이 트레일링 추적을 방해하지 않도록).

---

### 4. 텔레그램 알림

#### 트레일링 스탑 발동 시
```
📉 트레일링 스탑 [LINK]
최고가: 25,000원 → 현재가: 22,500원 (-10.0%)
진입가: 20,000원 | 손익: +12.5% (+X,XXX원)
```
- 손익 금액: `(현재가 - 진입가) × 수량` (수량은 positions 테이블의 quantity 사용)

#### 손절 발동 시 (기존 알림 그대로)
```
🛑 손절 [BTC]
진입가: 90,000,000원 → 현재가: 87,300,000원 (-3.0%)
```

---

## 변경 파일 목록

1. `backend/database.py` — `highest_price` 컬럼 마이그레이션 + 기존 포지션 초기화
2. `backend/orchestrator.py` — `_check_profit_stop()` 트레일링 로직 (고정 익절 제거)
3. `backend/execution/coin_executor.py` — `_save_position()` highest_price 초기화

---

## 제외 범위

- DCA 분할매수: 별도 스펙으로 분리
- RSI 다이버전스: 백테스팅 검증 후 진행
