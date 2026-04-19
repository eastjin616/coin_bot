import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from backend.config import get_settings
from backend.database import get_db
from backend.live_performance import base_enabled_window_performance, runtime_managed_window_performance
from backend.runtime_params import normalize_runtime_symbol, set_symbol_manual_override
from backend.runtime_status import get_runtime_status

logger = logging.getLogger(__name__)

_MANUAL_HOLDING_DISCLAIMER = (
    "수동보유는 거래소 실보유이지만 자동매매 포지션에는 미편입된 자산입니다."
)


def _is_allowed_chat(update: Update) -> bool:
    settings = get_settings()
    chat_id = update.effective_chat.id
    return chat_id in settings.allowed_chat_ids


def _command_help_text() -> str:
    return (
        "안녕하세요! AI 자동매매 봇입니다. 🤖\n\n"
        "/balance - 현재 보유 포지션 조회\n"
        "/status - 실시간 RSI + 미실현 손익\n"
        "/performance - 최근 7/14/30일 실현 성과 요약\n"
        "/dca - 포지션별 DCA 추가매수 현황 조회\n"
        "/watchlist - 현재 신규매수 허용/보유 관리 종목 조회\n"
        "/watchlist_remove BTC - 해당 심볼 신규매수 제외\n"
        "/watchlist_add BTC - 해당 심볼 신규매수 허용\n"
        "/list - 사용 가능한 명령 다시 보기"
    )


def _format_signal_candle_label(iso_value: str | None) -> str:
    if not iso_value:
        return "확정 일봉 기준"
    try:
        dt = __import__("datetime").datetime.fromisoformat(iso_value)
        return f"확정 일봉 기준 ({dt.strftime('%m-%d %H:%M')})"
    except ValueError:
        return "확정 일봉 기준"


def _top_selection_summary(selection: list[dict], limit: int = 3) -> str:
    rows = [row for row in selection if row.get("enabled")]
    rows.sort(key=lambda row: float(row.get("effective_selection_score") or row.get("selection_score") or -999), reverse=True)
    if not rows:
        return "선정 종목 점수: 없음"
    summary = ", ".join(
        f"{row['symbol'].split('-')[1]} {float(row.get('effective_selection_score') or row.get('selection_score') or 0):+.1f}"
        for row in rows[:limit]
    )
    return f"선정 점수: {summary}"


def _blocked_selection_summary(selection: list[dict], limit: int = 3) -> str | None:
    rows = [row for row in selection if not row.get("enabled")]
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            0 if row.get("live_derated") else 1,
            -(float(row.get("effective_selection_score") or row.get("selection_score") or -999)),
        )
    )
    summary = ", ".join(
        f"{row['symbol'].split('-')[1]} ({'live' if row.get('live_derated') else 'score'})"
        for row in rows[:limit]
    )
    return f"제외 요약: {summary}"


def _stateboard_summary(selection: list[dict], limit: int = 5) -> str | None:
    if not selection:
        return None
    rows = sorted(
        selection,
        key=lambda row: (
            0 if row.get("state_label") == "enabled" else 1,
            -(float(row.get("effective_selection_score") or row.get("selection_score") or -999)),
        ),
    )
    summary = ", ".join(
        f"{row['symbol'].split('-')[1]}={row.get('state_label')}"
        for row in rows[:limit]
    )
    return f"상태판: {summary}"


def _format_symbol_performance_row(prefix: str, row: dict | None) -> str:
    if not row:
        return f"{prefix}: 없음"
    return (
        f"{prefix}: {row['symbol'].split('-')[1]} "
        f"{row['realized_pnl_krw']:+,.0f}원 "
        f"(승률 {row['win_rate']:.1f}%, 평균 {row['avg_pnl_pct']:+.2f}%, 매도 {row['sell_count']}회)"
    )


def _coin_ticker(symbol: str) -> str:
    return symbol.split("-")[1] if "-" in symbol else symbol


def _load_coin_position_rows() -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT symbol, entry_price, quantity FROM positions WHERE market = 'coin'")
        return [
            {
                "symbol": row["symbol"],
                "entry_price": float(row["entry_price"] or 0.0),
                "quantity": float(row["quantity"] or 0.0),
                "source": "position",
            }
            for row in cur.fetchall()
        ]


def _load_manual_holdings_from_db(tracked_symbols: set[str]) -> tuple[bool, list[dict]]:
    """manual_holdings 테이블에서 active 수동보유 조회 (tracked 제외). 실패 시 False + []."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT symbol, quantity, avg_buy_price FROM manual_holdings"
                " WHERE status IN ('alert_only', 'import')"
            )
            rows = cur.fetchall()
        return True, [
            {
                "symbol": row["symbol"],
                "entry_price": float(row["avg_buy_price"] or 0.0),
                "quantity": float(row["quantity"] or 0.0),
                "source": "manual",
            }
            for row in rows
            if row["symbol"] not in tracked_symbols
        ]
    except Exception as e:
        logger.warning(f"manual_holdings DB 조회 실패: {e}")
        return False, []


def _load_exchange_only_holdings(executor, tracked_symbols: set[str]) -> tuple[bool, list[dict]]:
    """수동보유 조회: DB 우선, 실패 시 Exchange API 폴백."""
    db_ok, manual_rows = _load_manual_holdings_from_db(tracked_symbols)
    if db_ok:
        return True, manual_rows

    logger.warning("manual_holdings DB 조회 실패 → Exchange API 폴백")
    holdings_ok, exchange_holdings = executor.get_all_coin_holdings_snapshot()
    if not holdings_ok:
        logger.warning("거래소 실보유 조회 실패 — 수동보유 표시 미반영")
        return False, []
    manual_rows = []
    for holding in exchange_holdings:
        symbol = holding["symbol"]
        if symbol in tracked_symbols:
            continue
        try:
            manual_rows.append(
                {
                    "symbol": symbol,
                    "entry_price": float(holding.get("avg_buy_price") or 0.0),
                    "quantity": float(holding.get("quantity") or 0.0),
                    "current_price": float(holding.get("current_price") or 0.0),
                    "source": "manual",
                }
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"수동보유 파싱 실패 ({symbol}): {e} → 스킵")
    return True, manual_rows


def _all_coin_rows(executor) -> tuple[list[dict], bool]:
    try:
        position_rows = _load_coin_position_rows()
    except Exception as e:
        logger.error(f"포지션 DB 조회 실패: {e}")
        position_rows = []
    tracked_symbols = {row["symbol"] for row in position_rows}
    holdings_ok, manual_rows = _load_exchange_only_holdings(executor, tracked_symbols)
    return position_rows + manual_rows, holdings_ok


def _holding_line(
    symbol: str,
    entry_price: float,
    quantity: float,
    current_price: float,
    *,
    rsi: float = 0.0,
    source: str = "position",
) -> tuple[str, float, float]:
    ticker = _coin_ticker(symbol)
    source_suffix = " (수동보유)" if source == "manual" else ""
    rsi_str = f" | RSI {rsi:.1f}" if rsi > 0 else ""
    current = current_price or entry_price

    if entry_price > 0 and current > 0:
        pnl_pct = (current - entry_price) / entry_price * 100
        pnl_krw = (current - entry_price) * quantity
        pnl_icon = "📈" if pnl_pct >= 0 else "📉"
        return (
            f"{pnl_icon} {ticker}{source_suffix}: {pnl_pct:+.1f}% ({pnl_krw:+,.0f}원){rsi_str}",
            entry_price * quantity,
            current * quantity,
        )

    eval_value = current * quantity
    return (
        f"👀 {ticker}{source_suffix}: 수량 {quantity:.6f} | 평가 {eval_value:,.0f}원{rsi_str}",
        0.0,
        eval_value,
    )


def _append_performance_section(lines: list[str], title: str, summaries: list[dict]) -> None:
    lines.append(title)
    lines.append("")
    for summary in summaries:
        lines.append(
            f"{summary['days']}일: 실현손익 {summary['realized_pnl_krw']:+,.0f}원 | "
            f"승률 {summary['win_rate']:.1f}% | 평균 {summary['avg_pnl_pct']:+.2f}% | "
            f"매도 {summary['sell_count']}회 | 매수 {summary['buy_count']}회"
        )
        lines.append(_format_symbol_performance_row("최고", summary.get("top_winner")))
        lines.append(_format_symbol_performance_row("최저", summary.get("top_loser")))
        lines.append("")


def _performance_report_text(days_list: list[int] | None = None) -> str:
    days_list = days_list or [7, 14, 30]
    managed_summaries = runtime_managed_window_performance(days_list)
    core_summaries = base_enabled_window_performance(days_list)

    lines = ["📈 최근 실현 성과 리포트", ""]
    _append_performance_section(lines, "기준 1: runtime_params 등록 종목 전체", managed_summaries)
    _append_performance_section(lines, "기준 2: 현재 base-enabled 코어", core_summaries)

    return "\n".join(lines).strip()

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
    """최근 7/14/30일 실현 성과 리포트 텔레그램 전송."""
    try:
        await send_message(_performance_report_text([7, 14, 30]))
    except Exception as e:
        logger.error(f"주간 리포트 실패: {e}")


def _dca_summary_lines() -> list[str]:
    """DCA 활성 시 포지션별 진행 현황 요약 라인 반환. 비활성이거나 포지션 없으면 빈 리스트."""
    try:
        settings = get_settings()
        if not getattr(settings, "dca_enabled", False):
            return []
        max_dca = int(getattr(settings, "max_dca_count", 2))
        step_rsi = float(getattr(settings, "dca_step_rsi", 5.0))
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT symbol, dca_count, last_buy_rsi FROM positions"
                " WHERE market = 'coin' ORDER BY symbol"
            )
            rows = cur.fetchall()
        if not rows:
            return []
        lines = ["\n➕ DCA 현황"]
        for row in rows:
            sym = row["symbol"].replace("KRW-", "")
            dca_count = int(row["dca_count"] or 0)
            last_rsi = row["last_buy_rsi"]
            next_rsi = f"{float(last_rsi) - step_rsi:.1f}" if last_rsi else "—"
            remaining = max_dca - dca_count
            lines.append(
                f"  {sym}: {dca_count}/{max_dca}회 | 다음발동 RSI≤{next_rsi} | 잔여 {remaining}회"
            )
        return lines
    except Exception as e:
        logger.warning(f"DCA 현황 조회 실패: {e}")
        return []


async def send_daily_position_report():
    """매일 오전 9시 KST 포지션 현황 + 미실현 손익 + DCA 현황 전송"""
    try:
        import pyupbit
        from backend.execution.coin_executor import CoinExecutor

        executor = CoinExecutor()
        krw = executor.get_balance_krw()
        rows, _ = _all_coin_rows(executor)

        lines = ["📋 일일 포지션 현황\n"]

        if rows:
            total_invested = 0.0
            total_current = 0.0
            for row in rows:
                symbol = row["symbol"]
                entry = float(row.get("entry_price") or 0.0)
                qty = float(row.get("quantity") or 0.0)
                current = float(row.get("current_price") or 0.0)
                if not current:
                    current = float(pyupbit.get_current_price(symbol) or entry)
                line, invested, current_value = _holding_line(
                    symbol,
                    entry,
                    qty,
                    current,
                    source=str(row.get("source") or "position"),
                )
                total_invested += invested
                total_current += current_value
                lines.append(line)
            total_pnl = total_current - total_invested
            total_pnl_pct = (total_current - total_invested) / total_invested * 100 if total_invested > 0 else 0
            lines.append(f"\n합산 미실현 손익: {total_pnl:+,.0f}원 ({total_pnl_pct:+.1f}%)")
            if any(row.get("source") == "manual" for row in rows):
                lines.append(_MANUAL_HOLDING_DISCLAIMER)
        else:
            lines.append("📭 보유 중인 코인 없음")

        lines.extend(_dca_summary_lines())
        lines.append(f"\n💰 KRW 잔고: {krw:,.0f}원")
        await send_message("\n".join(lines))
    except Exception as e:
        logger.error(f"일일 포지션 리포트 실패: {e}")


async def _start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_command_help_text())


async def _list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return
    await update.message.reply_text(_command_help_text())


async def _dca_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return
    try:
        settings = get_settings()
        dca_enabled = getattr(settings, "dca_enabled", False)
        max_dca = int(getattr(settings, "max_dca_count", 2))
        step_rsi = float(getattr(settings, "dca_step_rsi", 5.0))

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT symbol, entry_price, dca_count, last_buy_rsi
                FROM positions WHERE market = 'coin'
                ORDER BY symbol
            """)
            rows = cur.fetchall()

        if not rows:
            await update.message.reply_text("보유 포지션 없음")
            return

        lines = [f"➕ DCA 현황 (활성: {'ON' if dca_enabled else 'OFF'})\n"]
        for row in rows:
            sym = row["symbol"].replace("KRW-", "")
            dca_count = int(row["dca_count"] or 0)
            last_rsi = row["last_buy_rsi"]
            last_rsi_str = f"{float(last_rsi):.1f}" if last_rsi else "—"
            next_rsi = f"{float(last_rsi) - step_rsi:.1f}" if last_rsi else "—"
            remaining = max_dca - dca_count
            lines.append(
                f"{sym}: {dca_count}/{max_dca}회 | 직전RSI {last_rsi_str} | 다음발동 RSI≤{next_rsi} | 남은횟수 {remaining}"
            )
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"DCA 조회 실패: {e}")
        await update.message.reply_text("❌ DCA 현황 조회 중 오류가 발생했습니다.")


async def _performance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return

    try:
        await update.message.reply_text(_performance_report_text([7, 14, 30]))
    except Exception as e:
        logger.error(f"performance 조회 실패: {e}")
        await update.message.reply_text("❌ 성과 리포트 조회 중 오류가 발생했습니다.")

async def _balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return

    try:
        from backend.execution.coin_executor import CoinExecutor
        executor = CoinExecutor()
        krw_balance = float(executor.get_balance_krw() or 0)
        rows, _ = _all_coin_rows(executor)

        lines = [f"💰 업비트 잔고: {krw_balance:,.0f}원\n"]

        if rows:
            lines.append("💼 보유 포지션")
            for row in rows:
                suffix = " (수동보유)" if row.get("source") == "manual" else ""
                lines.append(
                    f"• {row['symbol']}{suffix}: {float(row['quantity']):.6f} @ {float(row['entry_price'] or 0):,.0f}원"
                )
            if any(row.get("source") == "manual" for row in rows):
                lines.append(_MANUAL_HOLDING_DISCLAIMER)
        else:
            lines.append("📭 보유 중인 코인 없음")

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"잔고 조회 실패: {e}")
        await update.message.reply_text("❌ 잔고 조회 중 오류가 발생했습니다.")

async def _status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return

    await update.message.reply_text("⏳ 조회 중...")

    try:
        import pyupbit
        from backend.ai.chart_generator import get_coin_signal_indicators
        from backend.execution.coin_executor import CoinExecutor

        executor = CoinExecutor()
        krw = executor.get_balance_krw()
        runtime = get_runtime_status()
        rows, _ = _all_coin_rows(executor)

        lines = ["📊 실시간 현황\n"]

        if rows:
            total_invested = 0.0
            total_current = 0.0
            for row in rows:
                symbol = row["symbol"]
                entry = float(row.get("entry_price") or 0.0)
                qty = float(row.get("quantity") or 0.0)
                try:
                    indicators = get_coin_signal_indicators(symbol)
                    rsi = indicators.get("rsi", 0)
                    current = float(row.get("current_price") or 0.0) or float(pyupbit.get_current_price(symbol) or entry)
                except Exception:
                    rsi = 0
                    current = float(row.get("current_price") or 0.0) or entry
                line, invested, current_value = _holding_line(
                    symbol,
                    entry,
                    qty,
                    current,
                    rsi=float(rsi or 0.0),
                    source=str(row.get("source") or "position"),
                )
                total_invested += invested
                total_current += current_value
                lines.append(line)
            total_pnl = total_current - total_invested
            total_pnl_pct = (total_current - total_invested) / total_invested * 100 if total_invested > 0 else 0
            lines.append(f"\n합산: {total_pnl:+,.0f}원 ({total_pnl_pct:+.1f}%)")
            if any(row.get("source") == "manual" for row in rows):
                lines.append(_MANUAL_HOLDING_DISCLAIMER)
        else:
            lines.append("📭 보유 중인 코인 없음")

        regime_map = {"risk_off": "리스크오프", "caution": "주의", "risk_on": "리스크온"}
        regime = regime_map.get(runtime["regime"], "리스크온")
        lines.append(f"\n🧭 장세: {regime}")
        lines.append(_format_signal_candle_label(runtime.get("btc", {}).get("signal_candle_time")))
        lines.append(f"권장 매수 비중: {runtime['suggested_order_size_ratio'] * 100:.1f}%")
        lines.append(f"허용 종목: {', '.join(sym.split('-')[1] for sym in runtime['buy_enabled_symbols'])}")
        lines.append(_top_selection_summary(runtime.get("selection", [])))
        stateboard = _stateboard_summary(runtime.get("selection", []))
        if stateboard:
            lines.append(stateboard)
        blocked_summary = _blocked_selection_summary(runtime.get("selection", []))
        if blocked_summary:
            lines.append(blocked_summary)
        live_derated = runtime.get("live_derated_symbols", {})
        if live_derated:
            derated_labels = ", ".join(symbol.split("-")[1] for symbol in sorted(live_derated))
            lines.append(f"실전 성과로 일시 제외: {derated_labels}")
        streak_cooled = runtime.get("loss_streak_cooled_symbols", {})
        if streak_cooled:
            cooled_labels = ", ".join(symbol.split("-")[1] for symbol in sorted(streak_cooled))
            lines.append(f"연속 손실 쿨다운: {cooled_labels}")
        lines.append(
            "최근 30일 실현손익: "
            f"{runtime['recent_30d']['realized_pnl_krw']:+,.0f}원 "
            f"(승률 {runtime['recent_30d']['win_rate']:.1f}%, 매도 {runtime['recent_30d']['sell_count']}회)"
        )
        lines.append(f"\n💰 KRW 잔고: {krw:,.0f}원")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"status 조회 실패: {e}")
        await update.message.reply_text("❌ 조회 중 오류가 발생했습니다.")


async def _watchlist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return

    try:
        runtime = get_runtime_status()
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT symbol FROM positions WHERE market = 'coin'")
            held_symbols = sorted(row["symbol"] for row in cur.fetchall())

        lines = [
            "🧾 런타임 감시 종목",
            f"신규매수 허용: {', '.join(sym.split('-')[1] for sym in runtime['buy_enabled_symbols']) or '없음'}",
            f"보유 관리 중: {', '.join(sym.split('-')[1] for sym in held_symbols) or '없음'}",
        ]
        manual_overrides = [row for row in runtime.get("selection", []) if row.get("manual_override")]
        if manual_overrides:
            lines.append(
                "수동 오버라이드: "
                + ", ".join(f"{row['symbol'].split('-')[1]}={row['manual_override']}" for row in manual_overrides)
            )
        lines.append("")
        lines.append("제외: /watchlist_remove BTC")
        lines.append("복구: /watchlist_add BTC")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"watchlist 조회 실패: {e}")
        await update.message.reply_text("❌ 감시 종목 조회 중 오류가 발생했습니다.")


def _held_coin_symbols() -> set[str]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM positions WHERE market = 'coin'")
        return {row["symbol"] for row in cur.fetchall()}


async def _watchlist_remove_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return

    if not context.args:
        await update.message.reply_text("사용법: /watchlist_remove BTC")
        return

    try:
        symbol = normalize_runtime_symbol(context.args[0])
        set_symbol_manual_override(symbol, "disabled", actor="telegram")
        held = symbol in _held_coin_symbols()
        if held:
            await update.message.reply_text(
                f"🚫 {symbol} 신규매수 제외 완료\n보유 중인 포지션이라 watchlist에는 남고 출구 관리만 유지됩니다."
            )
        else:
            await update.message.reply_text(
                f"🚫 {symbol} 신규매수 제외 완료\n다음 사이클부터 runtime watchlist에서도 비활성화됩니다."
            )
    except KeyError:
        await update.message.reply_text("❌ runtime_params.json에 없는 심볼입니다.")
    except Exception as e:
        logger.error(f"watchlist_remove 실패: {e}")
        await update.message.reply_text("❌ 감시 종목 제외 중 오류가 발생했습니다.")


async def _watchlist_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        await update.message.reply_text("⛔ 접근 권한이 없습니다.")
        return

    if not context.args:
        await update.message.reply_text("사용법: /watchlist_add BTC")
        return

    try:
        symbol = normalize_runtime_symbol(context.args[0])
        set_symbol_manual_override(symbol, "enabled", actor="telegram")
        await update.message.reply_text(
            f"✅ {symbol} 신규매수 허용 완료\n다음 사이클부터 runtime selection에 다시 반영됩니다."
        )
    except KeyError:
        await update.message.reply_text("❌ runtime_params.json에 없는 심볼입니다.")
    except Exception as e:
        logger.error(f"watchlist_add 실패: {e}")
        await update.message.reply_text("❌ 감시 종목 복구 중 오류가 발생했습니다.")

def setup_bot() -> Application:
    settings = get_settings()
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", _start_handler))
    app.add_handler(CommandHandler("list", _list_handler))
    app.add_handler(CommandHandler("balance", _balance_handler))
    app.add_handler(CommandHandler("status", _status_handler))
    app.add_handler(CommandHandler("performance", _performance_handler))
    app.add_handler(CommandHandler("dca", _dca_handler))
    app.add_handler(CommandHandler("watchlist", _watchlist_handler))
    app.add_handler(CommandHandler("watchlist_remove", _watchlist_remove_handler))
    app.add_handler(CommandHandler("watchlist_add", _watchlist_add_handler))
    return app
