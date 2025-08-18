# -*- coding: utf-8 -*-

import uuid
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.constants import ADMIN_MENU, BTN_BACK_TO_ADMIN_MENU, CMD_CANCEL
import database as db

# یک state عددی ساده برای کانورسیشن ساخت کد هدیه
CREATE_GIFT_AMOUNT = 201

def _menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["➕ ساخت کد هدیه جدید", "📋 لیست کدهای هدیه"], [BTN_BACK_TO_ADMIN_MENU]],
        resize_keyboard=True
    )

async def gift_code_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # سازگار با Message و CallbackQuery
    em = update.effective_message
    await em.reply_text("🎁 بخش مدیریت کدهای هدیه", reply_markup=_menu_keyboard())
    return ADMIN_MENU

async def list_gift_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    codes = db.get_all_gift_codes()
    if not codes:
        await em.reply_text("هیچ کد هدیه‌ای تا به حال ساخته نشده است.", reply_markup=_menu_keyboard())
        return ADMIN_MENU

    await em.reply_text("📋 **لیست کدهای هدیه:**", parse_mode="Markdown")
    for code in codes:
        status = "✅ استفاده شده" if code.get('is_used') else "🟢 فعال"
        used_by = f" (توسط: `{code.get('used_by')}`)" if code.get('used_by') else ""
        text = f"`{code.get('code')}` - **{code.get('amount', 0):,.0f} تومان** - {status}{used_by}"

        keyboard = None
        if not code.get('is_used'):
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_gift_code_{code.get('code')}")
            ]])

        await em.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

    return ADMIN_MENU

async def delete_gift_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    code_to_delete = q.data.split('delete_gift_code_')[-1]

    if db.delete_gift_code(code_to_delete):
        await q.edit_message_text(f"✅ کد `{code_to_delete}` با موفقیت حذف شد.", parse_mode="Markdown")
    else:
        await q.edit_message_text(f"❌ خطا: کد `{code_to_delete}` یافت نشد یا قبلاً حذف شده بود.", parse_mode="Markdown")
    return ADMIN_MENU

async def create_gift_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text(
        "لطفاً مبلغ کد هدیه را به تومان وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return CREATE_GIFT_AMOUNT

async def create_gift_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip().replace(",", ".")
    try:
        amount = float(txt)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("❗️ لطفاً یک مبلغ عددی و مثبت وارد کنید.")
        return CREATE_GIFT_AMOUNT

    code = str(uuid.uuid4()).split('-')[0].upper()

    if db.create_gift_code(code, amount):
        await update.message.reply_text(
            f"✅ کد هدیه با موفقیت ساخته شد:\n\n`{code}`\n\nمبلغ: **{amount:,.0f} تومان**",
            parse_mode="Markdown",
            reply_markup=_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ در ساخت کد هدیه خطایی رخ داد (احتمالاً کد تکراری است). لطفاً دوباره تلاش کنید.",
            reply_markup=_menu_keyboard()
        )

    return ConversationHandler.END

async def cancel_create_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text("❌ عملیات لغو شد.", reply_markup=_menu_keyboard())
    return ConversationHandler.END