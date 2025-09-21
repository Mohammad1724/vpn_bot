# filename: bot/handlers/usage.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
import hiddify_api
from bot import utils

logger = logging.getLogger(__name__)


def _format_gb(val: float) -> str:
    try:
        f = float(val or 0.0)
    except Exception:
        f = 0.0
    return utils.to_persian_digits(f"{f:.2f}")


def _now_local_str() -> str:
    from datetime import datetime
    s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return utils.to_persian_digits(s)


async def _fetch_service_usage(service: dict) -> Tuple[int, str, float]:
    """
    خروجی: (service_id, name, current_usage_GB)
    اگر تماس پنل شکست بخورد، مقدار 0.0 برمی‌گرداند.
    """
    sid = int(service.get("service_id"))
    name = service.get("name") or "سرویس"
    uuid = service.get("sub_uuid")
    usage = 0.0
    try:
        info = await hiddify_api.get_user_info(uuid)
        if isinstance(info, dict):
            usage = float(info.get("current_usage_GB") or 0.0)
    except Exception as e:
        logger.warning("Failed to fetch usage for service %s (uuid=%s): %s", sid, uuid, e)
    return sid, name, usage


async def _build_usage_text(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """
    نمایش «مصرف زنده» به تفکیک سرویس (نه نود).
    مجموع و تفکیک هر دو از پنل خوانده می‌شود.
    در صورت خطا، مقدار هر سرویس صفر در نظر گرفته می‌شود.
    """
    services = db.get_user_services(user_id) or []
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="acc_usage_refresh")],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data="acc_back_to_main")]
    ])

    if not services:
        text = "📊 مصرف اینترنت شما\n\nدر حال حاضر سرویس فعالی ندارید."
        return text, kb

    coros = [_fetch_service_usage(s) for s in services if s.get("sub_uuid")]
    results = await asyncio.gather(*coros, return_exceptions=False)

    # مرتب‌سازی بر اساس مصرف نزولی
    results_sorted = sorted(results, key=lambda x: float(x[2] or 0.0), reverse=True)

    total = sum(float(r[2] or 0.0) for r in results_sorted)
    total_str = _format_gb(total)

    per_service_lines: List[str] = []
    for _, name, usage in results_sorted:
        per_service_lines.append(f"• {name}: { _format_gb(usage) } GB")

    text = (
        "📊 مصرف اینترنت شما (زنده از پنل)\n\n"
        f"مجموع مصرف: {total_str} GB\n\n"
        "تفکیک بر اساس سرویس:\n"
        f"{chr(10).join(per_service_lines)}\n\n"
        f"آخرین بروزرسانی: {_now_local_str()}\n"
        "(برای بروزرسانی زنده، دکمه زیر را بزنید)"
    )

    return text, kb


async def show_usage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش مصرف تجمیعی کاربر + تفکیک به ازای هر سرویس (زنده از پنل).
    از Message (📊 مصرف من) و Callback (🔄 بروزرسانی) پشتیبانی می‌کند.
    """
    user_id = update.effective_user.id

    try:
        text, kb = await _build_usage_text(user_id)
    except Exception as e:
        logger.error("Failed to build usage for user %s: %s", user_id, e, exc_info=True)
        text = "❌ خطا در دریافت مصرف. لطفاً دوباره تلاش کنید."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="acc_back_to_main")]
        ])

    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text=text, reply_markup=kb)
        except Exception:
            await context.bot.send_message(chat_id=user_id, text=text, reply_markup=kb)
    else:
        await update.effective_message.reply_text(text=text, reply_markup=kb)