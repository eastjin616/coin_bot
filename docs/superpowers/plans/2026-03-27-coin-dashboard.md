# coin_bot AI 투자 대시보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 coin_bot FastAPI에 LangChain RAG Agent 기반 AI 채팅과 Next.js 반응형 대시보드를 추가한다.

**Architecture:** Next.js(Vercel) → Next.js API Route(서버사이드) → FastAPI EC2. 클라이언트는 EC2에 직접 호출하지 않고 Next.js API Route를 경유해 X-API-Key 헤더를 안전하게 붙임. FastAPI에 LangChain Agent가 추가되어 DB/업비트 API를 툴로 호출하며 Groq LLM으로 자연어 답변 생성.

**Tech Stack:** FastAPI + LangChain 0.3.x + langchain-groq 0.2.x + Next.js 14 (App Router) + Tailwind CSS + pyupbit + psycopg3

---

## 파일 구조

### 백엔드 (신규/수정)
- **수정** `backend/config.py` — `dashboard_api_key`, `vercel_origin` 설정 추가
- **수정** `backend/main.py` — CORS 도메인 제한, 새 라우터 등록
- **신규** `backend/middleware/api_key_auth.py` — X-API-Key 검증 미들웨어
- **신규** `backend/routers/portfolio.py` — `GET /api/portfolio` 엔드포인트
- **신규** `backend/routers/chat.py` — `POST /chat` 엔드포인트
- **신규** `backend/ai/agent_tools.py` — LangChain 툴 3개 (get_portfolio, get_trade_history, get_market_signal)
- **신규** `backend/ai/chat_agent.py` — LangChain Agent 래퍼

### 백엔드 테스트
- **신규** `tests/test_api_key_auth.py`
- **신규** `tests/test_portfolio_router.py`
- **신규** `tests/test_agent_tools.py`
- **신규** `tests/test_chat_router.py`

### 프론트엔드 (신규 프로젝트)
- `dashboard/` — Next.js 14 프로젝트 루트
- `dashboard/app/layout.tsx` — 루트 레이아웃 (네비게이션 포함)
- `dashboard/app/page.tsx` — 메인 대시보드 (포트폴리오 + 최근 매매)
- `dashboard/app/chat/page.tsx` — AI 채팅 페이지
- `dashboard/app/history/page.tsx` — 매매 히스토리 페이지
- `dashboard/app/api/portfolio/route.ts` — 포트폴리오 프록시 API Route
- `dashboard/app/api/chat/route.ts` — 채팅 프록시 API Route
- `dashboard/app/api/trades/route.ts` — 매매내역 프록시 API Route
- `dashboard/components/CoinCard.tsx` — 코인 보유 카드 컴포넌트
- `dashboard/components/ChatUI.tsx` — 채팅 UI 컴포넌트
- `dashboard/components/TradeTable.tsx` — 매매내역 테이블 컴포넌트
- `dashboard/components/BottomNav.tsx` — 모바일 하단 네비게이션

---

## Task 1: 백엔드 설정 & 인증 미들웨어

**Files:**
- Modify: `backend/config.py`
- Create: `backend/middleware/__init__.py`
- Create: `backend/middleware/api_key_auth.py`
- Test: `tests/test_api_key_auth.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_api_key_auth.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

def test_missing_api_key_returns_401():
    from backend.middleware.api_key_auth import APIKeyMiddleware
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="secret")

    @app.get("/test")
    def endpoint():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test")
    assert resp.status_code == 401

def test_wrong_api_key_returns_401():
    from backend.middleware.api_key_auth import APIKeyMiddleware
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="secret")

    @app.get("/test")
    def endpoint():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401

def test_correct_api_key_returns_200():
    from backend.middleware.api_key_auth import APIKeyMiddleware
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="secret")

    @app.get("/test")
    def endpoint():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/test", headers={"X-API-Key": "secret"})
    assert resp.status_code == 200

def test_health_check_skips_auth():
    """/ 경로는 인증 없이 통과해야 함"""
    from backend.middleware.api_key_auth import APIKeyMiddleware
    app = FastAPI()
    app.add_middleware(APIKeyMiddleware, api_key="secret")

    @app.get("/")
    def root():
        return {"status": "ok"}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/")
    assert resp.status_code == 200
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
python -m pytest tests/test_api_key_auth.py -v
```
Expected: `ModuleNotFoundError` 또는 `ImportError`

- [ ] **Step 3: config.py에 설정 추가**

```python
# backend/config.py 에 아래 두 줄을 Settings 클래스 내 기존 필드들 아래에 추가
dashboard_api_key: str = ""
vercel_origin: str = "https://localhost:3000"
```

- [ ] **Step 4: 미들웨어 구현**

```python
# backend/middleware/__init__.py
# (빈 파일)
```

```python
# backend/middleware/api_key_auth.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SKIP_PATHS = {"/", "/docs", "/openapi.json", "/redoc"}

class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS or not self.api_key:
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if key != self.api_key:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

```bash
python -m pytest tests/test_api_key_auth.py -v
```
Expected: 4개 모두 PASS

- [ ] **Step 6: main.py 업데이트**

`backend/main.py`에서:
1. `from backend.middleware.api_key_auth import APIKeyMiddleware` 추가
2. CORS `allow_origins=["*"]` → `allow_origins=[settings.vercel_origin]` 변경
3. `app.add_middleware(APIKeyMiddleware, api_key=settings.dashboard_api_key)` 추가

전체 main.py:
```python
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import get_settings
from backend.database import create_tables
from backend.orchestrator import Orchestrator
from backend.routers import trades, watchlist, signals, balance, test_trade
from backend.middleware.api_key_auth import APIKeyMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

orchestrator = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    create_tables()
    orchestrator = Orchestrator()
    orchestrator.start()

    from backend.telegram_bot import setup_bot
    settings = get_settings()
    if settings.telegram_bot_token:
        bot_app = setup_bot()
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling()
        logging.getLogger(__name__).info("✅ 텔레그램 봇 polling 시작")
    else:
        bot_app = None

    yield

    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
    if orchestrator:
        orchestrator.stop()

settings = get_settings()
app = FastAPI(title="coin_bot API", lifespan=lifespan)

app.add_middleware(APIKeyMiddleware, api_key=settings.dashboard_api_key)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.vercel_origin, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trades.router)
app.include_router(watchlist.router)
app.include_router(signals.router)
app.include_router(balance.router)
app.include_router(test_trade.router)

@app.get("/")
def root():
    return {"status": "coin_bot API 실행 중"}
```

- [ ] **Step 7: .env에 키 추가**

```bash
# .env 파일 끝에 추가 (실제 랜덤 값으로 교체)
echo "DASHBOARD_API_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
echo "VERCEL_ORIGIN=http://localhost:3000" >> .env
```

- [ ] **Step 8: 커밋**

```bash
git add backend/config.py backend/main.py backend/middleware/ tests/test_api_key_auth.py
git commit -m "feat: API Key 인증 미들웨어 추가 및 CORS 도메인 제한"
```

---

## Task 2: 포트폴리오 API 엔드포인트

**Files:**
- Create: `backend/routers/portfolio.py`
- Modify: `backend/main.py`
- Test: `tests/test_portfolio_router.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_portfolio_router.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    # settings 캐시 초기화 후 테스트용 설정 주입
    from backend.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"DASHBOARD_API_KEY": "", "VERCEL_ORIGIN": "http://localhost:3000"}):
        from backend.main import app
        return TestClient(app)

def test_portfolio_returns_structure(client):
    with patch("backend.routers.portfolio.CoinExecutor") as MockExec:
        mock = MockExec.return_value
        mock.get_balance_krw.return_value = 100000.0
        with patch("backend.routers.portfolio.pyupbit.get_balances") as mock_balances:
            mock_balances.return_value = []
            resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert "krw_balance" in data
    assert "holdings" in data
    assert "total_value" in data

def test_portfolio_calculates_total_value(client):
    with patch("backend.routers.portfolio.CoinExecutor") as MockExec:
        mock = MockExec.return_value
        mock.get_balance_krw.return_value = 50000.0
        with patch("backend.routers.portfolio.pyupbit.get_balances") as mock_balances:
            mock_balances.return_value = [
                {"currency": "BTC", "balance": "0.001", "avg_buy_price": "80000000"}
            ]
            with patch("backend.routers.portfolio.pyupbit.get_current_price") as mock_price:
                mock_price.return_value = {"KRW-BTC": 90000000}
                resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    # total_value = krw_balance(50000) + BTC평가(0.001 * 90000000 = 90000) = 140000
    assert data["total_value"] == pytest.approx(140000.0, rel=0.01)
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
python -m pytest tests/test_portfolio_router.py -v
```
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 포트폴리오 라우터 구현**

```python
# backend/routers/portfolio.py
import logging
import pyupbit
from fastapi import APIRouter
from backend.execution.coin_executor import CoinExecutor
from backend.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/api/portfolio")
def get_portfolio():
    """현재 보유 코인 + KRW 잔고 + 평가금액 반환"""
    settings = get_settings()
    executor = CoinExecutor()

    krw_balance = executor.get_balance_krw()
    holdings = []
    total_value = krw_balance

    try:
        balances = pyupbit.get_balances(settings.upbit_access_key, settings.upbit_secret_key) or []
    except Exception as e:
        logger.error(f"업비트 잔고 조회 실패: {e}")
        balances = []

    coin_symbols = [f"KRW-{b['currency']}" for b in balances if b.get("currency") != "KRW" and float(b.get("balance", 0)) > 0]

    if coin_symbols:
        try:
            prices = pyupbit.get_current_price(coin_symbols) or {}
        except Exception as e:
            logger.error(f"현재가 조회 실패: {e}")
            prices = {}
    else:
        prices = {}

    for b in balances:
        currency = b.get("currency", "")
        if currency == "KRW":
            continue
        quantity = float(b.get("balance", 0))
        if quantity <= 0:
            continue
        symbol = f"KRW-{currency}"
        avg_price = float(b.get("avg_buy_price", 0))
        current_price = float(prices.get(symbol, avg_price) or avg_price)
        eval_value = quantity * current_price
        profit_rate = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
        total_value += eval_value
        holdings.append({
            "symbol": symbol,
            "quantity": quantity,
            "avg_price": avg_price,
            "current_price": current_price,
            "eval_value": eval_value,
            "profit_rate": round(profit_rate, 2),
        })

    return {
        "krw_balance": krw_balance,
        "holdings": holdings,
        "total_value": round(total_value, 0),
    }
```

- [ ] **Step 4: main.py에 라우터 등록**

`backend/main.py`에 아래 두 줄 추가:
```python
from backend.routers import portfolio  # import 줄에 추가
app.include_router(portfolio.router)   # include_router 줄들 아래에 추가
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

```bash
python -m pytest tests/test_portfolio_router.py -v
```
Expected: 2개 PASS

- [ ] **Step 6: 커밋**

```bash
git add backend/routers/portfolio.py backend/main.py tests/test_portfolio_router.py
git commit -m "feat: GET /api/portfolio 엔드포인트 추가"
```

---

## Task 3: LangChain Agent 툴 3개

**Files:**
- Create: `backend/ai/agent_tools.py`
- Test: `tests/test_agent_tools.py`

의존성 먼저 설치:
```bash
pip install langchain==0.3.* langchain-groq==0.2.* langchain-core==0.3.*
pip freeze | grep langchain >> requirements.txt
```

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_agent_tools.py
import pytest
from unittest.mock import patch, MagicMock

def test_get_portfolio_tool_returns_string():
    from backend.ai.agent_tools import get_portfolio_tool
    with patch("backend.ai.agent_tools.CoinExecutor") as MockExec:
        mock = MockExec.return_value
        mock.get_balance_krw.return_value = 100000.0
        with patch("backend.ai.agent_tools.pyupbit.get_balances", return_value=[]):
            result = get_portfolio_tool("")
    assert isinstance(result, str)
    assert "100000" in result or "잔고" in result

def test_get_trade_history_tool_returns_string():
    from backend.ai.agent_tools import get_trade_history_tool
    with patch("backend.ai.agent_tools.get_db_conn") as mock_conn:
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.return_value.cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = get_trade_history_tool("7")
    assert isinstance(result, str)

def test_get_market_signal_tool_returns_string():
    from backend.ai.agent_tools import get_market_signal_tool
    with patch("backend.ai.agent_tools.pyupbit.get_current_price", return_value={"KRW-BTC": 90000000}):
        with patch("backend.ai.agent_tools.get_db_conn") as mock_conn:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = {"confidence": 72.5, "action": "BUY", "executed_at": "2026-03-27"}
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_conn.return_value.cursor.return_value.__exit__ = MagicMock(return_value=False)
            result = get_market_signal_tool("KRW-BTC")
    assert isinstance(result, str)
    assert "90000000" in result or "BTC" in result
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
python -m pytest tests/test_agent_tools.py -v
```
Expected: FAIL (모듈 없음)

- [ ] **Step 3: agent_tools.py 구현**

```python
# backend/ai/agent_tools.py
import logging
import pyupbit
from langchain_core.tools import tool
from backend.database import get_db_conn
from backend.execution.coin_executor import CoinExecutor
from backend.config import get_settings

logger = logging.getLogger(__name__)


@tool
def get_portfolio_tool(query: str) -> str:
    """현재 보유 코인과 KRW 잔고, 평가금액을 조회한다. 포트폴리오 관련 질문에 사용."""
    settings = get_settings()
    executor = CoinExecutor()
    krw = executor.get_balance_krw()

    try:
        balances = pyupbit.get_balances(settings.upbit_access_key, settings.upbit_secret_key) or []
    except Exception:
        balances = []

    coin_symbols = [f"KRW-{b['currency']}" for b in balances if b.get("currency") != "KRW" and float(b.get("balance", 0)) > 0]
    prices = {}
    if coin_symbols:
        try:
            prices = pyupbit.get_current_price(coin_symbols) or {}
        except Exception:
            pass

    lines = [f"KRW 잔고: {krw:,.0f}원"]
    total = krw
    for b in balances:
        currency = b.get("currency", "")
        if currency == "KRW":
            continue
        qty = float(b.get("balance", 0))
        if qty <= 0:
            continue
        symbol = f"KRW-{currency}"
        avg = float(b.get("avg_buy_price", 0))
        cur = float(prices.get(symbol, avg) or avg)
        val = qty * cur
        rate = ((cur - avg) / avg * 100) if avg > 0 else 0
        total += val
        lines.append(f"{symbol}: {qty:.6f}개, 평균단가 {avg:,.0f}원, 현재가 {cur:,.0f}원, 평가금액 {val:,.0f}원, 수익률 {rate:.1f}%")

    lines.append(f"총 평가금액: {total:,.0f}원")
    return "\n".join(lines)


@tool
def get_trade_history_tool(days: str) -> str:
    """최근 N일간의 매매 내역과 실현 수익을 조회한다. 수익/손실 관련 질문에 사용. days 파라미터는 숫자 문자열."""
    try:
        n = int(days)
    except ValueError:
        n = 7

    try:
        conn = get_db_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, action, price, quantity, confidence, executed_at
                FROM trades
                WHERE market = 'coin' AND executed_at >= NOW() - INTERVAL '%s days'
                ORDER BY executed_at DESC
            """, (n,))
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        return f"DB 조회 실패: {e}"

    if not rows:
        return f"최근 {n}일간 매매 내역이 없습니다."

    # BUY/SELL 페어 매칭으로 실현 수익 계산
    buys: dict[str, dict] = {}
    realized = []
    total_profit = 0.0
    for row in sorted(rows, key=lambda r: r["executed_at"]):
        sym = row["symbol"]
        if row["action"] == "BUY":
            buys[sym] = row
        elif row["action"] == "SELL" and sym in buys:
            buy = buys.pop(sym)
            profit = (float(row["price"]) - float(buy["price"])) * float(row["quantity"])
            total_profit += profit
            realized.append(f"{sym}: 매수 {float(buy['price']):,.0f}원 → 매도 {float(row['price']):,.0f}원, 수익 {profit:+,.0f}원")

    total_profit = sum(
        float(r.split("수익 ")[1].replace("원", "").replace(",", "").replace("+", ""))
        for r in realized
    ) if realized else 0

    lines = [f"최근 {n}일간 매매 내역 ({len(rows)}건):"]
    for row in rows[:10]:
        lines.append(f"  {row['executed_at'].strftime('%m/%d %H:%M')} {row['symbol']} {row['action']} @ {float(row['price']):,.0f}원 (AI확률: {row['confidence']:.0f}%)")

    if realized:
        lines.append(f"\n실현 수익 합계: {total_profit:+,.0f}원")
        lines.append("상세:")
        lines.extend(f"  {r}" for r in realized)

    return "\n".join(lines)


@tool
def get_market_signal_tool(coin: str) -> str:
    """특정 코인의 현재 가격과 가장 최근 AI 분석 신호를 조회한다. 매매 판단 질문에 사용. coin은 'KRW-BTC' 형식."""
    symbol = coin.upper()
    if not symbol.startswith("KRW-"):
        symbol = f"KRW-{symbol}"

    # 현재가
    try:
        price_data = pyupbit.get_current_price(symbol)
        current_price = float(price_data) if isinstance(price_data, (int, float)) else float(price_data.get(symbol, 0))
    except Exception:
        current_price = 0

    # DB에서 최근 AI 분석값 재사용
    try:
        conn = get_db_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT action, confidence, executed_at FROM trades
                WHERE symbol = %s AND market = 'coin'
                ORDER BY executed_at DESC LIMIT 1
            """, (symbol,))
            row = cur.fetchone()
        conn.close()
    except Exception:
        row = None

    lines = [f"{symbol} 현재가: {current_price:,.0f}원"]
    if row:
        lines.append(f"최근 AI 분석 ({row['executed_at'].strftime('%m/%d %H:%M')}): {row['action']} 신호, 확률 {row['confidence']:.0f}%")
        if row["confidence"] >= 70:
            lines.append("→ AI 판단: 매수 고려 구간")
        elif row["confidence"] <= 20:
            lines.append("→ AI 판단: 매도/관망 구간")
        else:
            lines.append("→ AI 판단: 중립, 관망 권장")
    else:
        lines.append("최근 AI 분석 기록 없음")

    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

```bash
python -m pytest tests/test_agent_tools.py -v
```
Expected: 3개 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/ai/agent_tools.py tests/test_agent_tools.py
git commit -m "feat: LangChain Agent 툴 3개 (portfolio, trade_history, market_signal)"
```

---

## Task 4: LangChain Agent + Chat 엔드포인트

**Files:**
- Create: `backend/ai/chat_agent.py`
- Create: `backend/routers/chat.py`
- Modify: `backend/main.py`
- Test: `tests/test_chat_router.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_chat_router.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

@pytest.fixture
def client():
    from backend.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"DASHBOARD_API_KEY": "", "VERCEL_ORIGIN": "http://localhost:3000"}):
        from backend.main import app
        return TestClient(app)

def test_chat_returns_answer(client):
    with patch("backend.routers.chat.ask_agent") as mock_agent:
        mock_agent.return_value = "BTC 현재 분석 중입니다."
        resp = client.post("/chat", json={"message": "BTC 어때?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["answer"] == "BTC 현재 분석 중입니다."

def test_chat_empty_message_returns_400(client):
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422  # FastAPI validation error
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

```bash
python -m pytest tests/test_chat_router.py -v
```
Expected: FAIL

- [ ] **Step 3: chat_agent.py 구현**

```python
# backend/ai/chat_agent.py
import logging
from langchain_groq import ChatGroq
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from backend.ai.agent_tools import get_portfolio_tool, get_trade_history_tool, get_market_signal_tool
from backend.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 coin_bot 투자 어시스턴트입니다.
사용자의 암호화폐 포트폴리오와 매매 내역을 조회할 수 있는 툴을 가지고 있습니다.
항상 한국어로 답변하세요. 숫자는 쉼표로 구분하고, 수익은 +/- 기호를 붙여 명확히 표시하세요.
모르는 정보는 툴로 조회한 뒤 답변하세요."""

def ask_agent(message: str) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        return "Groq API 키가 설정되지 않았습니다."

    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        temperature=0,
    )
    tools = [get_portfolio_tool, get_trade_history_tool, get_market_signal_tool]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=3)

    try:
        result = executor.invoke({"input": message})
        return result.get("output", "답변을 생성하지 못했습니다.")
    except Exception as e:
        logger.error(f"Agent 실행 오류: {e}")
        return f"오류가 발생했습니다: {str(e)}"
```

- [ ] **Step 4: chat.py 라우터 구현**

```python
# backend/routers/chat.py
from fastapi import APIRouter
from pydantic import BaseModel, field_validator
from backend.ai.chat_agent import ask_agent

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v):
        if not v.strip():
            raise ValueError("message는 비어있을 수 없습니다.")
        return v.strip()

@router.post("/chat")
def chat(req: ChatRequest):
    answer = ask_agent(req.message)
    return {"answer": answer}
```

- [ ] **Step 5: main.py에 라우터 등록**

`backend/main.py`에서:
```python
from backend.routers import chat  # import에 추가
app.include_router(chat.router)   # include_router에 추가
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
python -m pytest tests/test_chat_router.py -v
```
Expected: 2개 PASS

- [ ] **Step 7: 전체 백엔드 테스트 한번에 실행**

```bash
python -m pytest tests/ -v
```
Expected: 전부 PASS

- [ ] **Step 8: EC2 배포**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
rsync -av --exclude='.git' --exclude='venv' --exclude='__pycache__' \
  -e "ssh -i ~/Desktop/coin-bot-key.pem" \
  . ubuntu@43.203.205.237:/home/ubuntu/coin_bot/

ssh -i ~/Desktop/coin-bot-key.pem ubuntu@43.203.205.237 \
  "cd /home/ubuntu/coin_bot && source venv/bin/activate && pip install langchain==0.3.* langchain-groq==0.2.* langchain-core==0.3.* && sudo systemctl restart coinbot"
```

- [ ] **Step 9: 배포 확인**

```bash
ssh -i ~/Desktop/coin-bot-key.pem ubuntu@43.203.205.237 "sudo journalctl -u coinbot -n 20 --no-pager"
```
Expected: 오류 없이 서버 시작 로그

- [ ] **Step 10: .env에 키 추가 및 EC2 재배포**

```bash
# EC2 .env에 DASHBOARD_API_KEY 추가
ssh -i ~/Desktop/coin-bot-key.pem ubuntu@43.203.205.237 \
  "echo 'DASHBOARD_API_KEY=your-secret-key-here' >> /home/ubuntu/coin_bot/.env && sudo systemctl restart coinbot"
```

- [ ] **Step 11: 커밋**

```bash
git add backend/ai/chat_agent.py backend/routers/chat.py backend/main.py tests/test_chat_router.py
git commit -m "feat: LangChain Agent + POST /chat 엔드포인트 추가"
```

---

## Task 5: Next.js 프로젝트 셋업 & API Routes

**Files:**
- Create: `dashboard/` (Next.js 프로젝트)
- Create: `dashboard/app/api/portfolio/route.ts`
- Create: `dashboard/app/api/chat/route.ts`
- Create: `dashboard/app/api/trades/route.ts`

- [ ] **Step 1: Next.js 프로젝트 생성**

```bash
cd /Users/seodongjin/Documents/GitHub/coin_bot
npx create-next-app@14 dashboard \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*"
```

- [ ] **Step 2: 환경변수 파일 설정**

```bash
# dashboard/.env.local 생성
cat > dashboard/.env.local << 'EOF'
NEXT_PUBLIC_APP_URL=http://localhost:3000
API_BASE_URL=http://localhost:8000
API_KEY=your-dashboard-api-key-here
EOF
```

- [ ] **Step 3: 포트폴리오 API Route 작성**

```typescript
// dashboard/app/api/portfolio/route.ts
import { NextResponse } from "next/server";

export async function GET() {
  const res = await fetch(`${process.env.API_BASE_URL}/api/portfolio`, {
    headers: { "X-API-Key": process.env.API_KEY ?? "" },
    cache: "no-store",
  });
  if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
  const data = await res.json();
  return NextResponse.json(data);
}
```

- [ ] **Step 4: 채팅 API Route 작성**

```typescript
// dashboard/app/api/chat/route.ts
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const res = await fetch(`${process.env.API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": process.env.API_KEY ?? "",
    },
    body: JSON.stringify({ message: body.message }),
  });
  if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
  const data = await res.json();
  return NextResponse.json(data);
}
```

- [ ] **Step 5: 매매내역 API Route 작성**

> 참고: FastAPI `GET /api/trades` 엔드포인트는 `backend/routers/trades.py`에 이미 구현되어 있음. 별도 추가 불필요.

```typescript
// dashboard/app/api/trades/route.ts
import { NextResponse } from "next/server";

export async function GET() {
  const res = await fetch(`${process.env.API_BASE_URL}/api/trades`, {
    headers: { "X-API-Key": process.env.API_KEY ?? "" },
    cache: "no-store",
  });
  if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
  const data = await res.json();
  return NextResponse.json(data);
}
```

- [ ] **Step 6: 개발 서버 실행 확인**

```bash
cd dashboard && npm run dev
```
브라우저에서 `http://localhost:3000` 접속 → Next.js 기본 페이지 확인

- [ ] **Step 7: 커밋**

```bash
git add dashboard/
git commit -m "feat: Next.js 프로젝트 셋업 + API Routes 프록시 추가"
```

---

## Task 6: 공통 컴포넌트 & 레이아웃

**Files:**
- Modify: `dashboard/app/layout.tsx`
- Create: `dashboard/components/BottomNav.tsx`
- Create: `dashboard/components/CoinCard.tsx`
- Create: `dashboard/components/TradeTable.tsx`

- [ ] **Step 1: 루트 레이아웃 (네비게이션 포함)**

```typescript
// dashboard/app/layout.tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import BottomNav from "@/components/BottomNav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "coin_bot 대시보드",
  description: "AI 암호화폐 자동매매 대시보드",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className={`${inter.className} bg-gray-950 text-white min-h-screen`}>
        <main className="max-w-lg mx-auto pb-20 px-4">{children}</main>
        <BottomNav />
      </body>
    </html>
  );
}
```

- [ ] **Step 2: 하단 네비게이션 컴포넌트**

```typescript
// dashboard/components/BottomNav.tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/", label: "대시보드", icon: "📊" },
  { href: "/chat", label: "AI 채팅", icon: "💬" },
  { href: "/history", label: "히스토리", icon: "📋" },
];

export default function BottomNav() {
  const pathname = usePathname();
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800">
      <div className="max-w-lg mx-auto flex">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={`flex-1 flex flex-col items-center py-3 text-xs gap-1 transition-colors ${
              pathname === tab.href ? "text-blue-400" : "text-gray-500"
            }`}
          >
            <span className="text-lg">{tab.icon}</span>
            {tab.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
```

- [ ] **Step 3: 코인 카드 컴포넌트**

```typescript
// dashboard/components/CoinCard.tsx
interface Holding {
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  eval_value: number;
  profit_rate: number;
}

export default function CoinCard({ holding }: { holding: Holding }) {
  const isProfit = holding.profit_rate >= 0;
  const ticker = holding.symbol.replace("KRW-", "");

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-bold text-lg">{ticker}</p>
          <p className="text-gray-400 text-sm">{holding.quantity.toFixed(6)}개</p>
        </div>
        <div className="text-right">
          <p className={`font-bold text-lg ${isProfit ? "text-green-400" : "text-red-400"}`}>
            {isProfit ? "+" : ""}{holding.profit_rate.toFixed(2)}%
          </p>
          <p className="text-gray-400 text-sm">{holding.eval_value.toLocaleString()}원</p>
        </div>
      </div>
      <div className="mt-2 flex justify-between text-sm text-gray-500">
        <span>평균 {holding.avg_price.toLocaleString()}원</span>
        <span>현재 {holding.current_price.toLocaleString()}원</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 매매내역 테이블 컴포넌트**

```typescript
// dashboard/components/TradeTable.tsx
interface Trade {
  id: number;
  symbol: string;
  action: string;
  price: number;
  quantity: number;
  confidence: number;
  executed_at: string;
}

export default function TradeTable({ trades, limit }: { trades: Trade[]; limit?: number }) {
  const rows = limit ? trades.slice(0, limit) : trades;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800">
            <th className="text-left py-2">코인</th>
            <th className="text-left py-2">구분</th>
            <th className="text-right py-2">가격</th>
            <th className="text-right py-2">AI%</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={t.id} className="border-b border-gray-800/50">
              <td className="py-2">{t.symbol.replace("KRW-", "")}</td>
              <td className={`py-2 font-medium ${t.action === "BUY" ? "text-green-400" : "text-red-400"}`}>
                {t.action}
              </td>
              <td className="py-2 text-right">{Number(t.price).toLocaleString()}</td>
              <td className="py-2 text-right text-gray-400">{t.confidence.toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="text-center text-gray-500 py-8">매매 내역 없음</p>}
    </div>
  );
}
```

- [ ] **Step 5: 커밋**

```bash
git add dashboard/app/layout.tsx dashboard/components/
git commit -m "feat: 레이아웃, BottomNav, CoinCard, TradeTable 컴포넌트"
```

---

## Task 7: 메인 대시보드 페이지

**Files:**
- Modify: `dashboard/app/page.tsx`

- [ ] **Step 1: 메인 페이지 구현**

```typescript
// dashboard/app/page.tsx
import CoinCard from "@/components/CoinCard";
import TradeTable from "@/components/TradeTable";

async function getPortfolio() {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const res = await fetch(`${baseUrl}/api/portfolio`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

async function getTrades() {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const res = await fetch(`${baseUrl}/api/trades`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export default async function DashboardPage() {
  const [portfolio, trades] = await Promise.all([getPortfolio(), getTrades()]);

  return (
    <div className="pt-6 space-y-6">
      {/* 잔고 요약 */}
      <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-2xl p-5">
        <p className="text-blue-200 text-sm">총 평가금액</p>
        <p className="text-3xl font-bold mt-1">
          {portfolio?.total_value?.toLocaleString() ?? "-"}원
        </p>
        <p className="text-blue-200 text-sm mt-2">
          KRW 잔고: {portfolio?.krw_balance?.toLocaleString() ?? "-"}원
        </p>
      </div>

      {/* 보유 코인 */}
      <section>
        <h2 className="text-gray-400 text-sm font-medium mb-3">보유 코인</h2>
        {portfolio?.holdings?.length > 0 ? (
          <div className="space-y-3">
            {portfolio.holdings.map((h: any) => (
              <CoinCard key={h.symbol} holding={h} />
            ))}
          </div>
        ) : (
          <p className="text-gray-500 text-sm text-center py-6">보유 코인 없음</p>
        )}
      </section>

      {/* 최근 매매 */}
      <section>
        <h2 className="text-gray-400 text-sm font-medium mb-3">최근 매매</h2>
        <div className="bg-gray-900 rounded-xl p-4">
          <TradeTable trades={trades} limit={3} />
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: 개발 서버에서 확인**

```bash
cd dashboard && npm run dev
```
`http://localhost:3000` 접속 → 대시보드 카드 렌더링 확인

- [ ] **Step 3: 커밋**

```bash
git add dashboard/app/page.tsx
git commit -m "feat: 메인 대시보드 페이지 (포트폴리오 + 최근 매매)"
```

---

## Task 8: AI 채팅 페이지

**Files:**
- Create: `dashboard/app/chat/page.tsx`
- Create: `dashboard/components/ChatUI.tsx`

- [ ] **Step 1: ChatUI 컴포넌트 구현**

```typescript
// dashboard/components/ChatUI.tsx
"use client";
import { useState } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTED = [
  "지금 BTC 사도 돼?",
  "이번주 수익 어때?",
  "제일 많이 번 코인이 뭐야?",
  "내 포트폴리오 보여줘",
];

export default function ChatUI() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "안녕하세요! 포트폴리오나 매매에 대해 질문해보세요 🤖" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send(text: string) {
    if (!text.trim() || loading) return;
    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.answer ?? "오류가 발생했습니다." }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "서버 연결 오류입니다." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto space-y-3 py-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-blue-600 text-white rounded-br-sm"
                  : "bg-gray-800 text-gray-100 rounded-bl-sm"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-2xl rounded-bl-sm px-4 py-2 text-sm text-gray-400">
              분석 중...
            </div>
          </div>
        )}
      </div>

      {/* 추천 질문 */}
      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-2 pb-3">
          {SUGGESTED.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              className="text-xs bg-gray-800 text-gray-300 rounded-full px-3 py-1.5 hover:bg-gray-700 transition"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* 입력창 */}
      <div className="flex gap-2 pb-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder="질문을 입력하세요..."
          className="flex-1 bg-gray-800 rounded-full px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={() => send(input)}
          disabled={loading}
          className="bg-blue-600 rounded-full w-10 h-10 flex items-center justify-center disabled:opacity-50"
        >
          ↑
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 채팅 페이지**

```typescript
// dashboard/app/chat/page.tsx
import ChatUI from "@/components/ChatUI";

export default function ChatPage() {
  return (
    <div className="pt-6">
      <h1 className="text-lg font-bold mb-4">AI 채팅</h1>
      <ChatUI />
    </div>
  );
}
```

- [ ] **Step 3: 개발 서버에서 확인**

`http://localhost:3000/chat` → 채팅 UI 확인, 추천 질문 버튼 클릭 테스트

- [ ] **Step 4: 커밋**

```bash
git add dashboard/components/ChatUI.tsx dashboard/app/chat/
git commit -m "feat: AI 채팅 페이지 (LangChain Agent 연동)"
```

---

## Task 9: 히스토리 페이지 & 배포

**Files:**
- Create: `dashboard/app/history/page.tsx`
- Modify: `dashboard/.env.local` (프로덕션 설정)

- [ ] **Step 1: 히스토리 페이지**

```typescript
// dashboard/app/history/page.tsx
import TradeTable from "@/components/TradeTable";

async function getAllTrades() {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
  const res = await fetch(`${baseUrl}/api/trades`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export default async function HistoryPage() {
  const trades = await getAllTrades();
  return (
    <div className="pt-6">
      <h1 className="text-lg font-bold mb-4">매매 히스토리</h1>
      <p className="text-gray-500 text-sm mb-4">총 {trades.length}건</p>
      <div className="bg-gray-900 rounded-xl p-4">
        <TradeTable trades={trades} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 빌드 확인**

```bash
cd dashboard && npm run build
```
Expected: 오류 없이 빌드 성공

- [ ] **Step 3: Vercel CLI로 배포**

```bash
npm i -g vercel
cd dashboard && vercel --prod
```
배포 중 Vercel이 환경변수 물어보면:
- `API_BASE_URL` = `http://43.203.205.237` (EC2 IP)
- `API_KEY` = EC2 .env의 `DASHBOARD_API_KEY` 값

- [ ] **Step 4: EC2 VERCEL_ORIGIN 업데이트**

Vercel 배포 후 나오는 URL (예: `https://coin-bot-dashboard.vercel.app`)을 EC2 .env에 반영:
```bash
ssh -i ~/Desktop/coin-bot-key.pem ubuntu@43.203.205.237 \
  "sed -i 's|VERCEL_ORIGIN=.*|VERCEL_ORIGIN=https://your-app.vercel.app|' /home/ubuntu/coin_bot/.env && sudo systemctl restart coinbot"
```

- [ ] **Step 5: E2E 동작 확인**

1. Vercel URL에서 대시보드 접속 → 포트폴리오 카드 확인
2. `/chat` → "내 포트폴리오 보여줘" 입력 → AI 답변 확인
3. `/history` → 매매내역 테이블 확인
4. 모바일 브라우저에서 반응형 확인

- [ ] **Step 6: 최종 커밋**

```bash
git add dashboard/app/history/ dashboard/.env.local.example
git commit -m "feat: 히스토리 페이지 + Vercel 배포 완료"
```

---

## 완료 기준

- [ ] `POST /chat` 에 "이번 달 수익 어때?" 보내면 DB 조회 기반 답변 반환
- [ ] `GET /api/portfolio` 가 보유 코인 + 수익률 반환
- [ ] Vercel URL에서 3개 화면 모두 로드
- [ ] 모바일 화면 (375px)에서 레이아웃 깨지지 않음
- [ ] 브라우저 Network 탭에 `API_KEY`가 노출되지 않음
