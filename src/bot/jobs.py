# filename: bot/jobs.py
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

logger = logging.getLogger(__name__)

# ... (بخش‌های دیگر بدون تغییر همان نسخه‌ای است که قبلا فرستادم) ...

# Helper: extract usage GB from user info payload
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

# تبدیل ارقام فارسی برای روزها در یادآور
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

def _normalize_digits(s: str) -> str:
    try:
        return str(s).translate(_PERSIAN_DIGITS)
    except Exception:
        return str(s)

def _compute_days_left_from_jalali(expiry_jalali: str) -> int | None:
    if not expiry_jalali or expiry_jalali in ("N/A", "نامشخص"):
        return None
    try:
        import jdatetime
    except Exception:
        return None
    try:
        s = _normalize_digits(expiry_jalali).replace("-", "/").strip()
        parts = [int(p) for p in s.split("/")[:3]]
        if len(parts) != 3:
            return None
        y, m, d = parts
        jalali_date = jdatetime.date(y, m, d)
        gregorian_expiry = jalali_date.togregorian()
        days_left = (gregorian_expiry - datetime.now().date()).days
        return days_left
    except Exception:
        return None

# ========== Expiry reminder (settings-driven) ==========
async def expiry_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """
    ارسال یادآوری انقضا:
      - بر اساس روزهای باقی‌مانده (expiry_reminder_days)
      - بر اساس حجم باقیمانده (expiry_reminder_gb و کلیدهای مشابه)
    """
    try:
        enabled = db.get_setting("expiry_reminder_enabled")
        if str(enabled).lower() in ("0", "false", "off"):
            return

        try:
            days_threshold = int(float(db.get_setting("expiry_reminder_days") or 3))
        except Exception:
            days_threshold = 3
        if days_threshold <= 0:
            days_threshold = None

        # آستانه GB (اولین کلید معتبر)
        def _get_first_number_setting(keys: list[str], cast=float):
            for k in keys:
                try:
                    v = db.get_setting(k)
                    if v is None or str(v).strip() == "":
                        continue
                    num = cast(float(v)) if cast is int else cast(v)
                    if float(num) <= 0:
                        continue
                    return num
                except Exception:
                    continue
            return None

        gb_threshold = _get_first_number_setting(
            keys=[
                "expiry_reminder_gb",
                "expiry_gb_threshold",
                "expiry_low_gb",
                "low_usage_threshold_gb",
                "usage_reminder_gb",
                "reminder_gb_threshold",
            ],
            cast=float
        )

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

                # پاس دادن رکورد سرویس به get_service_status تا از created_at تازه استفاده شود
                status, expiry_jalali, is_expired = get_service_status(info, svc)
                if is_expired or not expiry_jalali or expiry_jalali == "N/A":
                    continue

                days_left = _compute_days_left_from_jalali(expiry_jalali)

                name = svc.get("name") or "سرویس"
                sent_this_service = False

                if days_threshold and days_left is not None and 0 < days_left <= int(days_threshold):
                    already_sent = db.was_reminder_sent(svc["service_id"], "expiry_days", today) or \
                                   db.was_reminder_sent(svc["service_id"], "expiry", today)
                    if not already_sent:
                        text = template_days.format(days=days_left, service_name=name)
                        try:
                            await context.bot.send_message(chat_id=svc["user_id"], text=text)
                            db.mark_reminder_sent(svc["service_id"], "expiry_days", today)
                            db.mark_reminder_sent(svc["service_id"], "expiry", today)
                            sent_this_service = True
                        except RetryAfter as e:
                            await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
                            await context.bot.send_message(chat_id=svc["user_id"], text=text)
                            db.mark_reminder_sent(svc["service_id"], "expiry_days", today)
                            db.mark_reminder_sent(svc["service_id"], "expiry", today)
                            sent_this_service = True
                        except (Forbidden, BadRequest, TimedOut, NetworkError):
                            pass

                if (gb_threshold is not None) and (not sent_this_service):
                    u_limit_raw = info.get("usage_limit_GB", None)
                    try:
                        u_limit = float(u_limit_raw) if u_limit_raw is not None else None
                    except Exception:
                        u_limit = None

                    if (u_limit is not None) and (u_limit > 0):
                        used = _extract_usage_gb(info)
                        if used is not None:
                            remaining = max(0.0, u_limit - float(used))
                            if remaining <= float(gb_threshold):
                                if not db.was_reminder_sent(svc["service_id"], "expiry_gb", today):
                                    try:
                                        gb_left_str = f"{remaining:.2f}".rstrip("0").rstrip(".")
                                        text = template_gb.format(service_name=name, gb=float(gb_threshold), gb_left=gb_left_str)
                                        await context.bot.send_message(chat_id=svc["user_id"], text=text)
                                        db.mark_reminder_sent(svc["service_id"], "expiry_gb", today)
                                        sent_this_service = True
                                    except RetryAfter as e:
                                        await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
                                        await context.bot.send_message(chat_id=svc["user_id"], text=text)
                                        db.mark_reminder_sent(svc["service_id"], "expiry_gb", today)
                                        sent_this_service = True
                                    except (Forbidden, BadRequest, TimedOut, NetworkError):
                                        pass

                await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug("expiry check for service %s failed: %s", svc.get("service_id"), e)

    except Exception as e:
        logger.error("expiry_reminder_job error: %s", e, exc_info=True)