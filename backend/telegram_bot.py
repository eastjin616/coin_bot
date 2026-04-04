import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from backend.config import get_settings
from backend.database import get_db_conn

logger = logging.getLogger(__name__)

async def send_trade_alert(market: str, symbol: str, action: str, confidence: float, price: float, quantity: float, entry_price: float = 0, rsi: float = 0):
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("텔레그램 봇 토큰 없음 — 알림 건너뜀")
        return

    action_text = "매수" if action == "BUY" else "매도"

    if action == "BUY":
        icon = "🟢"
    else:
        icon = "🔴"

    lines = [
        f"{icon} {action_text} 체결!",
        f"",
        f"종목: {symbol}",
        f"체결가: {price:,.0f}원",
        f"수량: {quantity:.6f}",
        f"금액: {price * quantity:,.0f}원",
    ]

    if rsi > 0:
        lines.append(f"RSI: {rsi:.1f}")

    if action == "SELL" and entry_price > 0 and price > 0:
        pnl_pct = (price - entry_price) / entry_price * 100
        pnl_krw = (price - entry_price) * quantity
        pnl_icon = "📈" if pnl_pct >= 0 else "📉"
        lines.append(f"")
        lines.append(f"{pnl_icon} 수익률: {pnl_pct:+.2f}%")
        lines.append(f"손익: {pnl_krw:+,.0f}원")

    lines.append(f"")
    lines.append(f"💰 자동매매 시스템")

    await send_message("\n".join(lines))

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

async def send_disk_alert():
    """디스크 사용량 80% 초과 시 텔레그램 경고"""
    import shutil
    total, used, free = shutil.disk_usage("/")
    used_pct = used / total * 100
    if used_pct >= 80:
        free_gb = free / (1024 ** 3)
        text = (
            f"⚠️ 디스크 경고!\n\n"
            f"사용량: {used_pct:.1f}%\n"
            f"남은 용량: {free_gb:.2f}GB\n\n"
            f"조치 필요: /tmp 정리 등"
        )
        await send_message(text)
        logger.warning(f"디스크 사용량 경고: {used_pct:.1f}%")


async def send_weekly_report():
    """주간 수익률 리포트 텔레그램 전송"""
    try:
        import pyupbit
        from backend.execution.coin_executor import CoinExecutor

        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT action, SUM(price * quantity) as total
            FROM trades
            WHERE market = 'coin'
              AND executed_at >= NOW() - INTERVAL '7 days'
            GROUP BY action
        """)
        rows = {r["action"]: float(r["total"]) for r in cur.fetchall()}

        cur.execute("SELECT COUNT(*) as cnt FROM trades WHERE market='coin' AND executed_at >= NOW() - INTERVAL '7 days'")
        trade_count = cur.fetchone()["cnt"]

        cur.execute("""
            SELECT action, COUNT(*) as cnt FROM trades
            WHERE market='coin' AND executed_at >= NOW() - INTERVAL '7 days'
            GROUP BY action
        """)
        counts = {r["action"]: r["cnt"] for r in cur.fetchall()}
        conn.close()

        executor = CoinExecutor()
        krw = executor.get_balance_krw()

        buy_total = rows.get("BUY", 0)
        sell_total = rows.get("SELL", 0)
        pnl = sell_total - buy_total

        text = (
            f"📊 주간 수익률 리포트\n"
            f"{'='*20}\n"
            f"기간: 최근 7일\n\n"
            f"매수 횟수: {counts.get('BUY', 0)}회 ({buy_total:,.0f}원)\n"
            f"매도 횟수: {counts.get('SELL', 0)}회 ({sell_total:,.0f}원)\n"
            f"실현 손익: {pnl:+,.0f}원\n\n"
            f"현재 KRW 잔고: {krw:,.0f}원\n"
            f"총 거래 수: {trade_count}건"
        )
        await send_message(text)
    except Exception as e:
        logger.error(f"주간 리포트 실패: {e}")


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
        from backend.execution.coin_executor import CoinExecutor
        executor = CoinExecutor()
        krw_balance = float(executor.get_balance_krw() or 0)

        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT market, symbol, entry_price, quantity FROM positions")
        rows = cur.fetchall()
        conn.close()

        lines = [f"💰 업비트 잔고: {krw_balance:,.0f}원\n"]

        if rows:
            lines.append("💼 보유 포지션")
            for row in rows:
                lines.append(f"• {row['symbol']}: {float(row['quantity']):.6f} @ {float(row['entry_price']):,.0f}원")
        else:
            lines.append("📭 보유 중인 코인 없음")

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
