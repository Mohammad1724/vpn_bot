# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import database as db
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# States for the conversation
TRIAL_MENU, WAIT_DAYS, WAIT_GB = range(3)

def _get_current_values():
    days_raw = db.get_setting("trial_days")
    gb_raw = db.get_setting("trial_gb")
    try:
        days = int(float(days_raw)) if days_raw is not None else 1
    except Exception:
        days = 1
    try:
        gb = float(gb_raw) if gb_raw is not None else 1.0
    except Exception:
        gb = 1.0
    return days, gb

def _menu_keyboard():
    kb = [
        [InlineKeyboardButton("⏱ تنظیم روز تست", callback_data="trial_set_days")],
        [InlineKeyboardButton("📦 تنظیم حجم تست (GB)", callback_data="trial_set_gb")],
        [InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="back_to_settings")]
    ]
    return InlineKeyboardMarkup(kb)

async def trial_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only admin
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    days, gb = _get_current_values()
    text = (
        f"⚙️ تنظیمات سرویس تست\n\n"
        f"- روز فعلی: {days}\n"
        f"- حجم فعلی: {gb} GB\n\n"
        f"برای تغییر، یکی از گزینه‌های زیر را انتخاب کنید."
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)
    else:
        q = update.callback_query
        await q.answer()
        try:
            await q.edit_message_text(text, reply_markup=_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return TRIAL_MENU

async def ask_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏱ عدد روز تست را وارد کنید (1 تا 365):\n/cancel برای انصراف")
    return WAIT_DAYS

async def ask_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("📦 حجم تست را به گیگ وارد کنید (عدد اعشاری مجاز است، مثل 0.5):\n/cancel برای انصراف")
    return WAIT_GB

async def days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    txt = (update.message.text or "").strip()
    try:
        days = int(float(txt))
        if days <= 0 or days > 365:
            raise ValueError()
    except Exception:
        await update.message.reply_text("❌ مقدار نامعتبر. یک عدد بین 1 تا 365 وارد کنید.\n/cancel برای انصراف")
        return WAIT_DAYS

    db.set_setting("trial_days", str(days))
    await update.message.reply_text(f"✅ مدت سرویس تست روی {days} روز تنظیم شد.")
    # بازگشت به منوی تنظیمات تست
    return await trial_menu(update, context)

async def gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    txt = (update.message.text or "").strip().replace(",", ".")
    try:
        gb = float(txt)
        if gb <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("❌ مقدار نامعتبر. یک عدد مثبت (اعشاری مجاز) وارد کنید. مثل 0.5\n/cancel برای انصراف")
        return WAIT_GB

    db.set_setting("trial_gb", str(gb))
    await update.message.reply_text(f"✅ حجم سرویس تست روی {gb} گیگابایت تنظیم شد.")
    # بازگشت به منوی تنظیمات تست
    return await trial_menu(update, context)