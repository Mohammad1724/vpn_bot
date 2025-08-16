# -*- coding: utf-8 -*-

import asyncio
import logging
import shutil
import os
import sqlite3
from datetime import datetime, timedelta, time, timezone
from types import SimpleNamespace
from telegram.ext import Application, ContextTypes
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError
from telegram import InputFile

import database as db
import hiddify_api
from config import ADMIN_ID
from bot.utils import get_service_status
from bot.handlers.admin.reports import send_daily_summary, send_weekly_summary

logger = logging.getLogger(__name__)

# Global list to hold fallback tasks for clean shutdown
_BG_TASKS = []

# ========== Auto-backup (send DB file to admin) ==========
async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: running auto-backup...")
    base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"auto_backup_{timestamp}.sqlite3"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        # اتصال فعلی را موقتاً می‌بندیم
        db.close_db()

        # با backup API یک کپی امن تهیه می‌کنیم
        with sqlite3.connect(db.DB_NAME) as src, sqlite3.connect(backup_path) as dst:
            src.backup(dst)

        # ارسال فایل به ادمین
        with open(backup_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=InputFile(f, filename=backup_filename),
                caption=f"پشتیبان خودکار دیتابیس - {timestamp}"
            )
    except Exception as e:
        logger.error(f"Auto-backup failed: {e}", exc_info=True)
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ بکاپ خودکار با خطا مواجه شد:\n{e}")
        except Exception:
            pass
    finally:
        # اتصال را دوباره برقرار می‌کنیم
        db.init_db()
        # فایل بکاپ را از سرور حذف نمی‌کنیم تا در پوشه backups باقی بماند

# ========== Low-usage alert ==========
async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    # This function is not fully implemented in the provided code,
    # but the structure is here for future implementation.
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
                    import jdatetime
                    y, m, d = map(int, expiry_jalali.split('/'))
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
        db.delete_service(service['service_id'])
        await context.bot.send_message(
            chat_id=service['user_id'],
            text=f"🗑️ سرویس {f'({service['name']})' if service['name'] else ''} در پنل یافت نشد و از لیست شما حذف شد."
        )
        logger.info("Removed stale service %s (uuid=%s)", service['service_id'], service['sub_uuid'])
    except Exception as e:
        logger.error("Failed to remove stale service %s: %s", service['service_id'], e, exc_info=True)


# ========== Scheduler hooks ==========
async def post_init(app: Application):
    """
    JobQueue داخلی را استارت می‌کند و جاب‌ها را زمان‌بندی می‌کند.
    """
    try:
        from telegram.ext import JobQueue
        jq = JobQueue()
        jq.set_application(app)

        # گزارش‌ها
        if (db.get_setting('daily_report_enabled') or "1") == "1":
            jq.run_daily(send_daily_summary, time=time(hour=23, minute=50))
            logger.info("Daily report job scheduled.")
        if (db.get_setting('weekly_report_enabled') or "1") == "1":
            jq.run_daily(send_weekly_summary, time=time(hour=22, minute=0), days=(4,))  # Friday
            logger.info("Weekly report job scheduled.")

        # بکاپ خودکار
        backup_interval = int(db.get_setting('auto_backup_interval_hours') or 0)
        if backup_interval > 0:
            jq.run_repeating(auto_backup_job, interval=timedelta(hours=backup_interval), first=timedelta(hours=1))
            logger.info(f"Auto-backup job scheduled every {backup_interval} hours.")

        # یادآوری انقضا
        try:
            exp_hour = int(float(db.get_setting("expiry_reminder_hour") or 9))
        except Exception:
            exp_hour = 9
        jq.run_daily(expiry_reminder_job, time=time(hour=exp_hour, minute=0))
        logger.info("Expiry reminder job scheduled at %02d:00", exp_hour)

        jq.start()
        logger.info("Internal JobQueue started and all jobs scheduled.")
    except Exception as e:
        logger.error("JobQueue scheduling failed: %s", e, exc_info=True)


async def post_shutdown(app: Application):
    logger.info("Jobs shutdown.")