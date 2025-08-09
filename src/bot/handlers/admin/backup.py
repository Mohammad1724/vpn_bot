# -*- coding: utf-8 -*-

import os
import io
import sqlite3
import shutil
import tempfile
from datetime import datetime

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest

from bot.utils import is_valid_sqlite
from bot.keyboards import get_admin_menu_keyboard
from bot.constants import CMD_CANCEL, BACKUP_MENU, ADMIN_MENU, RESTORE_UPLOAD, BTN_BACK_TO_ADMIN_MENU
import database as db


def _backup_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"], [BTN_BACK_TO_ADMIN_MENU]]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بخش پشتیبان‌گیری و بازیابی.", reply_markup=_backup_menu_keyboard())
    return BACKUP_MENU


async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ذخیره بکاپ کنار فایل دیتابیس در پوشه backups
    base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_{ts}.sqlite3")

    try:
        # اتصال فعلی را ببند تا فایل قفل نباشد
        db.close_db()

        # تلاش 1: VACUUM INTO (ایمن‌ترین روش، نیازمند SQLite >= 3.27)
        try:
            with sqlite3.connect(db.DB_NAME) as conn:
                # خالی‌کردن WAL تا مطمئن‌تر باشیم
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
                conn.execute("VACUUM INTO ?", (backup_path,))
        except Exception:
            # تلاش 2: API پشتیبان‌گیری sqlite (سازگار با نسخه‌های قدیمی)
            with sqlite3.connect(db.DB_NAME) as src, sqlite3.connect(backup_path) as dst:
                src.backup(dst)

        await update.message.reply_text("در حال ارسال فایل پشتیبان...")
        with open(backup_path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=InputFile(f, filename=os.path.basename(backup_path)),
                caption=f"پشتیبان دیتابیس - {ts}"
            )
        await update.message.reply_text("تمام شد.", reply_markup=_backup_menu_keyboard())
        return BACKUP_MENU

    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال فایل: {e}", reply_markup=_backup_menu_keyboard())
        return BACKUP_MENU
    finally:
        # اتصال را دوباره برقرار کن
        try:
            db.init_db()
        except Exception:
            pass
        # پاک‌سازی فایل بکاپ موقتی
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
        except Exception:
            pass


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
    if not doc:
        await update.message.reply_text("❌ لطفاً فایل پشتیبان را به‌صورت Document ارسال کنید.")
        return RESTORE_UPLOAD

    # محدودیت منطقی حجم (مثلاً 50MB)
    if doc.file_size and doc.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("❌ حجم فایل زیاد است (حداکثر 50 مگابایت).")
        return RESTORE_UPLOAD

    # دانلود فایل به مسیر موقت
    tmp_dir = tempfile.gettempdir()
    dl_path = os.path.join(tmp_dir, f"restore_{doc.file_unique_id}.sqlite3")
    try:
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(custom_path=dl_path)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دانلود فایل: {e}")
        return RESTORE_UPLOAD

    # اعتبارسنجی فایل
    try:
        if not is_valid_sqlite(dl_path):
            await update.message.reply_text("❌ فایل ارسالی یک دیتابیس SQLite معتبر نیست.")
            try:
                os.remove(dl_path)
            except Exception:
                pass
            return RESTORE_UPLOAD
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در بررسی فایل: {e}")
        try:
            os.remove(dl_path)
        except Exception:
            pass
        return RESTORE_UPLOAD

    context.user_data['restore_path'] = dl_path
    kb = [[InlineKeyboardButton("✅ بله، مطمئنم", callback_data="admin_confirm_restore"),
           InlineKeyboardButton("❌ خیر، لغو کن", callback_data="admin_cancel_restore")]]
    await update.message.reply_text(
        "آیا از جایگزینی دیتابیس فعلی مطمئن هستید؟ این عمل غیرقابل بازگشت است.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return BACKUP_MENU


async def admin_confirm_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    path = context.user_data.get('restore_path')
    if not path or not os.path.exists(path):
        await q.edit_message_text("❌ خطا: فایل پشتیبان یافت نشد.")
        return BACKUP_MENU
    try:
        db.close_db()

        # حذف فایل‌های wal/shm قدیمی برای جلوگیری از تداخل
        for ext in (".wal", ".shm"):
            try:
                os.remove(db.DB_NAME + ext)
            except Exception:
                pass

        # بکاپ از دیتابیس فعلی قبل از جایگزینی (احتیاطی)
        try:
            base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
            backup_dir = os.path.join(base_dir, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copyfile(db.DB_NAME, os.path.join(backup_dir, f"pre_restore_{ts}.sqlite3"))
        except Exception:
            pass

        shutil.copyfile(path, db.DB_NAME)
        db.init_db()

        await q.edit_message_text("✅ دیتابیس با موفقیت بازیابی شد.\n\nبرای اعمال کامل تغییرات، ربات را ری‌استارت کنید.", parse_mode="Markdown")
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در جایگزینی دیتابیس: {e}")
    finally:
        context.user_data.clear()
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    return BACKUP_MENU


async def admin_cancel_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    path = context.user_data.get('restore_path')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass
    await q.edit_message_text("عملیات بازیابی لغو شد.")
    context.user_data.clear()
    return BACKUP_MENU