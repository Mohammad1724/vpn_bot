# -*- coding: utf-8 -*-

import asyncio
import logging
import shutil
import os
import sqlite3
from datetime import datetime, timedelta, time, timezone
from telegram.ext import Application, ContextTypes
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError
from telegram import InputFile

import database as db
import hiddify_api
from config import ADMIN_ID
from bot.utils import get_service_status
from bot.handlers.admin.reports import send_daily_summary, send_weekly_summary

logger = logging.getLogger(__name__)

# ========== Auto-backup (send DB file to admin) ==========
async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """پشتیبان‌گیری خودکار دیتابیس و ارسال به مقصد تنظیم‌شده"""
    logger.info("Job: running auto-backup...")

    base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"auto_backup_{timestamp}.sqlite3"
    backup_path = os.path.join(backup_dir, backup_filename)

    # حذف بکاپ‌های بسیار قدیمی برای مدیریت فضا
    manage_old_backups(backup_dir)

    # مقصد ارسال: اگر تنظیم نشده باشد، به ادمین اصلی ارسال می‌شود
    target_chat_id = db.get_setting("backup_target_chat_id") or ADMIN_ID

    db_closed = False
    try:
        # اتصال فعلی را موقتاً ببندیم تا بکاپ سازگار باشد
        db.close_db()
        db_closed = True

        try:
            # VACUUM INTO در SQLite 3.27+
            version = sqlite3.sqlite_version_info
            if version >= (3, 27, 0):
                with sqlite3.connect(db.DB_NAME) as conn:
                    conn.execute("VACUUM INTO ?", (backup_path,))
                logger.info("Auto-backup: VACUUM INTO succeeded")
            else:
                # روش backup() برای نسخه‌های قدیمی‌تر
                with sqlite3.connect(db.DB_NAME) as src, sqlite3.connect(backup_path) as dst:
                    src.backup(dst)
                logger.info("Auto-backup: backup() API succeeded")
        except Exception as e:
            logger.error("SQLite backup methods failed (%s). Falling back to file copy.", e, exc_info=True)
            shutil.copy2(db.DB_NAME, backup_path)
            logger.info("Auto-backup: file copy succeeded")

        # ارسال فایل
        with open(backup_path, "rb") as f:
            await context.bot.send_document(
                chat_id=target_chat_id,
                document=InputFile(f, filename=backup_filename),
                caption=f"پشتیبان خودکار دیتابیس - {timestamp}",
            )
        logger.info("Auto-backup sent to chat %s", target_chat_id)

    except Exception as e:
        logger.error("Auto-backup failed: %s", e, exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=target_chat_id,
                text=f"⚠️ بکاپ خودکار با خطا مواجه شد:\n{e}",
            )
        except Exception as msg_err:
            logger.error("Failed to send backup error notification: %s", msg_err, exc_info=True)
    finally:
        if db_closed:
            db.init_db()
        # فایل بکاپ روی سرور باقی می‌ماند (مدیریت چرخش در manage_old_backups انجام می‌شود)


def manage_old_backups(backup_dir: str, max_backups: int = 10):
    """نگهداشت تنها آخرین max_backups فایل بکاپ و حذف بقیه"""
    try:
        files = [
            f for f in os.listdir(backup_dir)
            if f.startswith("auto_backup_") and f.endswith(".sqlite3")
        ]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
        if len(files) > max_backups:
            for old in files[:-max_backups]:
                os.remove(os.path.join(backup_dir, old))
                logger.info("Removed old backup file: %s", old)
    except Exception as e:
        logger.error("Error managing old backups: %s", e, exc_info=True)


# ========== Low-usage alert (placeholder) ==========
async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: checking low-usage services... (not implemented)")


# ========== Expiry reminder (settings-driven) ==========
async def expiry_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """
    ارسال یادآوری انقضا بر اساس تنظیمات.
    """
    try:
        enabled = db.get_setting("expiry_reminder_enabled")
        if str(enabled).lower() in ("0", "false", "off"):
            return

        try:
            days_threshold = int(float(db.get_setting("expiry_reminder_days") or 3))
        except Exception:
            days_threshold = 3

        template = db.get_setting("expiry_reminder_message") or (
            "⏰ سرویس «{service_name}» شما {days} روز دیگر منقضی می‌شود.\n"
            "برای جلوگیری از قطعی، از «📋 سرویس‌های من» تمدید کنید."
        )

        services = db.get_all_active_services()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for svc in services:
            try:
                info = await hiddify_api.get_user_info(svc["sub_uuid"])
                if isinstance(info, dict) and info.get("_not_found"):
                    await _remove_stale_service(svc, context)
                    continue
                if not info:
                    continue

                status, expiry_jalali, is_expired = get_service_status(info)
                if is_expired or not expiry_jalali or expiry_jalali == "N/A":
                    continue

                try:
                    import jdatetime  # optional
                    y, m, d = map(int, expiry_jalali.split("/"))
                    jalali_date = jdatetime.date(y, m, d)
                    gregorian_expiry = jalali_date.togregorian()
                    days_left = (gregorian_expiry - datetime.now().date()).days
                except Exception:
                    continue

                if days_left <= 0 or days_left > days_threshold:
                    continue

                if db.was_reminder_sent(svc["service_id"], "expiry", today):
                    continue

                text = template.format(days=days_left, service_name=(svc.get("name") or "سرویس"))
                try:
                    await context.bot.send_message(chat_id=svc["user_id"], text=text)
                    db.mark_reminder_sent(svc["service_id"], "expiry", today)
                except RetryAfter as e:
                    await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
                    await context.bot.send_message(chat_id=svc["user_id"], text=text)
                    db.mark_reminder_sent(svc["service_id"], "expiry", today)
                except (Forbidden, BadRequest, TimedOut, NetworkError):
                    pass

                await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug("expiry check for service %s failed: %s", svc.get("service_id"), e)

    except Exception as e:
        logger.error("expiry_reminder_job error: %s", e, exc_info=True)


async def _remove_stale_service(service: dict, context: ContextTypes.DEFAULT_TYPE):
    try:
        db.delete_service(service["service_id"])
        name = service.get("name") or ""
        name_part = f"({name}) " if name else ""
        await context.bot.send_message(
            chat_id=service["user_id"],
            text=f"🗑️ سرویس {name_part}در پنل یافت نشد و از لیست شما حذف شد.",
        )
        logger.info("Removed stale service %s (uuid=%s)", service["service_id"], service["sub_uuid"])
    except Exception as e:
        logger.error("Failed to remove stale service %s: %s", service["service_id"], e, exc_info=True)


# ========== Scheduler hooks ==========
def _is_on(keys: list[str], default: str = "0") -> bool:
    """
    خواندن چند کلید و اگر یکی true بود، فعال تلقی می‌شود.
    برای سازگاری با نام‌های قدیم/جدید تنظیمات.
    """
    for k in keys:
        v = db.get_setting(k)
        if v is not None and str(v).lower() in ("1", "true", "on", "yes"):
            return True
    return str(default).lower() in ("1", "true", "on", "yes")


async def post_init(app: Application):
    """
    در PTB v21 نیازی به ساخت JobQueue جداگانه یا start کردن دستی نیست.
    از app.job_queue استفاده کنید.
    """
    try:
        jq = app.job_queue  # JobQueue داخلی اپلیکیشن

        # گزارش‌ها (حمایت از نام کلید قدیمی و جدید)
        if _is_on(["report_daily_enabled", "daily_report_enabled"], default="0"):
            jq.run_daily(send_daily_summary, time=time(hour=23, minute=50), name="daily_report")
            logger.info("Daily report job scheduled.")

        if _is_on(["report_weekly_enabled", "weekly_report_enabled"], default="0"):
            jq.run_daily(send_weekly_summary, time=time(hour=22, minute=0), days=(4,), name="weekly_report")  # Friday
            logger.info("Weekly report job scheduled.")

        # بکاپ خودکار
        try:
            backup_interval = int(db.get_setting("auto_backup_interval_hours") or 0)
        except Exception:
            backup_interval = 0

        if backup_interval > 0:
            jq.run_repeating(
                auto_backup_job,
                interval=timedelta(hours=backup_interval),
                first=timedelta(hours=1),
                name="auto_backup_job",
            )
            logger.info("Auto-backup job scheduled every %d hours.", backup_interval)

        # یادآوری انقضا
        try:
            exp_hour = int(float(db.get_setting("expiry_reminder_hour") or 9))
        except Exception:
            exp_hour = 9

        if _is_on(["expiry_reminder_enabled"], default="1"):
            jq.run_daily(expiry_reminder_job, time=time(hour=exp_hour, minute=0), name="expiry_reminder")
            logger.info("Expiry reminder job scheduled at %02d:00", exp_hour)

        logger.info("JobQueue: jobs scheduled.")
    except Exception as e:
        logger.error("JobQueue scheduling failed: %s", e, exc_info=True)


async def post_shutdown(app: Application):
    logger.info("Jobs shutdown.")