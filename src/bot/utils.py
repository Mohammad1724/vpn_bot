# -*- coding: utf-8 -*-

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Union
import logging
import random
import database as db
from config import PANEL_DOMAIN

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)

def get_domain_for_plan(plan: dict | None) -> str:
    """
    بر اساس نوع پلن (حجمی یا نامحدود)، یک ساب‌دامین مناسب را از دیتابیس می‌خواند و انتخاب می‌کند.
    """
    is_unlimited = plan and plan.get('gb', 1) == 0

    if is_unlimited:
        unlimited_domains_str = db.get_setting("unlimited_sub_domains")
        if unlimited_domains_str:
            return random.choice([d.strip() for d in unlimited_domains_str.split(',')])
    
    else: # Volume-based
        volume_domains_str = db.get_setting("volume_based_sub_domains")
        if volume_domains_str:
            return random.choice([d.strip() for d in volume_domains_str.split(',')])

    # Fallback to general list
    general_domains_str = db.get_setting("sub_domains")
    if general_domains_str:
        return random.choice([d.strip() for d in general_domains_str.split(',')])
    
    # Final fallback to panel domain
    return PANEL_DOMAIN


def parse_date_flexible(date_str: str) -> Union[datetime, None]:
    if not date_str:
        return None
    s = str(date_str).strip().replace("Z", "+00:00")
    
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    fmts = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(s.split('.')[0], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
            
    logger.error(f"Date parse failed for '{date_str}'.")
    return None

def get_service_status(hiddify_info: dict) -> tuple[str, str, bool]:
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