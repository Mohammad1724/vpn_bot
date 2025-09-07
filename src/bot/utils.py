# filename: bot/utils.py
# -*- coding: utf-8 -*-
import io
import sqlite3
import random
import logging
from typing import Union, Optional, Tuple, Dict, Any, List
from datetime import datetime, timedelta, timezone
import math
import re
from urllib.parse import quote_plus

import qrcode
import database as db
from config import PANEL_DOMAIN, ADMIN_PATH, SUB_PATH, SUB_DOMAINS

try:
    from config import SUBCONVERTER_ENABLED, SUBCONVERTER_URL, SUBCONVERTER_DEFAULT_TARGET
except Exception:
    SUBCONVERTER_ENABLED = False
    SUBCONVERTER_URL = ""
    SUBCONVERTER_DEFAULT_TARGET = "v2ray"
try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)

_PERSIAN_DIGIT_MAP = str.maketrans("0123456789,-", "۰۱۲۳۴۵۶۷۸۹،-")

def to_persian_digits(s: str) -> str:
    if not s: return ""
    try: return s.translate(_PERSIAN_DIGIT_MAP)
    except Exception: return s

def format_toman(amount: Union[int, float, str], persian_digits: bool = False) -> str:
    try: amt = int(round(float(amount)))
    except (ValueError, TypeError): amt = 0
    s = f"{amt:,.0f} تومان"
    if persian_digits: s = to_persian_digits(s)
    return s

def parse_date_flexible(date_str: str) -> Union[datetime, None]:
    if not date_str: return None
    s = str(date_str).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return dt.astimezone()
    except ValueError: pass
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d")
    for fmt in fmts:
        try:
            dt_naive = datetime.strptime(s.split('.')[0], fmt)
            return dt_naive.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone()
        except ValueError: continue
    if re.match(r"^\d+$", s):
        try:
            ts = int(s)
            if 946684800 <= ts <= 2145916800: return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        except (ValueError, OverflowError): pass
    logger.error(f"Date parse failed for '{date_str}'.")
    return None

def normalize_link_type(t: str) -> str:
    return (t or "sub").strip().lower().replace("clash-meta", "clashmeta")

def _clean_path(seg: Optional[str]) -> str:
    return (seg or "").strip().strip("/")

def build_subscription_url(user_uuid: str) -> str:
    sub_path = _clean_path(SUB_PATH) or "sub"
    domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    if isinstance(domain, str): domain = domain.strip()
    return f"https://{domain}/{sub_path}/{user_uuid}"

def _sanitize_sublink(url: str) -> str:
    if not isinstance(url, str) or not url.strip(): return url
    u = url.strip()
    admin, sub = _clean_path(ADMIN_PATH), (_clean_path(SUB_PATH) or "sub")
    return u.replace(f"/{admin}/", f"/{sub}/")

def make_qr_bytes(data: str) -> io.BytesIO:
    img = qrcode.make(data)
    bio = io.BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def _panel_expiry_from_info(user_data: dict) -> Optional[datetime]:
    if not isinstance(user_data, dict): return None
    exp_ts = user_data.get("expire")
    if isinstance(exp_ts, (int, float)) and exp_ts > 0:
        try: return datetime.fromtimestamp(int(exp_ts), tz=timezone.utc).astimezone()
        except Exception: pass
    start = user_data.get("last_reset_time") or user_data.get("start_date") or user_data.get("created_at")
    pkg_days = user_data.get("package_days")
    if start and pkg_days is not None:
        try:
            start_dt, days = parse_date_flexible(start), int(float(pkg_days))
            if start_dt and days > 0: return (start_dt + timedelta(days=days)).astimezone()
        except Exception: pass
    return None

def _format_expiry_and_days(user_data: dict) -> Tuple[str, int]:
    expire_dt = _panel_expiry_from_info(user_data)
    now_aware = datetime.now().astimezone()
    expire_jalali, days_left = "نامشخص", 0
    if expire_dt:
        try: expire_jalali = jdatetime.date.fromgregorian(date=expire_dt.date()).strftime('%Y/%m/%d') if jdatetime else expire_dt.strftime("%Y-%m-%d")
        except Exception: expire_jalali = expire_dt.strftime("%Y-%m-%d")
        if expire_dt > now_aware: days_left = math.ceil((expire_dt - now_aware).total_seconds() / (24 * 3600))
    return expire_jalali, days_left

def create_service_info_caption(user_data: dict, service_db_record: Optional[dict] = None, title: str = "🎉 سرویس شما!", override_sub_url: Optional[str] = None) -> str:
    used_gb, total_gb = round(float(user_data.get('current_usage_GB', 0.0)), 2), round(float(user_data.get('usage_limit_GB', 0.0)), 2)
    unlimited = (total_gb <= 0.0)
    expire_jalali, days_left = _format_expiry_and_days(user_data)
    is_active = not (user_data.get('status') in ('disabled', 'limited') or days_left <= 0 or (not unlimited and total_gb > 0 and used_gb >= total_gb))
    status_text = "✅ فعال" if is_active else "❌ غیرفعال"
    service_name = user_data.get('name') or user_data.get('uuid', 'N/A')
    if unlimited and isinstance(service_name, str) and "0 گیگ" in service_name: service_name = service_name.replace("0 گیگ", "نامحدود")
    if override_sub_url:
        sub_url = override_sub_url
    else:
        sub_url = build_subscription_url(user_data['uuid'])
    traffic_line = f"حجم: نامحدود | مصرف: {used_gb}GB" if unlimited else f"حجم: {used_gb}/{total_gb}GB (باقی: {round(max(total_gb - used_gb, 0.0), 2)}GB)"
    return (f"{title}\n{service_name}\n\nوضعیت: {status_text}\n{traffic_line}\nانقضا: {expire_jalali} | باقیمانده: {days_left} روز\n\nلینک اشتراک:\n`{sub_url}`")

def get_service_status(hiddify_info: dict) -> Tuple[str, str, bool]:
    now = datetime.now(timezone.utc)
    is_expired = False
    if hiddify_info.get('status') in ('disabled', 'limited') or hiddify_info.get('days_left', 999) < 0: is_expired = True
    usage_limit, current_usage = hiddify_info.get('usage_limit_GB', 0), hiddify_info.get('current_usage_GB', 0)
    if usage_limit > 0 and current_usage >= usage_limit: is_expired = True
    expire_ts = hiddify_info.get('expire')
    if isinstance(expire_ts, (int, float)) and expire_ts > 0: expiry_dt_utc = datetime.fromtimestamp(expire_ts, tz=timezone.utc)
    else:
        start_date_str = next((hiddify_info.get(k) for k in ['start_date', 'last_reset_time', 'created_at'] if hiddify_info.get(k)), None)
        package_days = hiddify_info.get('package_days', 0)
        if not start_date_str: return "نامشخص", "N/A", True
        start_dt = parse_date_flexible(start_date_str)
        if not start_dt: return "نامشخص", "N/A", True
        expiry_dt_utc = start_dt + timedelta(days=package_days)
    if not is_expired and now > expiry_dt_utc: is_expired = True
    expire_j = "N/A"
    if jdatetime:
        try: expire_j = jdatetime.date.fromgregorian(date=expiry_dt_utc.astimezone().date()).strftime('%Y/%m/%d')
        except Exception: pass
    return "🔴 منقضی شده" if is_expired else "🟢 فعال", expire_j, is_expired