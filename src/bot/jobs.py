# filename: bot/jobs.py
# -*- coding: utf-8 -*-

import asyncio
import logging
import shutil
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, time
from telegram.ext import Application, ContextTypes
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError
from telegram import InputFile

import database as db
import hiddify_api
from config import ADMIN_ID
from bot.utils import get_service_status
from bot.handlers.admin.reports import send_daily_summary, send_weekly_summary

# Optional usage aggregation configs (fallback if not present)
try:
    from config import USAGE_AGGREGATION_ENABLED, USAGE_UPDATE_INTERVAL_MIN
except Exception:
    USAGE_AGGREGATION_ENABLED = False
    USAGE_UPDATE_INTERVAL_MIN = 10

logger = logging.getLogger(__name__)

# -------------------- Auto-backup --------------------
async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: running auto-backup...")

    base_dir = os.path.dirname(os.path.abspath(db.DB_NAME))
    backup_dir = os.path.join(base_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"auto_backup_{timestamp}.sqlite3"
    backup_path = os.path.join(backup_dir, backup_filename)

    manage_old_backups(backup_dir)
    target_chat_id = db.get_setting("backup_target_chat_id") or ADMIN_ID

    db_closed = False
    try:
        db.close_db()
        db_closed = True

        try:
            # Prefer VACUUM INTO (SQLite >= 3.27)
            version = sqlite3.sqlite_version_info
            if version >= (3, 27, 0):
                path_escaped = backup_path.replace("'", "''")
                with sqlite3.connect(db.DB_NAME) as conn:
                    conn.execute(f"VACUUM INTO '{path_escaped}'")
                logger.info("Auto-backup: VACUUM INTO succeeded")
            else:
                # backup() API for older SQLite
                with sqlite3.connect(db.DB_NAME) as src, sqlite3.connect(backup_path) as dst:
                    src.backup(dst)
                logger.info("Auto-backup: backup() API succeeded")
        except Exception as e:
            logger.error("SQLite backup methods failed (%s). Falling back to file copy.", e, exc_info=True)
            try:
                with sqlite3.connect(db.DB_NAME) as conn:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            shutil.copy2(db.DB_NAME, backup_path)
            for ext in ("-wal", "-shm"):
                sp = db.DB_NAME + ext
                if os.path.exists(sp):
                    try:
                        shutil.copy2(sp, backup_path + ext)
                    except Exception:
                        pass
            logger.info("Auto-backup: file copy succeeded")

        # Send file
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


def manage_old_backups(backup_dir: str, max_backups: int = 10):
    try:
        files = [f for f in os.listdir(backup_dir) if f.startswith("auto_backup_") and f.endswith(".sqlite3")]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
        if len(files) > max_backups:
            for old in files[:-max_backups]:
                os.remove(os.path.join(backup_dir, old))
                logger.info("Removed old backup file: %s", old)
    except Exception as e:
        logger.error("Error managing old backups: %s", e, exc_info=True)


# -------------------- Low usage placeholder --------------------
async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: checking low-usage services... (not implemented)")


# -------------------- Helpers --------------------
def _extract_usage_gb(payload: dict) -> float | None:
    if not isinstance(payload, dict):
        return None
    for k in ("current_usage_GB", "usage_GB", "used_GB"):
        if k in payload:
            try:
                return float(payload[k])
            except Exception:
                return None
    return None


# -------------------- Expiry reminder --------------------
_P2E = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

def _norm_digits(s: str) -> str:
    return (s or "").translate(_P2E)

def _days_left_from_jalali(expiry_jalali: str) -> int | None:
    if not expiry_jalali or expiry_jalali in ("N/A", "نامشخص"):
        return None
    try:
        import jdatetime
        s = _norm_digits(expiry_jalali).replace("-", "/").strip()
        y, m, d = map(int, s.split("/")[:3])
        g = jdatetime.date(y, m, d).togregorian()
        return (g - datetime.now().date()).days
    except Exception:
        return None

async def expiry_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        if str(db.get_setting("expiry_reminder_enabled")).lower() in ("0", "false", "off"):
            return

        try:
            days_threshold = int(float(db.get_setting("expiry_reminder_days") or 3))
        except Exception:
            days_threshold = 3
        if days_threshold <= 0:
            days_threshold = None

        # Optional GB threshold
        def _get_first_num(keys: list[str]):
            for k in keys:
                try:
                    v = db.get_setting(k)
                    if v is None or str(v).strip() == "":
                        continue
                    num = float(v)
                    if num > 0:
                        return num
                except Exception:
                    continue
            return None

        gb_threshold = _get_first_num([
            "expiry_reminder_gb",
            "expiry_gb_threshold",
            "expiry_low_gb",
            "low_usage_threshold_gb",
            "usage_reminder_gb",
            "reminder_gb_threshold",
        ])

        template_days = db.get_setting("expiry_reminder_message") or (
            "⏰ سرویس «{service_name}» شما {days} روز دیگر منقضی می‌شود.\n"
            "برای جلوگیری از قطع، از «📋 سرویس‌های من» تمدید کنید."
        )
        template_gb = db.get_setting("expiry_reminder_gb_message") or (
            "⚠️ حجم باقیمانده سرویس «{service_name}» کمتر از {gb} گیگابایت است "
            "(باقی‌مانده: {gb_left} گیگابایت).\n"
            "برای جلوگیری از قطع، لطفاً شارژ یا تمدید کنید."
        )

        services = db.get_all_active_services()
        today = datetime.now().strftime("%Y-%m-%d")

        for svc in services:
            try:
                info = await hiddify_api.get_user_info(svc["sub_uuid"])
                if isinstance(info, dict) and info.get("_not_found"):
                    await _remove_stale_service(svc, context)
                    continue
                if not info:
                    continue

                # از رکورد DB برای محاسبه دقیق انقضا استفاده می‌کنیم
                status, expiry_jalali, is_expired = get_service_status(info, svc)
                if is_expired or not expiry_jalali or expiry_jalali == "N/A":
                    continue

                sent = False

                if days_threshold is not None:
                    days_left = _days_left_from_jalali(expiry_jalali)
                    if (days_left is not None) and (0 < days_left <= days_threshold):
                        if not (db.was_reminder_sent(svc["service_id"], "expiry_days", today) or
                                db.was_reminder_sent(svc["service_id"], "expiry", today)):
                            text = template_days.format(days=days_left, service_name=(svc.get("name") or "سرویس"))
                            try:
                                await context.bot.send_message(chat_id=svc["user_id"], text=text)
                                db.mark_reminder_sent(svc["service_id"], "expiry_days", today)
                                db.mark_reminder_sent(svc["service_id"], "expiry", today)
                                sent = True
                            except RetryAfter as e:
                                await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
                                await context.bot.send_message(chat_id=svc["user_id"], text=text)
                                db.mark_reminder_sent(svc["service_id"], "expiry_days", today)
                                db.mark_reminder_sent(svc["service_id"], "expiry", today)
                                sent = True
                            except (Forbidden, BadRequest, TimedOut, NetworkError):
                                pass

                if (gb_threshold is not None) and (not sent):
                    try:
                        u_limit = float(info.get("usage_limit_GB"))
                    except Exception:
                        u_limit = None
                    if (u_limit is not None) and (u_limit > 0):
                        used = _extract_usage_gb(info)
                        if used is not None:
                            rem = max(0.0, u_limit - float(used))
                            if rem <= float(gb_threshold):
                                if not db.was_reminder_sent(svc["service_id"], "expiry_gb", today):
                                    text = template_gb.format(
                                        service_name=(svc.get("name") or "سرویس"),
                                        gb=float(gb_threshold),
                                        gb_left=f"{rem:.2f}".rstrip("0").rstrip(".")
                                    )
                                    try:
                                        await context.bot.send_message(chat_id=svc["user_id"], text=text)
                                        db.mark_reminder_sent(svc["service_id"], "expiry_gb", today)
                                    except RetryAfter as e:
                                        await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
                                        await context.bot.send_message(chat_id=svc["user_id"], text=text)
                                        db.mark_reminder_sent(svc["service_id"], "expiry_gb", today)
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


# -------------------- Usage aggregation --------------------
async def update_user_usage_snapshot(context: ContextTypes.DEFAULT_TYPE):
    try:
        base_services = db.get_all_active_services() or []
        endpoints = db.list_all_endpoints_with_user() or []

        tasks = []
        sem = asyncio.Semaphore(8)

        async def fetch_usage(user_id: int, sub_uuid: str, server_name: str):
            async with sem:
                if not sub_uuid:
                    return None
                try:
                    info = await hiddify_api.get_user_info(sub_uuid)
                    if not info or (isinstance(info, dict) and info.get("_not_found")):
                        return None
                    usage = _extract_usage_gb(info)
                    if usage is None:
                        return None
                    return (user_id, server_name or "Unknown", float(usage))
                except Exception:
                    return None

        for s in base_services:
            tasks.append(fetch_usage(s["user_id"], s["sub_uuid"], s.get("server_name") or "Unknown"))
        for ep in endpoints:
            tasks.append(fetch_usage(ep["user_id"], ep.get("sub_uuid"), ep.get("server_name") or "Unknown"))

        if not tasks:
            return

        results = await asyncio.gather(*tasks, return_exceptions=False)

        agg = defaultdict(float)
        seen_by_user = defaultdict(set)
        for r in results:
            if not r:
                continue
            uid, srv, usage = r
            agg[(uid, srv)] += usage
            seen_by_user[uid].add(srv)

        for (uid, srv), total in agg.items():
            db.upsert_user_traffic(uid, srv, total)

        try:
            interval_min = int(db.get_setting("usage_update_interval_min") or USAGE_UPDATE_INTERVAL_MIN or 10)
        except Exception:
            interval_min = USAGE_UPDATE_INTERVAL_MIN or 10
        cleanup_after = max(2 * int(interval_min), 15)

        for uid, servers in seen_by_user.items():
            try:
                db.delete_user_traffic_not_in_and_older(
                    user_id=uid,
                    allowed_servers=list(servers),
                    older_than_minutes=cleanup_after,
                    also_delete_unknown=True
                )
            except Exception as e:
                logger.debug("cleanup user_traffic failed for user %s: %s", uid, e)

        logger.info("Usage snapshot updated: %d pairs; cleaned older than %d minutes.",
                    len(agg), cleanup_after)

    except Exception as e:
        logger.error("update_user_usage_snapshot failed: %s", e, exc_info=True)


# -------------------- One-time Backfill --------------------
async def initial_backfill_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        updated = db.backfill_active_services_server_names()
        if updated:
            logger.info("Initial backfill: updated server_name for %d services.", updated)
    except Exception as e:
        logger.error("Initial backfill failed: %s", e, exc_info=True)


# -------------------- Scheduler hooks (REQUIRED by app.py) --------------------
def _is_on(keys: list[str], default: str = "0") -> bool:
    for k in keys:
        v = db.get_setting(k)
        if v is not None and str(v).lower() in ("1", "true", "on", "yes"):
            return True
    return str(default).lower() in ("1", "true", "on", "yes")


async def post_init(app: Application):
    """
    Called by ApplicationBuilder.post_init in app.py
    """
    try:
        jq = app.job_queue

        # One-time backfill
        jq.run_once(initial_backfill_job, when=timedelta(seconds=2), name="initial_backfill")

        # Reports
        if _is_on(["report_daily_enabled", "daily_report_enabled"], default="0"):
            jq.run_daily(send_daily_summary, time=time(hour=23, minute=50), name="daily_report")
            logger.info("Daily report job scheduled.")
        if _is_on(["report_weekly_enabled", "weekly_report_enabled"], default="0"):
            jq.run_daily(send_weekly_summary, time=time(hour=22, minute=0), days=(4,), name="weekly_report")
            logger.info("Weekly report job scheduled.")

        # Auto-backup
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

        # Expiry reminder
        try:
            exp_hour = int(float(db.get_setting("expiry_reminder_hour") or 9))
        except Exception:
            exp_hour = 9
        if _is_on(["expiry_reminder_enabled"], default="1"):
            jq.run_daily(expiry_reminder_job, time=time(hour=exp_hour, minute=0), name="expiry_reminder")
            logger.info("Expiry reminder job scheduled at %02d:00", exp_hour)

        # Usage aggregation
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

        logger.info("JobQueue: jobs scheduled.")
    except Exception as e:
        logger.error("JobQueue scheduling failed: %s", e, exc_info=True)


async def post_shutdown(app: Application):
    """
    Called by ApplicationBuilder.post_shutdown in app.py
    """
    logger.info("Jobs shutdown.")