import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.database import create_tables
from backend.orchestrator import Orchestrator
from backend.routers import trades, watchlist, signals, balance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

orchestrator = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    create_tables()
    orchestrator = Orchestrator()
    orchestrator.start()

    # 텔레그램 봇 polling 시작
    from backend.telegram_bot import setup_bot
    from backend.config import get_settings
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

app = FastAPI(title="coin_bot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trades.router)
app.include_router(watchlist.router)
app.include_router(signals.router)
app.include_router(balance.router)

@app.get("/")
def root():
    return {"status": "coin_bot API 실행 중"}
