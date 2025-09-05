# -*- coding: utf-8 -*-

import asyncio
import logging
import shutil
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, time, timezone
from telegram.ext import Application, ContextTypes
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError
from telegram import InputFile

import database as db
import hiddify_api
from config import ADMIN_ID
from bot.utils import get_service_status
from bot.handlers.admin.reports import send_daily_summary, send_weekly_summary

# Optional usage aggregation configs
try:
    from config import USAGE_AGGREGATION_ENABLED, USAGE_UPDATE_INTERVAL_MIN
except Exception:
    USAGE_AGGREGATION_ENABLED = False
    USAGE_UPDATE_INTERVAL_MIN = 10

# Optional node health-check configs
try:
    from config import NODES_HEALTH_ENABLED, NODES_HEALTH_INTERVAL_MIN, NODES_AUTO_DISABLE_AFTER_FAILS
except Exception:
    NODES_HEALTH_ENABLED = True
    NODES_HEALTH_INTERVAL_MIN = 10
    NODES_AUTO_DISABLE_AFTER_FAILS = 3

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
            "برای جلوگیری از قطع، از «📋 سرویس‌های من» تمدید کنید."
        )

        services = db.get_all_active_services()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for svc in services:
            try:
                info = await hiddify_api.get_user_info(svc["sub_uuid"], server_name=svc.get("server_name"))
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


# ========== Usage aggregation across servers (+ endpoints for Subconverter) ==========
async def update_user_usage_snapshot(context: ContextTypes.DEFAULT_TYPE):
    """
    برای هر سرویس فعال، مصرف را از پنل مربوطه خوانده و
    مجموع مصرف هر کاربر را به تفکیک سرور به‌روزرسانی می‌کند.
    - شامل service_endpoints نیز می‌شود (برای حالت Subconverter/چندنودی)
    """
    try:
        base_services = db.get_all_active_services() or []
        endpoints = db.list_all_endpoints_with_user() or []

        # Normalize both lists into unified tasks: (user_id, sub_uuid, server_name)
        tasks_data = []
        for s in base_services:
            tasks_data.append((s["user_id"], s.get("server_name") or "Unknown", s["sub_uuid"]))
        for ep in endpoints:
            tasks_data.append((ep["user_id"], ep.get("server_name") or "Unknown", ep.get("sub_uuid")))

        if not tasks_data:
            return

        # Concurrency control
        sem = asyncio.Semaphore(8)

        async def fetch_usage(user_id: int, server_name: str, sub_uuid: str):
            async with sem:
                if not sub_uuid:
                    return None
                try:
                    usage = await hiddify_api.get_user_usage_gb(sub_uuid, server_name=server_name)
                    if usage is None:
                        return None
                    return (user_id, server_name or "Unknown", float(usage))
                except Exception:
                    return None

        coros = [fetch_usage(uid, srv, uuid) for (uid, srv, uuid) in tasks_data]
        results = await asyncio.gather(*coros, return_exceptions=False)

        # Aggregate per (user_id, server_name) and collect seen servers per user
        agg = defaultdict(float)
        seen_servers_by_user = defaultdict(set)
        for r in results:
            if not r:
                continue
            uid, srv, usage = r
            agg[(uid, srv)] += usage
            seen_servers_by_user[uid].add(srv)

        # Upsert into DB
        for (uid, srv), total_usage in agg.items():
            db.upsert_user_traffic(uid, srv, total_usage)

        # Cleanup old/stale user_traffic entries per user
        try:
            interval_min = int(db.get_setting("usage_update_interval_min") or USAGE_UPDATE_INTERVAL_MIN or 10)
        except Exception:
            interval_min = USAGE_UPDATE_INTERVAL_MIN or 10
        cleanup_after_min = max(2 * int(interval_min), 15)

        for uid, servers in seen_servers_by_user.items():
            try:
                db.delete_user_traffic_not_in_and_older(
                    user_id=uid,
                    allowed_servers=list(servers),
                    older_than_minutes=cleanup_after_min,
                    also_delete_unknown=True
                )
            except Exception as e:
                logger.debug("cleanup user_traffic failed for user %s: %s", uid, e)

        logger.info("Usage snapshot updated: %d user-server pairs; cleaned older than %d minutes.",
                    len(agg), cleanup_after_min)

    except Exception as e:
        logger.error("update_user_usage_snapshot failed: %s", e, exc_info=True)


# ========== Node health-check and live user count ==========
async def node_health_job(context: ContextTypes.DEFAULT_TYPE):
    """
    - هلس‌چک نودهای فعال (DB یا config)، با استفاده از hiddify_api.check_api_connection
    - بروزرسانی current_users هر نود از روی active_services
    - اختیاری: در صورت چند خطای متوالی، نود به‌صورت خودکار غیرفعال می‌شود و به ادمین اطلاع داده می‌شود.
    """
    try:
        nodes = db.list_nodes()  # همه‌ی نودها (فعال/غیرفعال)
        if not nodes:
            return

        # تنظیمات از DB یا config
        try:
            auto_disable_after = int(db.get_setting("nodes_auto_disable_after_fails") or NODES_AUTO_DISABLE_AFTER_FAILS)
        except Exception:
            auto_disable_after = NODES_AUTO_DISABLE_AFTER_FAILS

        bot_data = context.application.bot_data.setdefault("node_failures", {})
        sem = asyncio.Semaphore(6)

        async def check_node(n: dict):
            if str(n.get("panel_type", "hiddify")).lower() != "hiddify":
                return  # فعلاً فقط هیدیفای
            name = n["name"]
            node_id = n["id"]

            async with sem:
                ok = False
                try:
                    ok = await hiddify_api.check_api_connection(server_name=name)
                except Exception:
                    ok = False

                # به‌روزرسانی شمار کاربران زنده روی این نود
                try:
                    cnt = db.count_services_on_node(name)
                    db.update_node(node_id, {"current_users": int(cnt)})
                except Exception:
                    pass

                # مدیریت خطاهای متوالی و غیرفعال‌سازی خودکار
                try:
                    fails = int(bot_data.get(name, 0))
                except Exception:
                    fails = 0

                if ok:
                    if fails:
                        bot_data[name] = 0
                else:
                    fails += 1
                    bot_data[name] = fails
                    if fails >= auto_disable_after and int(n.get("is_active", 1)) == 1:
                        try:
                            db.update_node(node_id, {"is_active": 0})
                            await context.bot.send_message(
                                chat_id=ADMIN_ID,
                                text=f"⚠️ نود «{name}» به دلیل {fails} خطای متوالی در health-check غیرفعال شد."
                            )
                            logger.warning("Node %s auto-disabled after %d fails.", name, fails)
                        except Exception as e:
                            logger.error("Failed to auto-disable node %s: %s", name, e)

        await asyncio.gather(*(check_node(n) for n in nodes))

    except Exception as e:
        logger.error("node_health_job failed: %s", e, exc_info=True)


# ========== One-time Backfill ==========
async def initial_backfill_job(context: ContextTypes.DEFAULT_TYPE):
    """
    یک‌بار پس از استارت: server_name سرویس‌های فاقد مقدار را از روی لینک و جدول نودها پر می‌کند.
    """
    try:
        updated = db.backfill_active_services_server_names()
        if updated:
            logger.info("Initial backfill: updated server_name for %d services.", updated)
    except Exception as e:
        logger.error("Initial backfill failed: %s", e, exc_info=True)


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

        # Backfill یک‌باره‌ی server_name سرویس‌های قدیمی
        jq.run_once(initial_backfill_job, when=timedelta(seconds=2), name="initial_backfill")

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

        # Usage aggregation job
        if _is_on(["usage_aggregation_enabled"], default="1" if USAGE_AGGREGATION_ENABLED else "0"):
            try:
                interval_min = int(db.get_setting("usage_update_interval_min") or USAGE_UPDATE_INTERVAL_MIN or 10)
            except Exception:
                interval_min = USAGE_UPDATE_INTERVAL_MIN or 10
            jq.run_repeating(
                update_user_usage_snapshot,
                interval=timedelta(minutes=interval_min),
                first=timedelta(minutes=1),
                name="usage_aggregation_job",
            )
            logger.info("Usage aggregation job scheduled every %d minutes.", interval_min)

        # Node health-check job
        if _is_on(["nodes_health_enabled"], default="1" if NODES_HEALTH_ENABLED else "0"):
            try:
                nh_interval = int(db.get_setting("nodes_health_interval_min") or NODES_HEALTH_INTERVAL_MIN or 10)
            except Exception:
                nh_interval = NODES_HEALTH_INTERVAL_MIN or 10
            jq.run_repeating(
                node_health_job,
                interval=timedelta(minutes=nh_interval),
                first=timedelta(minutes=1),
                name="node_health_job",
            )
            logger.info("Node health-check job scheduled every %d minutes.", nh_interval)

        logger.info("JobQueue: jobs scheduled.")
    except Exception as e:
        logger.error("JobQueue scheduling failed: %s", e, exc_info=True)


async def post_shutdown(app: Application):
    logger.info("Jobs shutdown.")