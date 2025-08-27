# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Tuple
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
from bot import utils

# Optional defaults from config (for display)
try:
    from config import USAGE_UPDATE_INTERVAL_MIN
except Exception:
    USAGE_UPDATE_INTERVAL_MIN = 10


def _get_usage_interval_min() -> int:
    try:
        v = db.get_setting("usage_update_interval_min")
        if v is None or str(v).strip() == "":
            return int(USAGE_UPDATE_INTERVAL_MIN or 10)
        return int(float(v))
    except Exception:
        return int(USAGE_UPDATE_INTERVAL_MIN or 10)


def _fetch_user_traffic_rows(user_id: int) -> List[dict]:
    """
    خواندن ردیف‌های ترافیک از جدول snapshot برای کاربر.
    خروجی: لیستی از dict: {server_name, traffic_used, last_updated}
    """
    try:
        conn = db._connect_db()  # internal, but fine inside this project
        cur = conn.cursor()
        cur.execute(
            "SELECT server_name, traffic_used, last_updated FROM user_traffic WHERE user_id = ?",
            (user_id,)
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def _format_gb(val: float) -> str:
    # دو رقم اعشار + اعداد فارسی
    s = f"{float(val or 0):.2f}"
    return utils.to_persian_digits(s)


def _build_usage_text(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    rows = _fetch_user_traffic_rows(user_id)
    interval_min = _get_usage_interval_min()

    if not rows:
        text = (
            "📊 مصرف شما\n\n"
            "هنوز مصرفی ثبت نشده است یا در حال همگام‌سازی با پنل هستیم.\n"
            f"(به‌صورت دوره‌ای هر {utils.to_persian_digits(str(interval_min))} دقیقه به‌روزرسانی می‌شود)"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 بروزرسانی", callback_data="acc_usage_refresh")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="acc_back_to_main")]
        ])
        return text, kb

    # جمع کل و مرتب‌سازی تفکیک نود
    total = sum(float(r.get("traffic_used") or 0.0) for r in rows)
    rows_sorted = sorted(rows, key=lambda r: float(r.get("traffic_used") or 0.0), reverse=True)

    # آخرین زمان به‌روزرسانی
    try:
        last_ts = max((r.get("last_updated") or "") for r in rows if r.get("last_updated"))
    except Exception:
        last_ts = ""

    per_node_lines = []
    for r in rows_sorted:
        name = r.get("server_name") or "Unknown"
        used = _format_gb(r.get("traffic_used") or 0.0)
        per_node_lines.append(f"• {name}: {used} GB")

    total_str = _format_gb(total)
    last_str = (last_ts or "-")
    last_str = utils.to_persian_digits(str(last_str))

    text = (
        "📊 مصرف اینترنت شما\n\n"
        f"مجموع مصرف: {total_str} GB\n\n"
        "تفکیک بر اساس نود:\n"
        f"{chr(10).join(per_node_lines)}\n\n"
        f"آخرین بروزرسانی: {last_str}\n"
        f"(به‌صورت دوره‌ای هر {utils.to_persian_digits(str(interval_min))} دقیقه)"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="acc_usage_refresh")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="acc_back_to_main")]
    ])
    return text, kb


async def show_usage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش مصرف تجمیعی کاربر + تفکیک به ازای هر نود.
    هم از Message (دکمه «📊 مصرف من») و هم از Callback (🔄 بروزرسانی) پشتیبانی می‌کند.
    """
    user_id = update.effective_user.id
    text, kb = _build_usage_text(user_id)

    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await context.bot.send_message(chat_id=user_id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)