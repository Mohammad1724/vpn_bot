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
    from config import MULTI_SERVER_ENABLED, SERVERS
except Exception:
    MULTI_SERVER_ENABLED = False
    SERVERS = []

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
    if not s:
        return ""
    try:
        return s.translate(_PERSIAN_DIGIT_MAP)
    except Exception:
        return s

def format_toman(amount: Union[int, float, str], persian_digits: bool = False) -> str:
    try:
        amt = int(round(float(amount)))
    except (ValueError, TypeError):
        amt = 0
    s = f"{amt:,.0f} تومان"
    if persian_digits:
        s = to_persian_digits(s)
    return s

def parse_date_flexible(date_str: str) -> Union[datetime, None]:
    if not date_str:
        return None
    s = str(date_str).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return dt.astimezone()
    except ValueError:
        pass
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d")
    for fmt in fmts:
        try:
            clean_s = s.split('.')[0]
            dt_naive = datetime.strptime(clean_s, fmt)
            return dt_naive.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone()
        except ValueError:
            continue
    if re.match(r"^\d+$", s):
        try:
            ts = int(s)
            if 946684800 <= ts <= 2145916800:
                return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        except (ValueError, OverflowError):
            pass
    logger.error(f"Date parse failed for '{date_str}'.")
    return None

def normalize_link_type(t: str) -> str:
    return (t or "sub").strip().lower().replace("clash-meta", "clashmeta")

def link_type_to_subconverter_target(link_type: str) -> str:
    lt = normalize_link_type(link_type)
    if lt in ("sub", "sub64"): return "v2ray"
    if lt == "auto": return (SUBCONVERTER_DEFAULT_TARGET or "v2ray").strip().lower()
    if lt in ("xray", "singbox", "clash", "clashmeta"): return lt
    return "v2ray"

def build_subscription_url(user_uuid: str, server_name: Optional[str] = None) -> str:
    if MULTI_SERVER_ENABLED and SERVERS:
        server = next((s for s in SERVERS if str(s.get("name")) == str(server_name)), SERVERS[0])
        sub_path = server.get("sub_path") or server.get("admin_path")
        sub_domains = server.get("sub_domains") or []
        sub_domain = random.choice(sub_domains) if sub_domains else server.get("panel_domain")
        return f"https://{sub_domain}/{sub_path}/{user_uuid}"
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    return f"https://{sub_domain}/{sub_path}/{user_uuid}"

def build_subconverter_link(urls: List[str], target: Optional[str] = None) -> Optional[str]:
    try:
        if not SUBCONVERTER_ENABLED or not SUBCONVERTER_URL or not urls:
            return None
        tgt = (target or SUBCONVERTER_DEFAULT_TARGET or "v2ray").strip().lower()
        src = "|".join(u.strip() for u in urls if u and u.strip())
        if not src: return None
        src_enc = quote_plus(src, safe=":/?&=%|")
        base = SUBCONVERTER_URL.rstrip("/")
        return f"{base}/sub?target={tgt}&url={src_enc}"
    except Exception as e:
        logger.error("build_subconverter_link failed: %s", e, exc_info=True)
        return None

def make_qr_bytes(data: str) -> io.BytesIO:
    img = qrcode.make(data)
    bio = io.BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def _format_expiry_and_days(user_data: dict, service_db_record: Optional[dict] = None) -> Tuple[str, int]:
    expire_dt = None
    if service_db_record:
        plan_id = service_db_record.get('plan_id')
        start_dt = parse_date_flexible(service_db_record.get('created_at'))
        if start_dt:
            package_days = 0
            if plan_id:
                plan = db.get_plan(plan_id)
                if plan: package_days = int(plan.get('days', 0))
            else:
                try: package_days = int(db.get_setting("trial_days") or 1)
                except (ValueError, TypeError): package_days = 1
            if package_days > 0:
                expire_dt = start_dt + timedelta(days=package_days)

    if expire_dt is None and 'expire' in user_data and str(user_data['expire']).isdigit():
        try:
            expire_dt = datetime.fromtimestamp(int(user_data['expire']), tz=timezone.utc).astimezone()
        except (ValueError, OverflowError):
            expire_dt = None

    now_aware = datetime.now().astimezone()
    expire_jalali, days_left = "نامشخص", 0
    if expire_dt:
        try:
            expire_jalali = jdatetime.date.fromgregorian(date=expire_dt.date()).strftime('%Y/%m/%d') if jdatetime else expire_dt.strftime("%Y-%m-%d")
        except Exception:
            expire_jalali = expire_dt.strftime("%Y-%m-%d")
        if expire_dt > now_aware:
            days_left = math.ceil((expire_dt - now_aware).total_seconds() / (24 * 3600))
    return expire_jalali, days_left

def create_service_info_caption(
    user_data: dict, service_db_record: Optional[dict] = None, title: str = "🎉 سرویس شما!", override_sub_url: Optional[str] = None
) -> str:
    used_gb = round(float(user_data.get('current_usage_GB', 0.0)), 2)
    total_gb = round(float(user_data.get('usage_limit_GB', 0.0)), 2)
    unlimited = (total_gb <= 0.0)
    expire_jalali, days_left = _format_expiry_and_days(user_data, service_db_record)

    is_active = not (user_data.get('status') in ('disabled', 'limited') or days_left <= 0 or (not unlimited and total_gb > 0 and used_gb >= total_gb))
    status_text = "✅ فعال" if is_active else "❌ غیرفعال"
    service_name = user_data.get('name') or user_data.get('uuid', 'N/A')
    if unlimited and isinstance(service_name, str) and "0 گیگ" in service_name:
        service_name = service_name.replace("0 گیگ", "نامحدود")

    if override_sub_url:
        sub_url = override_sub_url
    elif service_db_record and service_db_record.get("sub_link"):
        sub_url = service_db_record["sub_link"]
    else:
        sub_url = build_subscription_url(user_data['uuid'], server_name=(service_db_record or {}).get("server_name"))

    traffic_line = f"حجم: نامحدود | مصرف: {used_gb}GB" if unlimited else f"حجم: {used_gb}/{total_gb}GB (باقی: {round(max(total_gb - used_gb, 0.0), 2)}GB)"

    return (
        f"{title}\n"
        f"{service_name}\n\n"
        f"وضعیت: {status_text}\n"
        f"{traffic_line}\n"
        f"انقضا: {expire_jalali} | باقیمانده: {days_left} روز\n\n"
        f"لینک اشتراک:\n`{sub_url}`"
    )

def get_service_status(hiddify_info: dict) -> Tuple[str, str, bool]:
    now = datetime.now(timezone.utc)
    is_expired = False
    if hiddify_info.get('status') in ('disabled', 'limited') or hiddify_info.get('days_left', 999) < 0:
        is_expired = True
    usage_limit, current_usage = hiddify_info.get('usage_limit_GB', 0), hiddify_info.get('current_usage_GB', 0)
    if usage_limit > 0 and current_usage >= usage_limit:
        is_expired = True
    expire_ts = hiddify_info.get('expire')
    if isinstance(expire_ts, (int, float)) and expire_ts > 0:
        expiry_dt_utc = datetime.fromtimestamp(expire_ts, tz=timezone.utc)
    else:
        start_date_str = next((hiddify_info.get(k) for k in ['start_date', 'last_reset_time', 'created_at'] if hiddify_info.get(k)), None)
        package_days = hiddify_info.get('package_days', 0)
        if not start_date_str: return "نامشخص", "N/A", True
        start_dt = parse_date_flexible(start_date_str)
        if not start_dt: return "نامشخص", "N/A", True
        expiry_dt_utc = start_dt + timedelta(days=package_days)
    if not is_expired and now > expiry_dt_utc:
        is_expired = True
    expire_j = "N/A"
    if jdatetime:
        try:
            expire_j = jdatetime.date.fromgregorian(date=expiry_dt_utc.astimezone().date()).strftime('%Y/%m/%d')
        except Exception: pass
    return "🔴 منقضی شده" if is_expired else "🟢 فعال", expire_j, is_expired

def is_valid_sqlite(filepath: str) -> bool:
    try:
        with sqlite3.connect(filepath) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            result = cur.fetchone()
        return result and result[0] == 'ok'
    except sqlite3.DatabaseError:
        return False