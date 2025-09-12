# -*- coding: utf-8 -*-

import os
import shutil
import tempfile
from datetime import datetime, timedelta
import sqlite3

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest
from telegram.constants import ParseMode

from bot.utils import is_valid_sqlite
from bot.constants import (
    CMD_CANCEL, BACKUP_MENU, ADMIN_MENU, RESTORE_UPLOAD, AWAIT_SETTING_VALUE
)
import database as db

# ---------------- Inline Keyboards ----------------
def _kb(rows): return InlineKeyboardMarkup(rows)

def _backup_menu_inline_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("📥 دریافت فایل پشتیبان", callback_data="backup_download")],
        [InlineKeyboardButton("📤 بارگذاری فایل پشتیبان", callback_data="backup_restore")],
        [InlineKeyboardButton("⚙️ تنظیمات پشتیبان‌گیری خودکار", callback_data="edit_auto_backup")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

def _back_to_backup_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("🔙 بازگشت به منوی پشتیبان‌گیری", callback_data="back_to_backup_menu")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

async def _send_or_edit(update: Update, text: str, reply_markup=None, parse_mode: ParseMode | None = ParseMode.HTML):
    q = getattr(update, "callback_query", None)
    if q:
        try: await q.answer()
        except Exception: pass
        try:
            await q.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as e:
            emsg = str(e).lower()
            if "can't parse entities" in emsg or "can't find end of the entity" in emsg:
                try:
                    await q.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
                except Exception:
                    try:
                        await q.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
                    except Exception:
                        pass
            else:
                try:
                    await q.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
                except BadRequest as e2:
                    emsg2 = str(e2).lower()
                    if "can't parse entities" in emsg2 or "can't find end of the entity" in emsg2:
                        await q.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
    else:
        try:
            await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as e:
            emsg = str(e).lower()
            if "can't parse entities" in emsg or "can't find end of the entity" in emsg:
                await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=None)

# ---------------- Main Menu ----------------
async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_or_edit(update, "💾 بخش پشتیبان‌گیری و بازیابی", reply_markup=_backup_menu_inline_kb(), parse_mode=ParseMode.HTML)
    return BACKUP_MENU

# ---------------- Download Backup ----------------
async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:  # اگر از کال‌بک آمده
        await _send_or_edit(update, "⏳ در حال آماده‌سازی فایل پشتیبان...", reply_markup=_back_to_backup_kb())

    base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_{ts}.sqlite3")

    try:
        db.close_db()
        try:
            # روش سریع (SQLite 3.27+)
            with sqlite3.connect(db.DB_NAME) as conn:
                conn.execute("VACUUM INTO ?", (backup_path,))
        except Exception:
            # روش جایگزین
            with sqlite3.connect(db.DB_NAME) as src, sqlite3.connect(backup_path) as dst:
                src.backup(dst)

        await update.effective_message.reply_text("📦 در حال ارسال فایل پشتیبان...")
        with open(backup_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=InputFile(f, filename=os.path.basename(backup_path)),
                caption=f"پشتیبان دیتابیس - {ts}"
            )
        # نمایش منو
        await update.effective_message.reply_text("منوی پشتیبان‌گیری:", reply_markup=_backup_menu_inline_kb())
    except Exception as e:
        await update.effective_message.reply_text(f"❌ خطا در ارسال فایل: {e}", reply_markup=_backup_menu_inline_kb())
    finally:
        db.init_db()
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
        except Exception:
            pass
    return BACKUP_MENU

# ---------------- Restore Backup ----------------
async def restore_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚠️ هشدار: بازیابی دیتابیس تمام اطلاعات فعلی را حذف می‌کند.\n"
        "برای ادامه، فایل SQLite با پسوند .db یا .sqlite3 را ارسال کنید."
    )
    await _send_or_edit(update, text, reply_markup=_back_to_backup_kb(), parse_mode=ParseMode.HTML)
    return RESTORE_UPLOAD

async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    doc = em.document
    if not doc or not (doc.file_name.endswith('.db') or doc.file_name.endswith('.sqlite3')):
        await em.reply_text("❌ فرمت فایل نامعتبر است. لطفاً یک فایل .db یا .sqlite3 ارسال کنید.", reply_markup=_backup_menu_inline_kb())
        return BACKUP_MENU

    tmp_dir = tempfile.gettempdir()
    dl_path = os.path.join(tmp_dir, f"restore_{doc.file_unique_id}.sqlite3")

    try:
        f = await doc.get_file()
        await f.download_to_drive(dl_path)
    except Exception as e:
        await em.reply_text(f"❌ خطا در دریافت فایل: {e}", reply_markup=_backup_menu_inline_kb())
        return BACKUP_MENU

    if not is_valid_sqlite(dl_path):
        await em.reply_text("❌ فایل ارسالی یک دیتابیس SQLite معتبر نیست.", reply_markup=_backup_menu_inline_kb())
        try:
            if os.path.exists(dl_path):
                os.remove(dl_path)
        except Exception:
            pass
        return BACKUP_MENU

    context.user_data['restore_path'] = dl_path
    kb = _kb([
        [InlineKeyboardButton("✅ بله، مطمئنم", callback_data="admin_confirm_restore")],
        [InlineKeyboardButton("❌ خیر، لغو کن", callback_data="admin_cancel_restore")]
    ])
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
        await q.edit_message_text("❌ خطا: فایل پشتیبان یافت نشد.", reply_markup=_backup_menu_inline_kb())
        return BACKUP_MENU
    try:
        db.close_db()
        shutil.move(path, db.DB_NAME)
        db.init_db()
        await q.edit_message_text(
            "✅ دیتابیس با موفقیت بازیابی شد.\n\nبرای اعمال کامل تغییرات، ربات را ری‌استارت کنید.",
            reply_markup=_backup_menu_inline_kb(),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در جایگزینی دیتابیس: {e}", reply_markup=_backup_menu_inline_kb())
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
    await q.edit_message_text("❌ عملیات بازیابی لغو شد.", reply_markup=_backup_menu_inline_kb())
    context.user_data.pop('restore_path', None)
    return BACKUP_MENU

# ---------------- Auto-backup settings ----------------
async def edit_auto_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_interval = db.get_setting("auto_backup_interval_hours") or "24"
    current_target = db.get_setting("backup_target_chat_id") or "ادمین اصلی"

    rows = [
        [InlineKeyboardButton(f"🕒 بازه فعلی: {current_interval}h", callback_data="edit_backup_interval")],
        [InlineKeyboardButton(f"🎯 مقصد فعلی: {current_target}", callback_data="edit_backup_target")],
        [InlineKeyboardButton("🔙 بازگشت به منوی پشتیبان‌گیری", callback_data="back_to_backup_menu")]
    ]
    await _send_or_edit(update, "⚙️ تنظیمات پشتیبان‌گیری خودکار:", reply_markup=_kb(rows))
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
        [InlineKeyboardButton("🔙 بازگشت", callback_data="edit_auto_backup")]
    ]
    await q.edit_message_text(f"🕒 بازه پشتیبان‌گیری خودکار (فعلی: {current}h):", reply_markup=_kb(rows))
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
        "برای بازگشت به حالت پیش‌فرض (ارسال به ادمین اصلی)، یک خط تیره (-) بفرستید."
    )
    # فلگ تعیین مقصد بکاپ
    context.user_data['awaiting_backup_target'] = True
    await q.edit_message_text(
        msg,
        reply_markup=_kb([[InlineKeyboardButton("❌ انصراف", callback_data="back_to_backup_menu")]])
    )
    return AWAIT_SETTING_VALUE

async def backup_target_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # فقط اگر در حالت ویرایش مقصد بکاپ هستیم
    if not context.user_data.get('awaiting_backup_target'):
        return AWAIT_SETTING_VALUE

    value_raw = (update.effective_message.text or "").strip()
    if value_raw == "-":
        db.set_setting("backup_target_chat_id", "")
    else:
        try:
            int(value_raw)
            db.set_setting("backup_target_chat_id", value_raw)
        except ValueError:
            await update.effective_message.reply_text(
                "❌ شناسه نامعتبر است. لطفاً فقط عدد ارسال کنید.",
                reply_markup=_kb([[InlineKeyboardButton("❌ انصراف", callback_data="back_to_backup_menu")]])
            )
            return AWAIT_SETTING_VALUE

    context.user_data.pop('awaiting_backup_target', None)
    await update.effective_message.reply_text("✅ مقصد بکاپ با موفقیت ذخیره شد.", reply_markup=_backup_menu_inline_kb())
    return BACKUP_MENU

# انتخابی (فعلاً استفاده نمی‌شود چون از دکمه شیشه‌ای انصراف استفاده می‌کنیم)
async def cancel_backup_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('awaiting_backup_target', None)
    await update.effective_message.reply_text("❌ عملیات لغو شد.", reply_markup=_backup_menu_inline_kb())
    return BACKUP_MENU