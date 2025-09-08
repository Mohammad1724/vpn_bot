import io
import sqlite3
import random
import logging
from typing import Union, Optional, Tuple
from datetime import datetime, timedelta, timezone
import math
import re

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
            # بازهٔ معقول یونیکس‌تایم به ثانیه
            if 946684800 <= ts <= 2145916800:
                return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
            # اگر میلی‌ثانیه بود
            if ts > 1_000_000_000_000:
                return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).astimezone()
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


def _get_panel_expire_dt(user_data: dict) -> Optional[datetime]:
    """
    فقط اگر فیلد expire وجود داشته باشد و معتبر باشد، تاریخ انقضا را از آن می‌سازد.
    (به ثانیه یا میلی‌ثانیه)
    """
    expire_ts = user_data.get("expire")
    if isinstance(expire_ts, (int, float, str)):
        try:
            val = float(expire_ts)
            # میلی‌ثانیه؟
            if val > 1e12:
                val = val / 1000.0
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None
    return None


def _pick_start_dt(user_data: dict, service_db_record: Optional[dict], now: datetime) -> Optional[datetime]:
    """
    انتخاب بهترین تاریخ شروع برای محاسبه انقضا/روزهای باقیمانده:
    - اگر created_at در DB وجود داشته باشد و سرویس «تازه» باشد (<= 36 ساعت)، همان را مبنا می‌گیریم.
    - در غیر این صورت، از جدیدترین مقدار بین last_reset_time، start_date، created_at/create_time (از پنل) استفاده می‌کنیم.
    - اگر هیچکدام نبود، None.
    """
    created_at_db = None
    if service_db_record:
        ca = service_db_record.get("created_at") or service_db_record.get("create_time")
        if ca:
            created_at_db = parse_date_flexible(ca)

    fresh_hours = 36
    is_fresh = created_at_db is not None and 0 <= (now - created_at_db).total_seconds() <= fresh_hours * 3600

    if is_fresh:
        return created_at_db

    candidates = []
    for key in ("last_reset_time", "start_date", "created_at", "create_time"):
        val = user_data.get(key)
        if val:
            dt = parse_date_flexible(val)
            if dt:
                candidates.append(dt)

    # اگر تاریخ‌های پنل در آینده بودند، کنار بگذار
    candidates = [dt for dt in candidates if dt <= now + timedelta(hours=2)]

    if not candidates:
        return created_at_db  # شاید created_at_db داریم ولی تازه نیست

    return max(candidates)


def _format_expiry_and_days(user_data: dict, service_db_record: Optional[dict] = None) -> Tuple[str, int]:
    """
    محاسبه تاریخ نمایش و روزهای باقیمانده با رویکرد مقاوم:
    - اگر expire معتبر از پنل داریم و عدد معقولی می‌دهد، همان مبناست.
    - اگر سرویس تازه ساخته شده و عدد روزهای باقیمانده از پنل کمتر از مدت پلن بود،
      از created_at دیتابیس برای شروع استفاده می‌کنیم تا بلافاصله پس از خرید، باقیمانده=مدت پلن شود.
    - در غیر این صورت از جدیدترین start/last_reset در پنل استفاده می‌کنیم.
    """
    now_utc = datetime.now(timezone.utc)
    package_days_raw = user_data.get("package_days", 0)
    try:
        package_days = int(package_days_raw or 0)
    except Exception:
        package_days = 0

    # گزینه 1: expire مستقیم از پنل
    expire_dt = _get_panel_expire_dt(user_data)
    days_left_via_expire = None
    if expire_dt:
        if expire_dt > now_utc:
            days_left_via_expire = math.ceil((expire_dt - now_utc).total_seconds() / (24 * 3600))
        else:
            days_left_via_expire = 0

    # اگر سرویس تازه است و باقیمانده پنل به‌وضوح کمتر از مدت پلن است، از created_at استفاده کن
    start_dt_candidate = _pick_start_dt(user_data, service_db_record, now_utc)
    if package_days > 0 and start_dt_candidate:
        alt_expire_dt = start_dt_candidate.astimezone(timezone.utc) + timedelta(days=package_days)
        alt_days_left = max(0, math.ceil((alt_expire_dt - now_utc).total_seconds() / (24 * 3600)))

        use_alt = False
        # معیار انتخاب جایگزین:
        # - اگر days_left_via_expire وجود ندارد
        # - یا اگر سرویس تازه (بر اساس created_at DB) بوده و اختلاف قابل‌توجه است (کمتر از مدت-2)
        # - یا اگر عدد پنل غیرمنطقی باشد (منفی/بیش از مدت پلن + 2)
        created_at_db = None
        if service_db_record:
            ca = service_db_record.get("created_at") or service_db_record.get("create_time")
            if ca:
                created_at_db = parse_date_flexible(ca)
        is_fresh = created_at_db is not None and 0 <= (now_utc - created_at_db.astimezone(timezone.utc)).total_seconds() <= 36 * 3600

        if days_left_via_expire is None:
            use_alt = True
        elif is_fresh and (days_left_via_expire < max(0, package_days - 2)):
            use_alt = True
        elif days_left_via_expire > package_days + 2:
            use_alt = True

        if use_alt:
            expire_dt = alt_expire_dt
            days_left_via_expire = alt_days_left

    # اگر هنوز تاریخ نداریم ولی package_days>0 داریم، از now به‌عنوان شروع استفاده کن
    if not expire_dt and package_days > 0:
        expire_dt = now_utc + timedelta(days=package_days)
        days_left_via_expire = package_days

    # تبدیل تاریخ برای نمایش
    expire_jalali = "نامشخص"
    if expire_dt:
        expire_local = expire_dt.astimezone()
        try:
            expire_jalali = (
                jdatetime.date.fromgregorian(date=expire_local.date()).strftime('%Y/%m/%d')
                if jdatetime else expire_local.strftime("%Y-%m-%d")
            )
        except Exception:
            expire_jalali = expire_local.strftime("%Y-%m-%d")

    return expire_jalali, int(days_left_via_expire or 0)


def create_service_info_caption(
    user_data: dict,
    service_db_record: Optional[dict] = None,
    title: str = "🎉 سرویس شما!",
    override_sub_url: Optional[str] = None
) -> str:
    used_gb = round(float(user_data.get('current_usage_GB', 0.0)), 2)
    total_gb = round(float(user_data.get('usage_limit_GB', 0.0)), 2)
    unlimited = (total_gb <= 0.0)

    expire_jalali, days_left = _format_expiry_and_days(user_data, service_db_record)
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

    package_days = int(user_data.get('package_days', 0) or 0)

    return (
        f"{title}\n"
        f"{service_name}\n\n"
        f"وضعیت: {status_text}\n"
        f"{traffic_line}\n"
        f"انقضا: {expire_jalali} | مدت: {package_days} روز | باقیمانده: {days_left} روز\n\n"
        f"لینک اشتراک:\n`{sub_url}`"
    )


def get_service_status(hiddify_info: dict) -> Tuple[str, str, bool]:
    expire_jalali, days_left = _format_expiry_and_days(hiddify_info, None)
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