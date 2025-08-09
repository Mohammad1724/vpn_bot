# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from bot.keyboards import get_main_menu_keyboard
from bot.constants import CMD_CANCEL, CHARGE_AMOUNT, CHARGE_RECEIPT
from telegram.error import BadRequest, Forbidden
import database as db
from config import ADMIN_ID

async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "لطفاً مبلغ شارژ (تومان) را وارد کنید (فقط عدد):",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return CHARGE_AMOUNT

async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount < 1000:
            raise ValueError
        context.user_data['charge_amount'] = amount
        card_number = db.get_setting('card_number') or "[تنظیم نشده]"
        card_holder = db.get_setting('card_holder') or "[تنظیم نشده]"
        await update.message.reply_text(
            f"لطفاً مبلغ **{amount:,} تومان** را به کارت زیر واریز کنید:\n\n`{card_number}`\n"
            f"به نام: {card_holder}\n\nسپس تصویر رسید را ارسال نمایید.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
        )
        return CHARGE_RECEIPT
    except (ValueError, TypeError):
        await update.message.reply_text("لطفاً یک عدد صحیح و حداقل ۱۰۰۰ تومان وارد کنید.")
        return CHARGE_AMOUNT

async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = context.user_data.get('charge_amount')
    if not amount:
        await update.message.reply_text("خطا: مبلغ شارژ مشخص نیست. از ابتدا شروع کنید.", reply_markup=get_main_menu_keyboard(user.id))
        return ConversationHandler.END

    receipt_photo = update.message.photo[-1]
    caption = (
        f"درخواست شارژ جدید 🔔\n\n"
        f"کاربر: {user.full_name} (@{user.username or 'N/A'})\n"
        f"آیدی عددی: `{user.id}`\n"
        f"مبلغ درخواستی: **{amount:,} تومان**"
    )
    keyboard = [[
        InlineKeyboardButton("✅ تایید شارژ", callback_data=f"admin_confirm_charge_{user.id}_{int(amount)}"),
        InlineKeyboardButton("❌ رد درخواست", callback_data=f"admin_reject_charge_{user.id}")
    ]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID, photo=receipt_photo.file_id, caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    await update.message.reply_text(
        "✅ رسید شما برای ادمین ارسال شد. لطفاً تا زمان بررسی منتظر بمانید.",
        reply_markup=get_main_menu_keyboard(user.id)
    )
    context.user_data.clear()
    return ConversationHandler.END