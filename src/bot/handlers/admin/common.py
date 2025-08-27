# -*- coding: utf-8 -*-

import asyncio
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update

from bot.keyboards import get_admin_menu_keyboard, get_main_menu_keyboard
from bot.constants import ADMIN_MENU
import database as db


async def _send_with_kb(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup):
    """
    ارسال پیام با درنظر گرفتن نوع آپدیت:
    - اگر از CallbackQuery آمده باشد، پیام جدید به کاربر ارسال می‌شود (ReplyKeyboard قابل ویرایش نیست).
    - اگر Message باشد، همان‌جا پاسخ داده می‌شود.
    """
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        # تلاش برای پاک کردن پیام قبلی اینلاین (اختیاری)
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=reply_markup)


async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_with_kb(update, context, "👑 به پنل ادمین خوش آمدید.", get_admin_menu_keyboard())
    return ADMIN_MENU


async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_with_kb(update, context, "از پنل ادمین خارج شدید.", get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await _send_with_kb(update, context, "به منوی اصلی ادمین بازگشتید.", get_admin_menu_keyboard())
    return ADMIN_MENU


async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await _send_with_kb(update, context, "عملیات لغو شد.", get_admin_menu_keyboard())
    return ADMIN_MENU


async def admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await _send_with_kb(update, context, "عملیات لغو شد.", get_admin_menu_keyboard())
    return ConversationHandler.END


async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # اطلاع به کاربر (با در نظر گرفتن نوع آپدیت)
    await _send_with_kb(update, context, "ربات در حال خاموش شدن است...", get_main_menu_keyboard(update.effective_user.id))
    # بستن DB و خاموش کردن اپلیکیشن
    db.close_db()
    asyncio.create_task(context.application.shutdown())