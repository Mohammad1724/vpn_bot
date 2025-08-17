# -*- coding: utf-8 -*-

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Union
import logging
import random
import jdatetime
import database as db
from config import PANEL_DOMAIN, ADMIN_PATH, SUB_PATH, SUB_DOMAINS

logger = logging.getLogger(__name__)

def parse_date_flexible(date_str: str) -> Union[datetime, None]:
    if not date_str:
        return None
    s = str(date_str).strip().replace("Z", "+00:00")
    # سعی اول: ISO
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            local_tz = datetime.now().astimezone().tzinfo
            dt = dt.replace(tzinfo=local_tz)
        return dt.astimezone()
    except Exception:
        pass
    # سعی دوم: الگوهای رایج
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d")
    for fmt in fmts:
        try:
            dt_naive = datetime.strptime(s.split('.')[0], fmt)
            local_tz = datetime.now().astimezone().tzinfo
            dt_local = dt_naive.replace(tzinfo=local_tz)
            return dt_local.astimezone()
        except Exception:
            continue
    logger.error(f"Date parse failed for '{date_str}'.")
    return None

def create_service_info_message(user_data: dict, title: str = "🎉 سرویس شما!") -> str:
    """
    ساخت پیام اطلاعات سرویس با نمایش صحیح نامحدود، تاریخ شمسی و لینک صحیح.
    """
    # لینک اشتراک داینامیک
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    subscription_link = f"https://{sub_domain}/{sub_path}/"

    # حجم‌ها (سازگار با API)
    used_gb = float(user_data.get('current_usage_GB', 0.0))
    total_gb = float(user_data.get('usage_limit_GB', 0.0))
    used_gb = round(used_gb, 2)
    total_gb = round(total_gb, 2)
    unlimited = (total_gb <= 0.0)

    # محاسبه تاریخ انقضا
    expire_dt = None
    start_date_str = user_data.get('created_at') or user_data.get('last_reset_time') or user_data.get('start_date')
    if 'expire' in user_data and str(user_data['expire']).isdigit():
        try:
            expire_dt = datetime.fromtimestamp(int(user_data['expire']), tz=timezone.utc).astimezone()
        except Exception:
            expire_dt = None
    if expire_dt is None and start_date_str:
        start_dt = parse_date_flexible(start_date_str)
        if start_dt:
            try:
                package_days = int(user_data.get('package_days', 0))
            except Exception:
                package_days = 0
            if package_days > 0:
                expire_dt = start_dt + timedelta(days=package_days)

    now_aware = datetime.now().astimezone()
    # تاریخ شمسی + روزهای باقی‌مانده
    expire_date_shamsi = "نامشخص"
    remaining_days = 0
    if expire_dt:
        try:
            expire_date_shamsi = jdatetime.date.fromgregorian(date=expire_dt.date()).strftime('%Y-%m-%d')
        except Exception as e:
            logger.error(f"Jdatetime conversion error: {e}")
        if expire_dt.date() > now_aware.date():
            remaining_days = (expire_dt.date() - now_aware.date()).days
        else:
            remaining_days = 0

    # وضعیت سرویس
    is_active = True
    if user_data.get('status') in ('disabled', 'limited'):
        is_active = False
    elif (not unlimited) and total_gb > 0 and used_gb >= total_gb:
        is_active = False
    elif expire_dt and expire_dt.date() < now_aware.date():
        is_active = False
    status_text = "✅ فعال" if is_active else "❌ غیرفعال"

    # نام سرویس: برای نامحدود، 0 گیگ را با نامحدود جایگزین کن
    service_name = user_data.get('name') or user_data.get('uuid', 'N/A')
    if unlimited:
        try:
            if isinstance(service_name, str) and "0 گیگ" in service_name:
                service_name = service_name.replace("0 گیگ", "نامحدود")
            elif service_name == user_data.get('uuid'):
                service_name = "سرویس نامحدود"
        except Exception:
            service_name = "سرویس نامحدود"

    # بدنه پیام بر اساس نامحدود/حجمی
    volume_section = ""
    if unlimited:
        volume_section = (
            f"▫️ حجم: نامحدود\n"
            f"▫️ مصرف تا این لحظه: {used_gb} گیگابایت\n"
        )
    else:
        remaining_gb = round(max(total_gb - used_gb, 0.0), 2)
        volume_section = (
            f"▫️ حجم کل: {total_gb} گیگابایت\n"
            f"▫️ حجم مصرفی: {used_gb} گیگابایت\n"
            f"▫️ حجم باقی‌مانده: {remaining_gb} گیگابایت\n"
        )

    # هشدار متناسب
    if unlimited:
        caution = "⚠️ برای جلوگیری از قطع شدن سرویس، قبل از پایان تاریخ انقضا آن را تمدید کنید."
    else:
        caution = "⚠️ برای جلوگیری از قطع شدن سرویس، قبل از اتمام حجم یا تاریخ انقضا، آن را تمدید کنید."

    # مونتاژ پیام
    message_text = f"""
{title}
{service_name}

▫️ وضعیت: {status_text}

{volume_section}▫️ تاریخ انقضا: {expire_date_shamsi}
▫️ روزهای باقی‌مانده: {remaining_days} روز

🔗 لینک اتصال شما (برای کپی روی آن کلیک کنید):
{subscription_link}{user_data['uuid']}

{caution}
    """.strip()
    return message_text

def get_domain_for_plan(plan: dict | None) -> str:
    is_unlimited = plan and plan.get('gb', 1) == 0
    if is_unlimited:
        unlimited_domains_str = db.get_setting("unlimited_sub_domains")
        if unlimited_domains_str:
            return random.choice([d.strip() for d in unlimited_domains_str.split(',')])
    else:
        volume_domains_str = db.get_setting("volume_based_sub_domains")
        if volume_domains_str:
            return random.choice([d.strip() for d in volume_domains_str.split(',')])
    general_domains_str = db.get_setting("sub_domains")
    if general_domains_str:
        return random.choice([d.strip() for d in general_domains_str.split(',')])
    return PANEL_DOMAIN

def get_service_status(hiddify_info: dict) -> tuple[str, str, bool]:
    # برای سازگاری با بخش‌هایی که هنوز از این تابع استفاده می‌کنند
    now = datetime.now(timezone.utc)
    is_expired = False
    if hiddify_info.get('status') in ('disabled', 'limited'):
        is_expired = True
    elif hiddify_info.get('days_left', 999) < 0:
        is_expired = True
    usage_limit = hiddify_info.get('usage_limit_GB', 0)
    current_usage = hiddify_info.get('current_usage_GB', 0)
    if usage_limit > 0 and current_usage >= usage_limit:
        is_expired = True

    jalali_display_str = "N/A"
    expire_ts = hiddify_info.get('expire')
    if isinstance(expire_ts, (int, float)) and expire_ts > 0:
        expiry_dt_utc = datetime.fromtimestamp(expire_ts, tz=timezone.utc)
    else:
        date_keys = ['start_date', 'last_reset_time', 'created_at']
        start_date_str = next((hiddify_info.get(k) for k in date_keys if hiddify_info.get(k)), None)
        package_days = hiddify_info.get('package_days', 0)
        if not start_date_str:
            return "نامشخص", "N/A", True
        start_dt_utc = parse_date_flexible(start_date_str)
        if not start_dt_utc:
            return "نامشخص", "N/A", True
        expiry_dt_utc = start_dt_utc + timedelta(days=package_days)

    if not is_expired and now > expiry_dt_utc:
        is_expired = True

    if jdatetime:
        try:
            local_expiry_dt = expiry_dt_utc.astimezone()
            jalali_display_str = jdatetime.date.fromgregorian(date=local_expiry_dt.date()).strftime('%Y/%m/%d')
        except Exception:
            pass

    status_text = "🔴 منقضی شده" if is_expired else "🟢 فعال"
    return status_text, jalali_display_str, is_expired

def is_valid_sqlite(filepath: str) -> bool:
    try:
        with sqlite3.connect(filepath) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            result = cur.fetchone()
        return result and result[0] == 'ok'
    except sqlite3.DatabaseError:
        return False