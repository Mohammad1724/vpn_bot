# -*- coding: utf-8 -*-

import os
import shutil
from telegram.ext import ContextTypes
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from bot.utils import is_valid_sqlite
from bot.keyboards import get_admin_menu_keyboard
from bot.constants import CMD_CANCEL, BACKUP_MENU, ADMIN_MENU, RESTORE_UPLOAD, BTN_BACK_TO_ADMIN_MENU
import database as db
from datetime import datetime
from telegram.error import BadRequest

async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("بخش پشتیبان‌گیری و بازیابی.", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return BACKUP_MENU

async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"backups/backup_{timestamp}.db"
    try:
        db.close_db()
        shutil.copy(db.DB_NAME, backup_filename)
        db.init_db()
        await update.message.reply_text("در حال آماده‌سازی فایل پشتیبان...")
        await context.bot.send_document(chat_id=update.effective_user.id, document=open(backup_filename, 'rb'), caption=f"پشتیبان دیتابیس - {timestamp}")
    except Exception as e:
        await update.message.reply_text(f"خطا در ارسال فایل: {e}")
    finally:
        if os.path.exists(backup_filename):
            os.remove(backup_filename)
    return BACKUP_MENU

async def restore_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"⚠️ هشدار: بازیابی دیتابیس تمام اطلاعات فعلی را حذف می‌کند.\n"
        f"برای ادامه، فایل SQLite با پسوند .db را ارسال کنید. برای لغو {CMD_CANCEL} را بفرستید.",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return RESTORE_UPLOAD

async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.endswith('.db'):
        await update.message.reply_text("فرمت فایل نامعتبر است. لطفاً یک فایل .db ارسال کنید.")
        return RESTORE_UPLOAD
    f = await doc.get_file()
    temp_path = os.path.join("backups", f"restore_temp_{datetime.now().timestamp()}.db")
    await f.download_to_drive(temp_path)
    if not is_valid_sqlite(temp_path):
        await update.message.reply_text("❌ فایل ارسالی یک دیتابیس SQLite معتبر نیست.", reply_markup=get_admin_menu_keyboard())
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return ADMIN_MENU
    context.user_data['restore_path'] = temp_path
    kb = [[InlineKeyboardButton("✅ بله، مطمئنم", callback_data="admin_confirm_restore"),
           InlineKeyboardButton("❌ خیر، لغو کن", callback_data="admin_cancel_restore")]]
    await update.message.reply_text("آیا از جایگزینی دیتابیس فعلی مطمئن هستید؟ این عمل غیرقابل بازگشت است.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return BACKUP_MENU

async def admin_confirm_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    path = context.user_data.get('restore_path')
    if not path or not os.path.exists(path):
        await q.edit_message_text("خطا: فایل پشتیبان یافت نشد.")
        return BACKUP_MENU
    try:
        db.close_db()
        shutil.move(path, db.DB_NAME)
        db.init_db()
        await q.edit_message_text("✅ دیتابیس با موفقیت بازیابی شد.\n\nبرای اعمال کامل تغییرات، ربات را ری‌استارت کنید.", parse_mode="Markdown")
    except Exception as e:
        await q.edit_message_text(f"خطا در جایگزینی دیتابیس: {e}")
    context.user_data.clear()
    return BACKUP_MENU

async def admin_cancel_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    path = context.user_data.get('restore_path')
    if path and os.path.exists(path):
        os.remove(path)
    await q.edit_message_text("عملیات بازیابی لغو شد.")
    context.user_data.clear()
    return BACKUP_MENU