import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from backend.config import get_settings
from backend.database import get_db_conn

logger = logging.getLogger(__name__)

async def send_trade_alert(market: str, symbol: str, action: str, confidence: float, price: float, quantity: float):
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("텔레그램 봇 토큰 없음 — 알림 건너뜀")
        return

    if market == "coin":
        icon = "🪙"
    elif action == "BUY":
        icon = "📈"
    else:
        icon = "📉"

    action_text = "매수" if action == "BUY" else "매도"
    market_text = "코인" if market == "coin" else "주식"

    text = (
        f"{icon} {action_text} 실행! ({market_text})\n\n"
        f"종목: {symbol}\n"
        f"신호: {action}\n"
        f"신뢰도: {confidence:.1f}%\n"
        f"체결가: {price:,.0f}원\n"
        f"수량: {quantity:.6f}\n\n"
        f"💰 자동매매 시스템"
    )

    await send_message(text)

async def send_message(text: str):
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.allowed_chat_ids:
        logger.warning("텔레그램 설정 없음 — 알림 건너뜀")
        return

    from telegram import Bot
    bot = Bot(token=settings.telegram_bot_token)
    for chat_id in settings.allowed_chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logger.error(f"텔레그램 알림 실패 (chat_id={chat_id}): {e}")

async def _start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "안녕하세요! AI 자동매매 봇입니다. 🤖\n\n"
        "/balance - 현재 보유 포지션 조회"
    )

async def _balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_settings()
    chat_id = update.effective_chat.id
    if chat_id not in settings.allowed_chat_ids:
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return

    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT market, symbol, entry_price, quantity FROM positions")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text("📭 현재 보유 중인 포지션이 없습니다.")
            return

        lines = ["💼 현재 포지션\n"]
        for market, symbol, entry_price, quantity in rows:
            lines.append(f"• [{market.upper()}] {symbol}: {quantity:.6f} @ {entry_price:,.0f}원")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"잔고 조회 실패: {e}")
        await update.message.reply_text("❌ 잔고 조회 중 오류가 발생했습니다.")

def setup_bot() -> Application:
    settings = get_settings()
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", _start_handler))
    app.add_handler(CommandHandler("balance", _balance_handler))
    return app
