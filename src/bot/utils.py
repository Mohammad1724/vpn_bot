# filename: bot/utils.py
# (کل فایل - اصلاح شده با debug)

import io
import sqlite3
import random
import logging
from typing import Union, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta, timezone
import math
import re
from urllib.parse import quote_plus

import qrcode
import database as db

try:
    from config import PANEL_DOMAIN, SUB_DOMAINS, PANEL_SECRET_UUID, SUB_PATH
except ImportError:
    PANEL_DOMAIN, SUB_DOMAINS, PANEL_SECRET_UUID, SUB_PATH = "", [], "", "sub"

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
            dt_naive = datetime.strptime(s.split('.')[0], fmt)
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


def _clean_path(seg: Optional[str]) -> str:
    return (seg or "").strip().strip("/")


def build_subscription_url(user_uuid: str) -> str:
    domain = (random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN)
    client_secret = _clean_path(PANEL_SECRET_UUID)

    if not client_secret:
        logger.warning("PANEL_SECRET_UUID is not set in config.py! Subscription links will be incorrect.")
        sub_path = _clean_path(SUB_PATH) or "sub"
        return f"https://{domain}/{sub_path}/{user_uuid}/"

    return f"https://{domain}/{client_secret}/{user_uuid}/sub/"


def make_qr_bytes(data: str) -> io.BytesIO:
    img = qrcode.make(data)
    bio = io.BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


def _panel_expiry_from_info(user_data: dict) -> Optional[datetime]:
    if not isinstance(user_data, dict):
        return None

    # اولویت اول: فیلد expire (timestamp)
    expire_ts = user_data.get("expire")
    if isinstance(expire_ts, (int, float)) and expire_ts > 0:
        try:
            return datetime.fromtimestamp(int(expire_ts), tz=timezone.utc)
        except Exception:
            pass

    # اولویت دوم: محاسبه بر اساس start_date و package_days
    start_str = user_data.get("start_date") or user_data.get("last_reset_time")
    days = user_data.get("package_days")
    if start_str and isinstance(days, int) and days > 0:
        start_dt = parse_date_flexible(start_str)
        if start_dt:
            return start_dt + timedelta(days=days)

    return None


def _format_expiry_and_days(user_data: dict) -> Tuple[str, int]:
    expire_dt_utc = _panel_expiry_from_info(user_data)
    now_utc = datetime.now(timezone.utc)

    expire_jalali, days_left = "نامشخص", 0

    if expire_dt_utc:
        # تبدیل به منطقه زمانی محلی برای نمایش صحیح
        expire_local = expire_dt_utc.astimezone()
        try:
            expire_jalali = jdatetime.date.fromgregorian(date=expire_local.date()).strftime('%Y/%m/%d') if jdatetime else expire_local.strftime("%Y-%m-%d")
        except Exception:
            expire_jalali = expire_local.strftime("%Y-%m-%d")

        if expire_dt_utc > now_utc:
            time_left = expire_dt_utc - now_utc
            days_left = math.ceil(time_left.total_seconds() / (24 * 3600))
            
        # Debug logging
        logger.debug(f"Debug info for user: expire_dt_utc={expire_dt_utc}, now_utc={now_utc}, days_left={days_left}")

    return expire_jalali, days_left


def create_service_info_caption(
    user_data: dict,
    service_db_record: Optional[dict] = None,
    title: str = "🎉 سرویس شما!",
    override_sub_url: Optional[str] = None
) -> str:
    used_gb = round(float(user_data.get('current_usage_GB', 0.0)), 2)
    total_gb = round(float(user_data.get('usage_limit_GB', 0.0)), 2)
    unlimited = (total_gb <= 0.0)

    expire_jalali, days_left = _format_expiry_and_days(user_data)
    is_active = not (
        user_data.get('status') in ('disabled', 'limited')
        or days_left <= 0
        or (not unlimited and total_gb > 0 and used_gb >= total_gb)
    )

    status_text = "✅ فعال" if is_active else "❌ غیرفعال"
    service_name = user_data.get('name') or user_data.get('uuid', 'N/A')
    if unlimited and isinstance(service_name, str) and "0 گیگ" in service_name:
        service_name = service_name.replace("0 گیگ", "نامحدود")

    if override_sub_url:
        sub_url = override_sub_url
    elif service_db_record and service_db_record.get('sub_link'):
        sub_url = service_db_record.get('sub_link')
    else:
        sub_url = build_subscription_url(user_data['uuid'])

    traffic_line = (
        f"حجم: نامحدود | مصرف: {used_gb}GB"
        if unlimited
        else f"حجم: {used_gb}/{total_gb}GB (باقی: {round(max(total_gb - used_gb, 0.0), 2)}GB)"
    )

    # نمایش مدت کل پلن و روزهای باقیمانده
    package_days = user_data.get('package_days', 0)
    
    # Debug info
    start_date = user_data.get('start_date', 'N/A')
    expire_ts = user_data.get('expire', 'N/A')
    logger.debug(f"Service debug: package_days={package_days}, start_date={start_date}, expire={expire_ts}, days_left={days_left}")
    
    return (
        f"{title}\n"
        f"{service_name}\n\n"
        f"وضعیت: {status_text}\n"
        f"{traffic_line}\n"
        f"انقضا: {expire_jalali} | مدت: {package_days} روز | باقیمانده: {days_left} روز\n\n"
        f"لینک اشتراک:\n`{sub_url}`"
    )


def get_service_status(hiddify_info: dict) -> Tuple[str, str, bool]:
    expire_jalali, days_left = _format_expiry_and_days(hiddify_info)
    is_expired = days_left <= 0
    if hiddify_info.get('status') in ('disabled', 'limited'):
        is_expired = True

    usage_limit = hiddify_info.get('usage_limit_GB', 0)
    current_usage = hiddify_info.get('current_usage_GB', 0)
    if usage_limit > 0 and current_usage >= usage_limit:
        is_expired = True

    return "🔴 منقضی شده" if is_expired else "🟢 فعال", expire_jalali, is_expired


def is_valid_sqlite(filepath: str) -> bool:
    try:
        with sqlite3.connect(filepath) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            result = cur.fetchone()
        return result and result[0] == 'ok'
    except sqlite3.DatabaseError:
        return False