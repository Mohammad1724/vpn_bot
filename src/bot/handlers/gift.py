# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup
from bot.keyboards import get_main_menu_keyboard
from bot.constants import CMD_CANCEL, REDEEM_GIFT
import database as db

async def gift_code_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎁 لطفاً کد هدیه خود را وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return REDEEM_GIFT

async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.upper()
    user_id = update.effective_user.id
    amount = db.use_gift_code(code, user_id)
    if amount is not None:
        await update.message.reply_text(
            f"✅ تبریک! مبلغ {amount:.0f} تومان به کیف پول شما اضافه شد.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
    else:
        await update.message.reply_text(
            "❌ کد هدیه نامعتبر یا قبلاً استفاده شده است.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
    return ConversationHandler.END  # <--- FIX: End conversation here