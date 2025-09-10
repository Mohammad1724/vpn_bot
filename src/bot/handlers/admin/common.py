# filename: bot/handlers/admin/common.py
# -*- coding: utf-8 -*-

import asyncio
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton

from bot.constants import ADMIN_MENU
from bot.keyboards import get_main_menu_keyboard
import database as db


def _admin_inline_menu() -> InlineKeyboardMarkup:
    """
    منوی اصلی ادمین به صورت دکمه‌های شیشه‌ای (Inline).
    callback_data‌ها با app.py فعلی سازگارند.
    """
    rows = [
        [
            InlineKeyboardButton("➕ مدیریت پلن‌ها", callback_data="admin_plans"),
            InlineKeyboardButton("📈 گزارش‌ها و آمار", callback_data="admin_reports"),
        ],
        [
            InlineKeyboardButton("💾 پشتیبان‌گیری", callback_data="admin_backup"),
            InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("🎁 مدیریت کد هدیه", callback_data="admin_gift"),
            InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin_settings"),
        ],
        [
            InlineKeyboardButton("🏠 بازگشت به خانه", callback_data="home_menu"),
            InlineKeyboardButton("🛑 خاموش کردن ربات", callback_data="admin_shutdown"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


async def _send_with_kb(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup):
    """
    ارسال پیام با درنظر گرفتن نوع آپدیت:
    - اگر از CallbackQuery آمده باشد، پیام قبلی حذف و پیام جدید ارسال می‌شود.
    - اگر Message باشد، همان‌جا پاسخ داده می‌شود.
    """
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup)


async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ورودی منوی ادمین (هم برای Message و هم CallbackQuery).
    منوی شیشه‌ای را نمایش می‌دهد.
    """
    await _send_with_kb(update, context, "👑 به پنل ادمین خوش آمدید.", _admin_inline_menu())
    return ADMIN_MENU


async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    خروج از پنل ادمین و بازگشت به منوی اصلی کاربر (Reply Keyboard اصلی).
    """
    await _send_with_kb(update, context, "از پنل ادمین خارج شدید.", get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بازگشت به منوی اصلی ادمین در هر نقطه (پاکسازی user_data و نمایش منوی شیشه‌ای).
    """
    context.user_data.clear()
    await _send_with_kb(update, context, "به منوی اصلی ادمین بازگشتید.", _admin_inline_menu())
    return ADMIN_MENU


async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    لغو عملیات جاری و بازگشت به منوی اصلی ادمین.
    """
    context.user_data.clear()
    await _send_with_kb(update, context, "عملیات لغو شد.", _admin_inline_menu())
    return ADMIN_MENU


async def admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    لغو یک Conversation زیرمجموعه و خروج از آن؛ سپس نمایش منوی اصلی ادمین.
    """
    context.user_data.clear()
    await _send_with_kb(update, context, "عملیات لغو شد.", _admin_inline_menu())
    return ConversationHandler.END


async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    خاموش‌کردن ربات (اطلاع به کاربر، بستن DB و شات‌داون اپلیکیشن).
    """
    await _send_with_kb(update, context, "ربات در حال خاموش شدن است...", get_main_menu_keyboard(update.effective_user.id))
    db.close_db()
    asyncio.create_task(context.application.shutdown())