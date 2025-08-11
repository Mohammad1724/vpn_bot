# -*- coding: utf-8 -*-

import os
import shutil
import tempfile
from datetime import datetime
import sqlite3

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest

from bot.utils import is_valid_sqlite
from bot.keyboards import get_admin_menu_keyboard
from bot.constants import CMD_CANCEL, BACKUP_MENU, ADMIN_MENU, RESTORE_UPLOAD, BTN_BACK_TO_ADMIN_MENU
import database as db

def _backup_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        ["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"],
        ["⚙️ تنظیمات پشتیبان‌گیری خودکار"],
        [BTN_BACK_TO_ADMIN_MENU],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بخش پشتیبان‌گیری و بازیابی.", reply_markup=_backup_menu_keyboard())
    return BACKUP_MENU

async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_{ts}.sqlite3")

    try:
        db.close_db()
        try:
            with sqlite3.connect(db.DB_NAME) as conn:
                conn.execute("VACUUM INTO ?", (backup_path,))
        except Exception:
            with sqlite3.connect(db.DB_NAME) as src, sqlite3.connect(backup_path) as dst:
                src.backup(dst)

        await update.message.reply_text("در حال آماده‌سازی فایل پشتیبان...")
        with open(backup_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=InputFile(f, filename=os.path.basename(backup_path)),
                caption=f"پشتیبان دیتابیس - {ts}"
            )
    except Exception as e:
        await update.message.reply_text(f"خطا در ارسال فایل: {e}")
    finally:
        db.init_db()
        if os.path.exists(backup_path):
            os.remove(backup_path)
    return BACKUP_MENU

async def restore_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"⚠️ هشدار: بازیابی دیتابیس تمام اطلاعات فعلی را حذف می‌کند.\n"
        f"برای ادامه، فایل SQLite با پسوند .db یا .sqlite3 را ارسال کنید. برای لغو {CMD_CANCEL} را بفرستید.",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return RESTORE_UPLOAD

async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not (doc.file_name.endswith('.db') or doc.file_name.endswith('.sqlite3')):
        await update.message.reply_text("فرمت فایل نامعتبر است. لطفاً یک فایل .db یا .sqlite3 ارسال کنید.")
        return RESTORE_UPLOAD
    
    tmp_dir = tempfile.gettempdir()
    dl_path = os.path.join(tmp_dir, f"restore_{doc.file_unique_id}.sqlite3")
    
    f = await doc.get_file()
    await f.download_to_drive(dl_path)

    if not is_valid_sqlite(dl_path):
        await update.message.reply_text("❌ فایل ارسالی یک دیتابیس SQLite معتبر نیست.", reply_markup=get_admin_menu_keyboard())
        if os.path.exists(dl_path):
            os.remove(dl_path)
        return ADMIN_MENU
        
    context.user_data['restore_path'] = dl_path
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
    finally:
        context.user_data.clear()
        if path and os.path.exists(path):
            os.remove(path)
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