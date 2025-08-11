# -*- coding: utf-8 -*-

import os
import shutil
import tempfile
from datetime import datetime, timedelta
import sqlite3

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest

from bot.utils import is_valid_sqlite
from bot.keyboards import get_admin_menu_keyboard
from bot.constants import CMD_CANCEL, BACKUP_MENU, ADMIN_MENU, RESTORE_UPLOAD, BTN_BACK_TO_ADMIN_MENU, AWAIT_SETTING_VALUE
import database as db

def _backup_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        ["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"],
        ["⚙️ تنظیمات پشتیبان‌گیری خودکار"],
        [BTN_BACK_TO_ADMIN_MENU],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        try:
            await q.edit_message_text("بخش پشتیبان‌گیری و بازیابی.", reply_markup=None)
            await q.message.reply_text("منوی پشتیبان‌گیری:", reply_markup=_backup_menu_keyboard())
        except BadRequest:
            await q.from_user.send_message("بخش پشتیبان‌گیری و بازیابی.", reply_markup=_backup_menu_keyboard())
    else:
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

# ===== Auto-backup settings =====
async def edit_auto_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        send_func = q.edit_message_text
    else:
        send_func = update.message.reply_text
        
    current_interval = db.get_setting("auto_backup_interval_hours") or "24"
    current_target = db.get_setting("backup_target_chat_id") or "ادمین اصلی"

    rows = [
        [InlineKeyboardButton(f"🕒 بازه فعلی: {current_interval}h", callback_data="edit_backup_interval")],
        [InlineKeyboardButton(f"🎯 مقصد فعلی: {current_target}", callback_data="edit_backup_target")],
        [InlineKeyboardButton("🔙 بازگشت به منوی پشتیبان‌گیری", callback_data="back_to_backup_menu")],
    ]
    await send_func("تنظیمات پشتیبان‌گیری خودکار:", reply_markup=InlineKeyboardMarkup(rows))
    return BACKUP_MENU

async def edit_backup_interval_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    current = db.get_setting("auto_backup_interval_hours") or "24"
    rows = [
        [InlineKeyboardButton("⛔ خاموش", callback_data="set_backup_interval_0")],
        [InlineKeyboardButton("⏱ هر 6 ساعت", callback_data="set_backup_interval_6")],
        [InlineKeyboardButton("🕒 هر 12 ساعت", callback_data="set_backup_interval_12")],
        [InlineKeyboardButton("📅 روزانه", callback_data="set_backup_interval_24")],
        [InlineKeyboardButton("🗓 هفتگی", callback_data="set_backup_interval_168")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="edit_auto_backup")],
    ]
    await q.edit_message_text(f"بازه پشتیبان‌گیری خودکار (فعلی: {current}h):", reply_markup=InlineKeyboardMarkup(rows))
    return BACKUP_MENU

async def set_backup_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        hours = int(q.data.replace("set_backup_interval_", ""))
        db.set_setting("auto_backup_interval_hours", str(hours))
        
        from bot import jobs
        if context.application.job_queue:
            for job in context.application.job_queue.jobs():
                if job.name == 'auto_backup_job':
                    job.schedule_removal()
            if hours > 0:
                context.application.job_queue.run_repeating(jobs.auto_backup_job, interval=timedelta(hours=hours), first=timedelta(hours=1))
        
        await q.edit_message_text("✅ بازه پشتیبان‌گیری ذخیره شد.")
        await edit_auto_backup_start(update, context)
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در ذخیره تنظیم: {e}")
    return BACKUP_MENU

async def edit_backup_target_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    current = db.get_setting("backup_target_chat_id") or "ادمین اصلی"
    msg = (
        f"🎯 مقصد فعلی بکاپ‌ها: {current}\n\n"
        "شناسه عددی چت مقصد (ربات، کانال خصوصی یا کاربر) را ارسال کنید.\n"
        "برای بازگشت به حالت پیش‌فرض (ارسال به ادمین اصلی)، یک خط تیره (-) بفرستید."
    )
    await q.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True))
    return AWAIT_SETTING_VALUE

async def backup_target_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value_raw = (update.message.text or "").strip()
    if value_raw == "-":
        db.set_setting("backup_target_chat_id", "")
    else:
        try:
            int(value_raw)
            db.set_setting("backup_target_chat_id", value_raw)
        except ValueError:
            await update.message.reply_text("❌ شناسه نامعتبر است. لطفاً فقط عدد ارسال کنید.")
            return AWAIT_SETTING_VALUE
            
    await update.message.reply_text("✅ مقصد بکاپ با موفقیت ذخیره شد.", reply_markup=_backup_menu_keyboard())
    return ConversationHandler.END