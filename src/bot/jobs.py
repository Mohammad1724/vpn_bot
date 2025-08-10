# -*- coding: utf-8 -*-

import asyncio
import logging
import shutil
import os
from datetime import datetime, timedelta, time, timezone
from types import SimpleNamespace
from telegram.ext import Application, ContextTypes
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError

import database as db
import hiddify_api
from config import USAGE_ALERT_THRESHOLD, EXPIRY_REMINDER_DAYS, ADMIN_ID  # EXPIRY_REMINDER_DAYS فقط برای fallback
from bot.utils import get_service_status
from bot.handlers.admin.reports import send_daily_summary, send_weekly_summary

logger = logging.getLogger(__name__)

# Global list to hold fallback tasks for clean shutdown
_BG_TASKS = []

# ========== Auto-backup (send DB file to admin) ==========
async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: running auto-backup...")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"backups/auto_backup_{timestamp}.db"
    try:
        shutil.copy(db.DB_NAME, backup_filename)
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=open(backup_filename, 'rb'),
            caption=f"پشتیبان خودکار دیتابیس - {timestamp}"
        )
    except Exception as e:
        logger.error(f"Auto-backup failed: {e}", exc_info=True)
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ بکاپ خودکار با خطا مواجه شد:\n{e}")
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(backup_filename):
                os.remove(backup_filename)
        except Exception:
            pass

# ========== Low-usage alert ==========
async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: checking low-usage services...")
    services = db.get_all_active_services()
    for service in services:
        if service.get('low_usage_alert_sent'):
            continue
        try:
            info = await hiddify_api.get_user_info(service['sub_uuid'])
            if isinstance(info, dict) and info.get('_not_found'):
                await _remove_stale_service(service, context)
                continue
            if not info:
                continue

            _, _, is_expired = get_service_status(info)
            if is_expired:
                continue

            usage_limit = info.get('usage_limit_GB', 0)
            current_usage = info.get('current_usage_GB', 0)
            if usage_limit > 0 and (current_usage / usage_limit) >= USAGE_ALERT_THRESHOLD:
                try:
                    await context.bot.send_message(
                        chat_id=service['user_id'],
                        text=(
                            f"📢 هشدار مصرف!\n\n"
                            f"بیش از {int(USAGE_ALERT_THRESHOLD * 100)}٪ از حجم سرویس "
                            f"{f'({service['name']})' if service['name'] else ''} مصرف شده است.\n"
                            f"({current_usage:.2f} گیگ از {usage_limit:.0f} گیگ)\n\n"
                            "برای جلوگیری از قطعی، لطفاً سرویس خود را تمدید نمایید."
                        )
                    )
                    db.set_low_usage_alert_sent(service['service_id'])
                except (Forbidden, BadRequest) as e:
                    logger.warning("Low-usage alert send failed: %s", e)
                await asyncio.sleep(0.2)
        except Exception as e:
            logger.error("Low-usage job error: %s", e, exc_info=True)

# ========== Expiry reminder (settings-driven) ==========
async def expiry_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """
    ارسال یادآوری انقضا بر اساس تنظیمات:
    - expiry_reminder_enabled (on/off)
    - expiry_reminder_days (threshold)
    - expiry_reminder_message (template with {days} & {service_name})
    برای جلوگیری از ارسال تکراری، در جدول reminder_log ثبت می‌شود.
    """
    try:
        enabled = db.get_setting("expiry_reminder_enabled")
        if str(enabled).lower() in ("0", "false", "off"):
            return

        try:
            days_threshold = int(float(db.get_setting("expiry_reminder_days") or 3))
        except Exception:
            # fallback به config اگر key در settings نبود
            days_threshold = EXPIRY_REMINDER_DAYS if isinstance(EXPIRY_REMINDER_DAYS, int) else 3

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

                # تبدیل تاریخ جلالی به میلادی و محاسبه روز باقی‌مانده
                try:
                    import jdatetime
                    y, m, d = map(int, expiry_jalali.split('/'))
                    jalali_date = jdatetime.date(y, m, d)
                    gregorian_expiry = jalali_date.togregorian()
                    days_left = (gregorian_expiry - datetime.now().date()).days
                except Exception:
                    # اگر نشد، ارسال نکنیم
                    continue

                if days_left <= 0 or days_left > days_threshold:
                    continue

                # جلوگیری از ارسال تکراری در یک روز
                if db.was_reminder_sent(svc["service_id"], "expiry", today):
                    continue

                text = template.format(days=days_left, service_name=(svc.get("name") or "سرویس"))
                try:
                    await context.bot.send_message(chat_id=svc["user_id"], text=text)
                    db.mark_reminder_sent(svc["service_id"], "expiry", today)
                except RetryAfter as e:
                    # تلاش مجدد کوتاه (اختیاری)
                    await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
                    try:
                        await context.bot.send_message(chat_id=svc["user_id"], text=text)
                        db.mark_reminder_sent(svc["service_id"], "expiry", today)
                    except Exception:
                        pass
                except (Forbidden, BadRequest, TimedOut, NetworkError):
                    # move on
                    pass

                await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug("expiry check for service %s failed: %s", svc.get("service_id"), e)

    except Exception as e:
        logger.error("expiry_reminder_job error: %s", e, exc_info=True)

# سازگاری با کد قدیمی: اگر جایی check_expiring_services صدا زده می‌شد
async def check_expiring_services(context: ContextTypes.DEFAULT_TYPE):
    await expiry_reminder_job(context)

# ========== Helpers ==========
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

# ========== Fallback loops (when JobQueue is unavailable) ==========
async def _low_usage_loop(app: Application, interval_s: int = 4 * 60 * 60):
    ctx = SimpleNamespace(bot=app.bot)
    try:
        while not _STOP_EVENT.is_set():
            await check_low_usage(ctx)
            try:
                await asyncio.wait_for(_STOP_EVENT.wait(), timeout=interval_s)
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        pass

async def _daily_expiry_loop(app: Application, hour: int = 9, minute: int = 0):
    try:
        while not _STOP_EVENT.is_set():
            now = datetime.now()
            target = datetime.combine(now.date(), time(hour, minute))
            if now >= target:
                target += timedelta(days=1)
            wait_sec = (target - now).total_seconds()
            try:
                await asyncio.wait_for(_STOP_EVENT.wait(), timeout=wait_sec)
            except asyncio.TimeoutError:
                ctx = SimpleNamespace(bot=app.bot)
                try:
                    await expiry_reminder_job(ctx)
                except Exception:
                    logger.exception("Error running expiry reminder")
    except asyncio.CancelledError:
        pass

# ========== Scheduler hooks ==========
async def post_init(app: Application):
    """
    JobQueue داخلی را استارت می‌کند و جاب‌ها را زمان‌بندی می‌کند.
    """
    try:
        from telegram.ext import JobQueue
        jq = JobQueue()
        jq.set_application(app)

        # Low-usage هر 4 ساعت
        jq.run_repeating(check_low_usage, interval=timedelta(hours=4), first=10)

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

        # یادآوری انقضا روزانه در ساعت تنظیم‌شده
        try:
            exp_hour = int(float(db.get_setting("expiry_reminder_hour") or 9))
        except Exception:
            exp_hour = 9
        jq.run_daily(expiry_reminder_job, time=time(hour=exp_hour, minute=0))
        logger.info("Expiry reminder job scheduled at %02d:00", exp_hour)

        jq.start()
        logger.info("Internal JobQueue started and all jobs scheduled.")
        return
    except Exception as e:
        logger.info("JobQueue not available (%s). Falling back to asyncio loops.", e)

    # Fallback به حلقه‌های asyncio
    global _STOP_EVENT
    _STOP_EVENT = asyncio.Event()
    loop = asyncio.get_event_loop()
    _BG_TASKS.clear()
    _BG_TASKS.append(loop.create_task(_low_usage_loop(app)))
    # ساعت fallback را از settings بخوانیم
    try:
        exp_hour = int(float(db.get_setting("expiry_reminder_hour") or 9))
    except Exception:
        exp_hour = 9
    _BG_TASKS.append(loop.create_task(_daily_expiry_loop(app, hour=exp_hour, minute=0)))

async def post_shutdown(app: Application):
    if not _BG_TASKS:
        return
    _STOP_EVENT.set()
    for t in _BG_TASKS:
        t.cancel()
    try:
        await asyncio.gather(*_BG_TASKS, return_exceptions=True)
    finally:
        _BG_TASKS.clear()