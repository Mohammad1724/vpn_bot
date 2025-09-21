# filename: bot/handlers/usage.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from typing import List, Tuple
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
import hiddify_api
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


def _format_gb_val(val: float) -> str:
    try:
        f = float(val or 0.0)
    except Exception:
        f = 0.0
    return utils.to_persian_digits(f"{f:.2f}")


async def _live_total_usage_gb(user_id: int) -> float:
    """
    مجموع مصرف واقعی کاربر را به‌صورت زنده از پنل جمع می‌کند
    (جمع current_usage_GB تمام سرویس‌های فعال کاربر).
    در صورت بروز خطا، 0.0 برمی‌گرداند.
    """
    try:
        services = db.get_user_services(user_id) or []
        uuids = [s.get("sub_uuid") for s in services if s.get("sub_uuid")]
        if not uuids:
            return 0.0

        async def _one(uuid: str) -> float:
            try:
                info = await hiddify_api.get_user_info(uuid)
                if isinstance(info, dict):
                    return float(info.get("current_usage_GB") or 0.0)
            except Exception:
                pass
            return 0.0

        vals = await asyncio.gather(*[_one(u) for u in uuids], return_exceptions=False)
        return float(sum(v for v in vals if isinstance(v, (int, float))))
    except Exception:
        return 0.0


def _build_usage_text(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """
    - مجموع مصرف: زنده از پنل
    - تفکیک بر اساس نود: از اسنپ‌شات دوره‌ای (user_traffic)
    """
    rows = _fetch_user_traffic_rows(user_id)
    interval_min = _get_usage_interval_min()

    # تفکیک نود از اسنپ‌شات
    total_snap = sum(float(r.get("traffic_used") or 0.0) for r in rows)
    rows_sorted = sorted(rows, key=lambda r: float(r.get("traffic_used") or 0.0), reverse=True)
    try:
        last_ts = max((r.get("last_updated") or "") for r in rows if r.get("last_updated"))
    except Exception:
        last_ts = ""

    per_node_lines = []
    for r in rows_sorted:
        name = r.get("server_name") or "Unknown"
        used = _format_gb_val(r.get("traffic_used") or 0.0)
        per_node_lines.append(f"• {name}: {used} GB")

    # متن را الان نمی‌سازیم؛ اول کیبورد را بسازیم
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="acc_usage_refresh")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="acc_back_to_main")]
    ])

    # Note: مجموع مصرف (زنده) را در show_usage_menu محاسبه می‌کنیم تا async باشد
    # این تابع فقط اسکلت متن و تفکیک را برمی‌گرداند؛ مجموع بعداً جایگزین می‌شود.
    header = "📊 مصرف اینترنت شما"
    node_part = (
        "تفکیک بر اساس نود:\n" + ("\n".join(per_node_lines) if per_node_lines else "—")
    )
    last_str = utils.to_persian_digits(str(last_ts or "-"))
    tail = f"آخرین بروزرسانی: {last_str}\n(به‌صورت دوره‌ای هر {utils.to_persian_digits(str(interval_min))} دقیقه)"

    # placeholder برای مجموع (زنده) که بعداً جایگزین می‌شود
    text = (
        f"{header}\n\n"
        f"مجموع مصرف (زنده از پنل): {{LIVE_TOTAL_GB}} GB\n\n"
        f"{node_part}\n\n"
        f"{tail}"
    )
    return text, kb


async def show_usage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش مصرف تجمیعی کاربر + تفکیک به ازای هر نود.
    - مجموع مصرف: زنده از پنل (current_usage_GB همه سرویس‌ها)
    - تفکیک نود: از اسنپ‌شات user_traffic
    هم از Message (دکمه «📊 مصرف من») و هم از Callback (🔄 بروزرسانی) پشتیبانی می‌کند.
    """
    user_id = update.effective_user.id
    base_text, kb = _build_usage_text(user_id)

    # محاسبه زنده مجموع مصرف
    live_total = await _live_total_usage_gb(user_id)
    live_total_str = _format_gb_val(live_total)

    text = base_text.replace("{LIVE_TOTAL_GB}", live_total_str)

    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text=text, reply_markup=kb)
        except Exception:
            await context.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
    else:
        await update.effective_message.reply_text(text=text, reply_markup=kb)