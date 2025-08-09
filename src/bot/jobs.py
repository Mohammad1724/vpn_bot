# -*- coding: utf-8 -*-

import asyncio
import logging
import shutil
import os
from datetime import datetime, timedelta, time
from types import SimpleNamespace
from telegram.ext import Application, ContextTypes
from telegram.error import Forbidden, BadRequest

import database as db
import hiddify_api
from config import USAGE_ALERT_THRESHOLD, EXPIRY_REMINDER_DAYS, ADMIN_ID
from bot.utils import get_service_status
from bot.handlers.admin.reports import send_daily_summary, send_weekly_summary

logger = logging.getLogger(__name__)

# Global list to hold fallback tasks for clean shutdown
_BG_TASKS = []

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
            pass # Avoid error loops if bot can't send message to admin
    finally:
        if os.path.exists(backup_filename):
            os.remove(backup_filename)

async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: checking low-usage services...")
    for service in db.get_all_active_services():
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
                await context.bot.send_message(
                    chat_id=service['user_id'],
                    text=(
                        f"📢 هشدار اتمام حجم!\n\n"
                        f"کاربر گرامی، بیش از {int(USAGE_ALERT_THRESHOLD * 100)}٪ از حجم سرویس شما "
                        f"{f'({service['name']})' if service['name'] else ''} مصرف شده است.\n"
                        f"({current_usage:.2f} گیگ از {usage_limit:.0f} گیگ)\n\n"
                        "برای جلوگیری از قطعی، لطفاً سرویس خود را تمدید نمایید."
                    )
                )
                db.set_low_usage_alert_sent(service['service_id'])
                await asyncio.sleep(0.2)
        except (Forbidden, BadRequest) as e:
            logger.warning("Low-usage alert send failed: %s", e)
        except Exception as e:
            logger.error("Low-usage job error: %s", e, exc_info=True)

async def check_expiring_services(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: checking expiring services...")
    for service in db.get_all_active_services():
        try:
            info = await hiddify_api.get_user_info(service['sub_uuid'])
            if isinstance(info, dict) and info.get('_not_found'):
                await _remove_stale_service(service, context)
                continue
            if not info:
                continue

            _, expiry_date_str, is_expired = get_service_status(info)
            if is_expired or expiry_date_str == "N/A":
                continue

            y, m, d = map(int, expiry_date_str.split('/'))
            import jdatetime
            jalali_date = jdatetime.date(y, m, d)
            gregorian_expiry = jalali_date.togregorian()
            days_left = (gregorian_expiry - datetime.now().date()).days

            if days_left == EXPIRY_REMINDER_DAYS:
                await context.bot.send_message(
                    chat_id=service['user_id'],
                    text=(
                        f"⏳ یادآوری انقضای سرویس\n\n"
                        f"{days_left} روز تا پایان اعتبار سرویس {f'({service['name']})' if service['name'] else ''} باقی مانده است.\n\n"
                        "برای جلوگیری از قطعی، لطفاً سرویس خود را تمدید نمایید."
                    )
                )
                await asyncio.sleep(0.2)
        except (Forbidden, BadRequest) as e:
            logger.warning("Expiry reminder send failed: %s", e)
        except Exception as e:
            logger.error("Expiry job error: %s", e, exc_info=True)

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

# Fallback loops (when JobQueue is unavailable)
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
                    await check_expiring_services(ctx)
                except Exception:
                    logger.exception("Error running expiry check")
    except asyncio.CancelledError:
        pass

async def post_init(app: Application):
    try:
        from telegram.ext import JobQueue
        jq = JobQueue()
        jq.set_application(app)

        jq.run_repeating(check_low_usage, interval=timedelta(hours=4), first=10)
        
        if db.get_setting('daily_report_enabled') == '1':
            jq.run_daily(send_daily_summary, time=time(hour=23, minute=50))
            logger.info("Daily report job scheduled.")
        if db.get_setting('weekly_report_enabled') == '1':
            jq.run_daily(send_weekly_summary, time=time(hour=22, minute=0), days=(4,)) # Friday
            logger.info("Weekly report job scheduled.")
            
        backup_interval = int(db.get_setting('auto_backup_interval_hours') or 0)
        if backup_interval > 0:
            jq.run_repeating(auto_backup_job, interval=timedelta(hours=backup_interval), first=timedelta(hours=1))
            logger.info(f"Auto-backup job scheduled every {backup_interval} hours.")

        jq.start()
        logger.info("Internal JobQueue started and all jobs scheduled.")
        return
    except Exception as e:
        logger.info("JobQueue not available (%s). Falling back to asyncio loops.", e)

    global _STOP_EVENT
    _STOP_EVENT = asyncio.Event()
    loop = asyncio.get_event_loop()
    _BG_TASKS.clear()
    _BG_TASKS.append(loop.create_task(_low_usage_loop(app)))
    _BG_TASKS.append(loop.create_task(_daily_expiry_loop(app)))

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