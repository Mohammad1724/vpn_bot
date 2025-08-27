# -*- coding: utf-8 -*-

import io
import sqlite3
import random
import logging
from typing import Union, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta, timezone
import math
import re

import qrcode
import database as db
from config import PANEL_DOMAIN, ADMIN_PATH, SUB_PATH, SUB_DOMAINS

# Optional multi-server import
try:
    from config import MULTI_SERVER_ENABLED, SERVERS
except Exception:
    MULTI_SERVER_ENABLED = False
    SERVERS = []

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)

# ---------------------------
# Helpers for Formatting
# ---------------------------
_PERSIAN_DIGIT_MAP = str.maketrans("0123456789,-", "۰۱۲۳۴۵۶۷۸۹،-")

def to_persian_digits(s: str) -> str:
    """تبدیل اعداد لاتین به فارسی"""
    if not s:
        return ""
    try:
        return s.translate(_PERSIAN_DIGIT_MAP)
    except Exception:
        return s

def format_toman(amount: Union[int, float, str], persian_digits: bool = False) -> str:
    """فرمت‌بندی مبلغ به تومان با جداکننده هزارگان"""
    try:
        amt = int(round(float(amount)))
    except (ValueError, TypeError):
        amt = 0
    s = f"{amt:,.0f} تومان"
    if persian_digits:
        s = to_persian_digits(s)
    return s

def parse_date_flexible(date_str: str) -> Union[datetime, None]:
    """تجزیه انعطاف‌پذیر تاریخ در فرمت‌های مختلف"""
    if not date_str:
        return None

    s = str(date_str).strip().replace("Z", "+00:00")

    # تلاش با datetime.fromisoformat (پایتون 3.7+)
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            local_tz = datetime.now().astimezone().tzinfo
            dt = dt.replace(tzinfo=local_tz)
        return dt.astimezone()
    except ValueError:
        pass

    # تلاش با فرمت‌های مختلف
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d")
    for fmt in fmts:
        try:
            # حذف میلی‌ثانیه
            clean_s = s.split('.')[0]
            dt_naive = datetime.strptime(clean_s, fmt)
            local_tz = datetime.now().astimezone().tzinfo
            return dt_naive.replace(tzinfo=local_tz).astimezone()
        except ValueError:
            continue

    # تلاش با الگو برای اعداد timestamp
    if re.match(r"^\d+$", s):
        try:
            ts = int(s)
            if 946684800 <= ts <= 2145916800:  # محدوده معقول برای timestamp (2000-2038)
                return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        except (ValueError, OverflowError):
            pass

    logger.error(f"Date parse failed for '{date_str}'.")
    return None

# ---------------------------
# Subscription and Service Info
# ---------------------------
def build_subscription_url(user_uuid: str, server_name: Optional[str] = None) -> str:
    """ساخت URL اشتراک بر اساس UUID کاربر و سرور انتخابی (در صورت وجود)"""
    if MULTI_SERVER_ENABLED and SERVERS:
        # انتخاب سرور با نام یا fallback به اولی
        server = None
        if server_name:
            for s in SERVERS:
                if str(s.get("name")) == str(server_name):
                    server = s
                    break
        if not server:
            server = SERVERS[0]
        sub_path = server.get("sub_path") or server.get("admin_path")
        sub_domains = server.get("sub_domains") or []
        sub_domain = random.choice(sub_domains) if sub_domains else server.get("panel_domain")
        return f"https://{sub_domain}/{sub_path}/{user_uuid}"
    # حالت تک‌سرور
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    return f"https://{sub_domain}/{sub_path}/{user_uuid}"

def make_qr_bytes(data: str) -> io.BytesIO:
    """تولید کد QR برای یک رشته و بازگرداندن آن به صورت BytesIO"""
    img = qrcode.make(data)
    bio = io.BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def _format_expiry_and_days(user_data: dict, service_db_record: Optional[dict] = None) -> Tuple[str, int]:
    """محاسبه تاریخ انقضا و روزهای باقی‌مانده برای یک سرویس"""
    expire_dt = None

    # روش 1: استفاده از رکورد سرویس در دیتابیس برای محاسبه
    if service_db_record:
        plan_id = service_db_record.get('plan_id')
        start_date_str = service_db_record.get('created_at')
        start_dt = parse_date_flexible(start_date_str)

        if start_dt:
            package_days = 0
            if plan_id:
                plan = db.get_plan(plan_id)
                if plan:
                    package_days = int(plan.get('days', 0))
            else: # سرویس تست رایگان
                try:
                    package_days = int(db.get_setting("trial_days") or 1)
                except (ValueError, TypeError):
                    package_days = 1

            if package_days > 0:
                expire_dt = start_dt + timedelta(days=package_days)

    # روش 2: استفاده از timestamp انقضا از پنل هیدیفای
    if expire_dt is None and 'expire' in user_data and str(user_data['expire']).isdigit():
        try:
            expire_dt = datetime.fromtimestamp(int(user_data['expire']), tz=timezone.utc).astimezone()
        except (ValueError, OverflowError):
            expire_dt = None

    now_aware = datetime.now().astimezone()
    expire_jalali = "نامشخص"
    days_left = 0

    if expire_dt:
        # تبدیل به تاریخ شمسی
        try:
            expire_jalali = jdatetime.date.fromgregorian(date=expire_dt.date()).strftime('%Y/%m/%d') if jdatetime else expire_dt.strftime("%Y-%m-%d")
        except Exception:
            expire_jalali = expire_dt.strftime("%Y-%m-%d")

        # محاسبه روزهای باقیمانده
        if expire_dt > now_aware:
            time_diff = expire_dt - now_aware
            days_left = math.ceil(time_diff.total_seconds() / (24 * 3600))
        else:
            days_left = 0

    return expire_jalali, days_left

def create_service_info_caption(user_data: dict, service_db_record: Optional[dict] = None, title: str = "🎉 سرویس شما!") -> str:
    """ایجاد متن توضیحات برای سرویس با اطلاعات کامل"""
    used_gb = round(float(user_data.get('current_usage_GB', 0.0)), 2)
    total_gb = round(float(user_data.get('usage_limit_GB', 0.0)), 2)
    unlimited = (total_gb <= 0.0)

    expire_jalali, days_left = _format_expiry_and_days(user_data, service_db_record)

    # بررسی وضعیت فعال بودن سرویس
    is_active = True
    if user_data.get('status') in ('disabled', 'limited'):
        is_active = False
    elif days_left <= 0:
        is_active = False
    elif (not unlimited) and total_gb > 0 and used_gb >= total_gb:
        is_active = False
    status_text = "✅ فعال" if is_active else "❌ غیرفعال"

    # تصحیح نام سرویس برای سرویس‌های نامحدود
    service_name = user_data.get('name') or user_data.get('uuid', 'N/A')
    if unlimited and isinstance(service_name, str) and "0 گیگ" in service_name:
        service_name = service_name.replace("0 گیگ", "نامحدود")

    # ساخت لینک اشتراک (اولویت با sub_link ذخیره‌شده در DB برای پشتیبانی چندسرور)
    if service_db_record and service_db_record.get("sub_link"):
        sub_url = service_db_record["sub_link"]
    else:
        sub_url = build_subscription_url(user_data['uuid'], server_name=(service_db_record or {}).get("server_name"))

    sub_url_line = f"`{sub_url}`"

    # قالب‌بندی خط مربوط به ترافیک
    if unlimited:
        traffic_line = f"حجم: نامحدود | مصرف: {used_gb}GB"
    else:
        remaining_gb = max(total_gb - used_gb, 0.0)
        traffic_line = f"حجم: {used_gb}/{total_gb}GB (باقی: {round(remaining_gb, 2)}GB)"

    # ساخت متن نهایی
    caption = (
        f"{title}\n"
        f"{service_name}\n\n"
        f"وضعیت: {status_text}\n"
        f"{traffic_line}\n"
        f"انقضا: {expire_jalali} | باقیمانده: {days_left} روز\n\n"
        f"لینک اشتراک:\n{sub_url_line}"
    )
    return caption

def create_service_info_message(user_data: dict, service_db_record: Optional[dict] = None, title: str = "🎉 سرویس شما!") -> str:
    """این تابع برای سازگاری با کد قدیمی حفظ شده است"""
    return create_service_info_caption(user_data, service_db_record=service_db_record, title=title)

def get_domain_for_plan(plan: dict | None) -> str:
    """انتخاب دامنه مناسب بر اساس نوع پلن (نامحدود/حجمی)"""
    is_unlimited = plan and plan.get('gb', 1) == 0

    if is_unlimited:
        unlimited_domains_str = db.get_setting("unlimited_sub_domains")
        if unlimited_domains_str:
            domains = [d.strip() for d in unlimited_domains_str.split(',') if d.strip()]
            if domains:
                return random.choice(domains)
    else:
        volume_domains_str = db.get_setting("volume_based_sub_domains")
        if volume_domains_str:
            domains = [d.strip() for d in volume_domains_str.split(',') if d.strip()]
            if domains:
                return random.choice(domains)

    # اگر دامنه اختصاصی یافت نشد، از دامنه‌های عمومی استفاده می‌کنیم
    general_domains_str = db.get_setting("sub_domains")
    if general_domains_str:
        domains = [d.strip() for d in general_domains_str.split(',') if d.strip()]
        if domains:
            return random.choice(domains)

    # اگر هیچ دامنه‌ای تنظیم نشده باشد، از دامنه اصلی استفاده می‌کنیم
    return PANEL_DOMAIN

def get_service_status(hiddify_info: dict) -> Tuple[str, str, bool]:
    """بررسی وضعیت سرویس (فعال/منقضی) و تاریخ انقضا"""
    now = datetime.now(timezone.utc)
    is_expired = False

    # حالت 1: سرویس غیرفعال یا محدود شده
    if hiddify_info.get('status') in ('disabled', 'limited'):
        is_expired = True
    # حالت 2: روزهای باقیمانده منفی است
    elif hiddify_info.get('days_left', 999) < 0:
        is_expired = True

    # حالت 3: استفاده بیش از حجم مجاز
    usage_limit = hiddify_info.get('usage_limit_GB', 0)
    current_usage = hiddify_info.get('current_usage_GB', 0)
    if usage_limit > 0 and current_usage >= usage_limit:
        is_expired = True

    # محاسبه تاریخ انقضا
    expire_ts = hiddify_info.get('expire')
    if isinstance(expire_ts, (int, float)) and expire_ts > 0:
        expiry_dt_utc = datetime.fromtimestamp(expire_ts, tz=timezone.utc)
    else:
        # اگر timestamp انقضا موجود نیست، سعی می‌کنیم از تاریخ شروع و مدت پکیج محاسبه کنیم
        date_keys = ['start_date', 'last_reset_time', 'created_at']
        start_date_str = next((hiddify_info.get(k) for k in date_keys if hiddify_info.get(k)), None)
        package_days = hiddify_info.get('package_days', 0)

        if not start_date_str:
            return "نامشخص", "N/A", True

        start_dt = parse_date_flexible(start_date_str)
        if not start_dt:
            return "نامشخص", "N/A", True

        expiry_dt_utc = start_dt + timedelta(days=package_days)

    # بررسی انقضا بر اساس زمان فعلی
    if not is_expired and now > expiry_dt_utc:
        is_expired = True

    # تبدیل به تاریخ شمسی
    expire_j = "N/A"
    if jdatetime:
        try:
            local_expiry_dt = expiry_dt_utc.astimezone()
            expire_j = jdatetime.date.fromgregorian(date=local_expiry_dt.date()).strftime('%Y/%m/%d')
        except Exception:
            pass

    status_text = "🔴 منقضی شده" if is_expired else "🟢 فعال"
    return status_text, expire_j, is_expired

def is_valid_sqlite(filepath: str) -> bool:
    """بررسی معتبر بودن فایل SQLite"""
    try:
        with sqlite3.connect(filepath) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            result = cur.fetchone()
        return result and result[0] == 'ok'
    except sqlite3.DatabaseError:
        return False