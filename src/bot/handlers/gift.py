# filename: bot/handlers/gift.py
# -*- coding: utf-8 -*-

from datetime import datetime
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup

from bot.keyboards import get_main_menu_keyboard
from bot.constants import CMD_CANCEL, REDEEM_GIFT
from bot import utils
import database as db


async def gift_code_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎁 لطفاً کد هدیه خود را وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return REDEEM_GIFT


async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = (update.message.text or "").strip().upper()
    user_id = update.effective_user.id

    # 1) چک کردن کد شارژ اول
    first_charge_code = (db.get_setting('first_charge_code') or '').upper()
    if code == first_charge_code:
        # چک کردن شرایط کد شارژ اول
        pct = int(db.get_setting('first_charge_bonus_percent') or 0)
        exp_raw = db.get_setting('first_charge_expires_at') or ''
        exp_dt = utils.parse_date_flexible(exp_raw) if exp_raw else None
        now = datetime.now().astimezone()

        if pct <= 0:
            await update.message.reply_text("❌ کد وارد شده نامعتبر است.", reply_markup=get_main_menu_keyboard(user_id))
            return ConversationHandler.END

        if exp_dt and now > exp_dt:
            await update.message.reply_text("❌ این کد منقضی شده است.", reply_markup=get_main_menu_keyboard(user_id))
            return ConversationHandler.END

        # چک کن آیا کاربر قبلاً شارژ داشته؟
        if hasattr(db, "get_user_charge_count") and db.get_user_charge_count(user_id) > 0:
            await update.message.reply_text("❌ این کد فقط برای اولین شارژ حساب معتبر است.", reply_markup=get_main_menu_keyboard(user_id))
            return ConversationHandler.END

        # کد معتبر است
        context.user_data['first_charge_promo_applied'] = True
        await update.message.reply_text(
            f"✅ کد شارژ اول با موفقیت فعال شد!\n\n"
            f"در شارژ بعدی خود، {pct}% پاداش دریافت خواهید کرد. لطفاً اکنون از «💳 شارژ حساب» اقدام کنید.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
        return ConversationHandler.END

    # 2) چک کردن کدهای هدیه معمولی
    amount = db.use_gift_code(code, user_id)
    if amount is not None:
        await update.message.reply_text(
            f"✅ تبریک! مبلغ {amount:,.0f} تومان به کیف پول شما اضافه شد.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
    else:
        await update.message.reply_text(
            "❌ کد هدیه نامعتبر یا قبلاً استفاده شده است.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
    return ConversationHandler.END