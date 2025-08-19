# -*- coding: utf-8 -*-

import re
import logging
import asyncio
from datetime import datetime
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.constants import ParseMode

from bot.constants import (
    USER_MANAGEMENT_MENU, BTN_BACK_TO_ADMIN_MENU,
    BROADCAST_MENU, BROADCAST_MESSAGE, BROADCAST_CONFIRM,
    BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE,
    MANAGE_USER_AMOUNT
)
from bot import utils
import database as db
import hiddify_api

logger = logging.getLogger(__name__)

# ... (بقیه توابع users.py: _user_mgmt_keyboard, _action_kb, ...) — همانند نسخه قبلی

# -------------------------------
# تایید/رد شارژ
# -------------------------------
async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    parts = q.data.split('_')
    try:
        # callback_data: admin_confirm_charge_{user_id}_{amount}_{optional_promo_code}
        user_id = int(parts[3])
        amount = int(parts[4])
        promo_code_in = parts[5].upper() if len(parts) > 5 else ""
    except (IndexError, ValueError):
        await q.edit_message_text("❌ اطلاعات دکمه نامعتبر است.")
        return

    # 1. اعمال شارژ اصلی
    ok = db.update_balance(user_id, amount)
    if not ok:
        await q.edit_message_text("❌ اعمال شارژ اصلی ناموفق بود.")
        return

    # 2. اعمال پاداش کد شارژ اول (در صورت وجود و معتبر بودن)
    bonus_applied = 0
    try:
        pc = (db.get_setting('first_charge_code') or '').upper()
        pct = int(db.get_setting('first_charge_bonus_percent') or 0)
        exp_raw = db.get_setting('first_charge_expires_at') or ''
        exp_dt = utils.parse_date_flexible(exp_raw) if exp_raw else None
        now = datetime.now().astimezone()

        if hasattr(db, "get_user_charge_count") and db.get_user_charge_count(user_id) == 0:
            if promo_code_in and promo_code_in == pc and pct > 0 and (not exp_dt or now <= exp_dt):
                bonus = int(amount * (pct / 100.0))
                if bonus > 0:
                    db.update_balance(user_id, bonus)
                    bonus_applied = bonus
    except Exception as e:
        logger.error(f"Error applying first charge bonus: {e}")

    # پیام نهایی به ادمین
    final_text = f"✅ مبلغ {amount:,} تومان برای کاربر `{user_id}` تایید شد."
    if bonus_applied > 0:
        final_text += f"\n🎁 پاداش شارژ اول به مبلغ {bonus_applied:,} تومان نیز اعمال شد."
    
    await q.edit_message_text(final_text, parse_mode=ParseMode.MARKDOWN)

    # اطلاع‌رسانی به کاربر
    try:
        user_info = db.get_user(user_id)
        new_balance = user_info['balance'] if user_info else 0
        user_message = f"✅ حساب شما به مبلغ {amount:,} تومان شارژ شد."
        if bonus_applied > 0:
            user_message += f"\n🎁 شما {bonus_applied:,} تومان پاداش شارژ اول دریافت کردید."
        user_message += f"\n💰 موجودی جدید شما: {new_balance:,.0f} تومان"
        await context.bot.send_message(chat_id=user_id, text=user_message)
    except Exception as e:
        logger.warning(f"Failed to notify user {user_id} about successful charge: {e}")

async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        user_id = int(q.data.split('_')[-1])
        await q.edit_message_text(f"❌ درخواست شارژ کاربر `{user_id}` رد شد.")
        await context.bot.send_message(chat_id=user_id, text="❌ متاسفانه درخواست شارژ شما توسط ادمین رد شد.")
    except Exception:
        await q.edit_message_text("❌ عملیات ناموفق بود.")