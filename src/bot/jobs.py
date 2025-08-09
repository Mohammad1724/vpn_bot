# -*- coding: utf-8 -*-

import asyncio
import logging
from datetime import datetime, timedelta, time
from types import SimpleNamespace
from telegram.ext import Application, ContextTypes
from telegram.error import Forbidden, BadRequest

import database as db
import hiddify_api
from config import USAGE_ALERT_THRESHOLD, EXPIRY_REMINDER_DAYS
from bot.utils import get_service_status

logger = logging.getLogger(__name__)

async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: checking low-usage services...")
    for service in db.get_all_active_services():
        if service.get('low_usage_alert_sent'):
            continue
        try:
            info = await hiddify_api.get_user_info(service['sub_uuid'])
            # Auto-clean if 404 sentinel returned
            if isinstance(info, dict) and info.get('_not_found'):
                _remove_stale_service(service, context)
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
                _remove_stale_service(service, context)
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

def _remove_stale_service(service: dict, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = db._connect_db()
        conn.execute("DELETE FROM active_services WHERE service_id = ?", (service['service_id'],))
        conn.commit()
        # Notify user
        asyncio.create_task(context.bot.send_message(
            chat_id=service['user_id'],
            text=f"🗑️ سرویس {f'({service['name']})' if service['name'] else ''} در پنل یافت نشد و از لیست شما حذف شد."
        ))
        logger.info("Removed stale service %s (uuid=%s)", service['service_id'], service['sub_uuid'])
    except Exception as e:
        logger.error("Failed to remove stale service %s: %s", service['service_id'], e, exc_info=True)

# Fallback loops (when JobQueue is unavailable)
async def _low_usage_loop(app: Application, interval_s: int = 4 * 60 * 60):
    ctx = SimpleNamespace(bot=app.bot)
    while True:
        try:
            await check_low_usage(ctx)
        except Exception:
            logger.exception("Error in _low_usage_loop")
        await asyncio.sleep(interval_s)

async def _daily_expiry_loop(app: Application, hour: int = 9, minute: int = 0):
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), time(hour, minute))
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        ctx = SimpleNamespace(bot=app.bot)
        try:
            await check_expiring_services(ctx)
        except Exception:
            logger.exception("Error in _daily_expiry_loop")

async def post_init(app: Application):
    # Avoid touching app.job_queue to prevent PTBUserWarning
    job_queue_available = False
    try:
        from telegram.ext import JobQueue  # noqa: F401
        job_queue_available = True
    except Exception:
        job_queue_available = False

    if job_queue_available:
        jq = app.job_queue  # will not warn since JobQueue is available
        if jq:
            jq.run_repeating(check_low_usage, interval=timedelta(hours=4), first=10)
            jq.run_daily(check_expiring_services, time=time(hour=9, minute=0))
            return

    # Fallback without warnings
    loop = asyncio.get_event_loop()
    loop.create_task(_low_usage_loop(app))
    loop.create_task(_daily_expiry_loop(app))