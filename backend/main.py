import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import get_settings
from backend.database import create_tables
from backend.orchestrator import Orchestrator
from backend.routers import trades, watchlist, signals, balance, test_trade, portfolio, chat
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
app.include_router(portfolio.router)
app.include_router(chat.router)

@app.get("/")
def root():
    return {"status": "coin_bot API 실행 중"}
