# -*- coding: utf-8 -*-

import sqlite3
from datetime import datetime, timedelta
from typing import Union
import jdatetime
import logging

logger = logging.getLogger(__name__)

def parse_date_flexible(date_str: str) -> Union[datetime.date, None]:
    if not date_str:
        return None
    s = str(date_str).strip()
    candidates = [s]
    for sep in ("T", " "):
        if sep in s:
            candidates.append(s.split(sep, 1)[0])
    candidates.extend([c.replace("/", "-") for c in list(candidates)])
    seen, ordered = set(), []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    for c in ordered:
        try:
            return datetime.fromisoformat(c).date()
        except Exception:
            pass
    fmts = ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S")
    for c in ordered:
        for fmt in fmts:
            try:
                return datetime.strptime(c, fmt).date()
            except Exception:
                continue
    logger.error(f"Date parse failed for '{date_str}'.")
    return None

def get_service_status(hiddify_info: dict):
    # returns (status_text_persian, jalali_expiry_str, is_expired)
    
    # 1. اولویت با فلگ‌های مستقیم پنل (برای سرویس تست و منقضی‌شده‌ها)
    if hiddify_info.get('status') in ('disabled', 'limited'):
        status, is_expired = "🔴 منقضی شده", True
    elif hiddify_info.get('days_left', 999) <= 0:
        status, is_expired = "🔴 منقضی شده", True
    else:
        status, is_expired = "🟢 فعال", False

    # 2. محاسبه تاریخ انقضا
    date_keys = ['start_date', 'last_reset_time', 'created_at']
    start_date_str = next((hiddify_info.get(k) for k in date_keys if hiddify_info.get(k)), None)
    package_days = hiddify_info.get('package_days', 0)

    if not start_date_str:
        return "نامشخص", "N/A", True

    start_date_obj = parse_date_flexible(start_date_str)
    if not start_date_obj:
        return "نامشخص", "N/A", True

    expiry_date_obj = start_date_obj + timedelta(days=package_days)
    jalali_expiry_date = jdatetime.date.fromgregorian(date=expiry_date_obj)
    jalali_display_str = jalali_expiry_date.strftime("%Y/%m/%d")

    # 3. بازبینی وضعیت بر اساس تاریخ محاسبه‌شده
    if not is_expired and expiry_date_obj < datetime.now().date():
        is_expired = True
        status = "🔴 منقضی شده"
        
    return status, jalali_display_str, is_expired

def is_valid_sqlite(filepath: str) -> bool:
    try:
        with sqlite3.connect(filepath) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            result = cur.fetchone()
        return result and result[0] == 'ok'
    except sqlite3.DatabaseError:
        return False