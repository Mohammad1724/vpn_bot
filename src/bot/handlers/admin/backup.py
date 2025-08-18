# -*- coding: utf-8 -*-

import os
import shutil
import tempfile
from datetime import datetime, timedelta
import sqlite3

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest
from telegram.constants import ParseMode

from bot.utils import is_valid_sqlite
from bot.keyboards import get_admin_menu_keyboard
from bot.constants import (
    CMD_CANCEL, BACKUP_MENU, ADMIN_MENU, RESTORE_UPLOAD,
    BTN_BACK_TO_ADMIN_MENU, AWAIT_SETTING_VALUE
)
import database as db


def _backup_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        ["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"],
        ["⚙️ تنظیمات پشتیبان‌گیری خودکار"],
        [BTN_BACK_TO_ADMIN_MENU],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.edit_message_text("بخش پشتیبان‌گیری و بازیابی.", reply_markup=None)
            await q.message.reply_text("منوی پشتیبان‌گیری:", reply_markup=_backup_menu_keyboard())
        except BadRequest:
            await q.from_user.send_message("منوی پشتیبان‌گیری:", reply_markup=_backup_menu_keyboard())
    else:
        await em.reply_text("منوی پشتیبان‌گیری:", reply_markup=_backup_menu_keyboard())
    return BACKUP_MENU


async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_{ts}.sqlite3")

    try:
        db.close_db()
        try:
            # تلاش برای VACUUM INTO (SQLite 3.27+)
            with sqlite3.connect(db.DB_NAME) as conn:
                conn.execute("VACUUM INTO ?", (backup_path,))
        except Exception:
            # پشتیبان‌گیری با روش backup()
            with sqlite3.connect(db.DB_NAME) as src, sqlite3.connect(backup_path) as dst:
                src.backup(dst)

        await em.reply_text("در حال آماده‌سازی فایل پشتیبان...")
        with open(backup_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=InputFile(f, filename=os.path.basename(backup_path)),
                caption=f"پشتیبان دیتابیس - {ts}"
            )
    except Exception as e:
        await em.reply_text(f"❌ خطا در ارسال فایل: {e}")
    finally:
        db.init_db()
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
        except Exception:
            pass
    return BACKUP_MENU


async def restore_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text(
        f"⚠️ هشدار: بازیابی دیتابیس تمام اطلاعات فعلی را حذف می‌کند.\n"
        f"برای ادامه، فایل SQLite با پسوند .db یا .sqlite3 را ارسال کنید. برای لغو {CMD_CANCEL} را بفرستید.",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return RESTORE_UPLOAD


async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    doc = em.document
    if not doc or not (doc.file_name.endswith('.db') or doc.file_name.endswith('.sqlite3')):
        await em.reply_text("❌ فرمت فایل نامعتبر است. لطفاً یک فایل .db یا .sqlite3 ارسال کنید.")
        return RESTORE_UPLOAD

    tmp_dir = tempfile.gettempdir()
    dl_path = os.path.join(tmp_dir, f"restore_{doc.file_unique_id}.sqlite3")

    try:
        f = await doc.get_file()
        await f.download_to_drive(dl_path)
    except Exception as e:
        await em.reply_text(f"❌ خطا در دریافت فایل: {e}")
        return BACKUP_MENU

    if not is_valid_sqlite(dl_path):
        await em.reply_text("❌ فایل ارسالی یک دیتابیس SQLite معتبر نیست.", reply_markup=_backup_menu_keyboard())
        try:
            if os.path.exists(dl_path):
                os.remove(dl_path)
        except Exception:
            pass
        return BACKUP_MENU

    context.user_data['restore_path'] = dl_path
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ بله، مطمئنم", callback_data="admin_confirm_restore"),
        InlineKeyboardButton("❌ خیر، لغو کن", callback_data="admin_cancel_restore")
    ]])
    await em.reply_text(
        "آیا از جایگزینی دیتابیس فعلی مطمئن هستید؟ این عمل غیرقابل بازگشت است.",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
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
        shutil.move(path, db.DB_NAME)
        db.init_db()
        await q.edit_message_text(
            "✅ دیتابیس با موفقیت بازیابی شد.\n\nبرای اعمال کامل تغییرات، ربات را ری‌استارت کنید.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در جایگزینی دیتابیس: {e}")
    finally:
        context.user_data.pop('restore_path', None)
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
    await q.edit_message_text("❌ عملیات بازیابی لغو شد.")
    context.user_data.pop('restore_path', None)
    return BACKUP_MENU


# ===== Auto-backup settings =====
async def edit_auto_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    current_interval = db.get_setting("auto_backup_interval_hours") or "24"
    current_target = db.get_setting("backup_target_chat_id") or "ادمین اصلی"

    rows = [
        [InlineKeyboardButton(f"🕒 بازه فعلی: {current_interval}h", callback_data="edit_backup_interval")],
        [InlineKeyboardButton(f"🎯 مقصد فعلی: {current_target}", callback_data="edit_backup_target")],
        [InlineKeyboardButton("🔙 بازگشت به منوی پشتیبان‌گیری", callback_data="back_to_backup_menu")],
    ]
    if q:
        await q.answer()
        try:
            await q.edit_message_text("تنظیمات پشتیبان‌گیری خودکار:", reply_markup=InlineKeyboardMarkup(rows))
        except BadRequest:
            await q.from_user.send_message("تنظیمات پشتیبان‌گیری خودکار:", reply_markup=InlineKeyboardMarkup(rows))
    else:
        await update.effective_message.reply_text("تنظیمات پشتیبان‌گیری خودکار:", reply_markup=InlineKeyboardMarkup(rows))
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
        # حذف جاب قبلی و برنامه‌ریزی مجدد
        if context.application.job_queue:
            for job in context.application.job_queue.jobs():
                if job.name == 'auto_backup_job':
                    job.schedule_removal()
            if hours > 0:
                context.application.job_queue.run_repeating(
                    jobs.auto_backup_job,
                    interval=timedelta(hours=hours),
                    first=timedelta(hours=1),
                    name='auto_backup_job'
                )

        await q.edit_message_text("✅ بازه پشتیبان‌گیری ذخیره شد.")
        # بازگشت به تنظیمات پشتیبان‌گیری
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
        "برای بازگشت به حالت پیش‌فرض (ارسال به ادمین اصلی)، یک خط تیره (-) بفرستید.\n"
        f"{CMD_CANCEL} برای انصراف."
    )
    await q.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return AWAIT_SETTING_VALUE


async def backup_target_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value_raw = (update.effective_message.text or "").strip()
    if value_raw == "-":
        db.set_setting("backup_target_chat_id", "")
    else:
        try:
            int(value_raw)
            db.set_setting("backup_target_chat_id", value_raw)
        except ValueError:
            await update.effective_message.reply_text("❌ شناسه نامعتبر است. لطفاً فقط عدد ارسال کنید.")
            return AWAIT_SETTING_VALUE

    await update.effective_message.reply_text("✅ مقصد بکاپ با موفقیت ذخیره شد.", reply_markup=_backup_menu_keyboard())
    return BACKUP_MENU


async def cancel_backup_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text("❌ عملیات لغو شد.", reply_markup=_backup_menu_keyboard())
    return BACKUP_MENU