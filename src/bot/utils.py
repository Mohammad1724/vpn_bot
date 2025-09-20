# filename: bot/utils.py
# -*- coding: utf-8 -*-
import io
import sqlite3
import random
import logging
from typing import Union, Optional, Tuple
from datetime import datetime, timedelta, timezone
import math
import re
from urllib.parse import quote_plus, urlparse

import qrcode
import database as db

try:
    from config import PANEL_DOMAIN, SUB_DOMAINS, PANEL_SECRET_UUID, SUB_PATH
except ImportError:
    PANEL_DOMAIN, SUB_DOMAINS, PANEL_SECRET_UUID, SUB_PATH = "", [], "", "sub"

try:
    from config import UNLIMITED_DISPLAY_THRESHOLD_GB
except Exception:
    UNLIMITED_DISPLAY_THRESHOLD_GB = 900.0

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


def parse_date_flexible(date_str: Union[str, int, float]) -> Union[datetime, None]:
    if date_str is None or date_str == "":
        return None

    if isinstance(date_str, (int, float)) or (isinstance(date_str, str) and re.match(r"^\d+(\.\d+)?$", date_str.strip())):
        try:
            val = float(date_str)
            if val > 1e12:
                val = val / 1000.0
            return datetime.fromtimestamp(val, tz=timezone.utc).astimezone()
        except Exception:
            pass

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

    logger.error(f"Date parse failed for '{date_str}'.")
    return None


def _to_float(x, default=0.0) -> float:
    try:
        if x is None or (isinstance(x, str) and x.strip().lower() in ("", "none", "null", "nan")):
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def _to_int(x, default=0) -> int:
    try:
        if x is None or (isinstance(x, str) and x.strip().lower() in ("", "none", "null", "nan")):
            return int(default)
        return int(float(x))
    except Exception:
        return int(default)


def normalize_link_type(t: str) -> str:
    lt = (t or "sub").strip().lower().replace("clash-meta", "clashmeta")
    allowed = {"sub", "sub64", "singbox", "clash", "clashmeta", "xray"}
    return lt if lt in allowed else "sub"


def _clean_path(seg: Optional[str]) -> str:
    return (seg or "").strip().strip("/")


def _hostname_only(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s
    p = urlparse(s)
    return (p.netloc or "").strip()


def _normalize_subdomains(sd):
    if isinstance(sd, str):
        parts = [p.strip() for p in sd.split(",") if p.strip()]
    else:
        parts = [str(x).strip() for x in (sd or []) if str(x).strip()]
    return [_hostname_only(p) for p in parts]


def _parse_domains_csv(s: str) -> list[str]:
    return [h.strip() for h in (s or "").split(",") if h.strip()]


def _pick_domains_from_settings(plan_gb: int | None) -> list[str]:
    if plan_gb is not None:
        try:
            g = int(plan_gb)
        except Exception:
            g = None
        if g is not None and g <= 0:
            raw = db.get_setting("unlimited_sub_domains")
            if raw:
                return _normalize_subdomains(_parse_domains_csv(raw))
        elif g is not None and g > 0:
            raw = db.get_setting("volume_based_sub_domains")
            if raw:
                return _normalize_subdomains(_parse_domains_csv(raw))

    gen = db.get_setting("sub_domains")
    if gen:
        return _normalize_subdomains(_parse_domains_csv(gen))

    return _normalize_subdomains(SUB_DOMAINS) or [_hostname_only(PANEL_DOMAIN)]


def build_subscription_url(
    user_uuid: str,
    link_type: str | None = None,
    name: str | None = None,
    plan_gb: int | None = None
) -> str:
    domains = _pick_domains_from_settings(plan_gb)
    host = _hostname_only(random.choice(domains) if domains else PANEL_DOMAIN)

    if link_type is None:
        link_type = (db.get_setting("default_sub_link_type") or "sub").strip().lower()
    lt = normalize_link_type(link_type)

    client_secret = _clean_path(PANEL_SECRET_UUID)
    sub_path = _clean_path(SUB_PATH) or "sub"

    if client_secret:
        base = f"https://{host}/{client_secret}/{user_uuid}"
        if lt == "sub":
            final_url = f"{base}/sub/"
        else:
            final_url = f"{base}/{lt}/"
    else:
        if lt == "sub":
            final_url = f"https://{host}/{sub_path}/{user_uuid}/"
        else:
            final_url = f"https://{host}/{lt}/{user_uuid}/"

    if name:
        safe_name = quote_plus(name)
        if lt == "sub":
            final_url += f"#{safe_name}"
        else:
            sep = "&" if "?" in final_url else "?"
            final_url += f"{sep}name={safe_name}"

    return final_url


def make_qr_bytes(data: str) -> io.BytesIO:
    img = qrcode.make(data)
    bio = io.BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


def _get_panel_expire_dt(user_data: dict) -> Optional[datetime]:
    expire_ts = user_data.get("expire")
    if isinstance(expire_ts, (int, float, str)):
        try:
            val = float(expire_ts)
            if val > 1e12:
                val = val / 1000.0
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None
    return None


def _pick_start_dt(user_data: dict, service_db_record: Optional[dict], now: datetime) -> Optional[datetime]:
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

    candidates = [dt for dt in candidates if dt <= now + timedelta(hours=2)]
    if not candidates:
        return created_at_db

    return max(candidates)


def _format_expiry_and_days(user_data: dict, service_db_record: Optional[dict] = None) -> Tuple[str, int]:
    now_utc = datetime.now(timezone.utc)
    try:
        package_days = int(user_data.get("package_days") or 0)
    except Exception:
        package_days = 0

    expire_dt = _get_panel_expire_dt(user_data)
    days_left_via_expire = None
    if expire_dt:
        days_left_via_expire = max(0, math.ceil((expire_dt - now_utc).total_seconds() / (24 * 3600)))

    start_dt_candidate = _pick_start_dt(user_data, service_db_record, now_utc)
    if package_days > 0 and start_dt_candidate:
        alt_expire_dt = start_dt_candidate.astimezone(timezone.utc) + timedelta(days=package_days)
        alt_days_left = max(0, math.ceil((alt_expire_dt - now_utc).total_seconds() / (24 * 3600)))

        use_alt = False
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

    if not expire_dt and package_days > 0:
        expire_dt = now_utc + timedelta(days=package_days)
        days_left_via_expire = package_days

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


def create_progress_bar(used, total, blocks=10):
    if total <= 0:
        return "", 0
    ratio = min(1.0, used / total)
    percent = int(ratio * 100)
    filled = int(ratio * blocks)
    bar = "▰" * filled + "▱" * (blocks - filled)
    return bar, percent


def create_service_info_caption(
    hiddify_user_info: dict,
    service_db_record: dict,
    title: str = "اطلاعات سرویس شما",
    override_sub_url: str | None = None
) -> str:
    # پاس دادن رکورد DB برای محاسبه صحیح انقضا
    status, jalali_exp, is_expired = get_service_status(hiddify_user_info, service_db_record)

    usage_limit = _to_float(hiddify_user_info.get('usage_limit_GB'), 0.0)
    current_usage = _to_float(hiddify_user_info.get('current_usage_GB'), 0.0)

    bar, percent = create_progress_bar(current_usage, usage_limit)

    name = service_db_record.get('name') or hiddify_user_info.get('name') or "سرویس"

    link = override_sub_url or service_db_record.get('sub_link')
    safe_link_md = f"`{str(link).replace('`','\\`')}`" if link else "—"

    traffic_str = "نامحدود" if usage_limit <= 0 or usage_limit > UNLIMITED_DISPLAY_THRESHOLD_GB else f"{current_usage:.2f}/{int(usage_limit)} GB"

    caption = (
        f"{title}\n\n"
        f"🆔 {name}\n"
        f"⏳ {int(_to_int(hiddify_user_info.get('package_days'), 0))} روز | 📅 تا {jalali_exp}\n\n"
        f"📦 ترافیک: {traffic_str}\n"
        f"{bar} {percent}%\n\n"
        f"🔗 لینک اشتراک (با یک لمس کپی می‌شود):\n{safe_link_md}"
    )
    return caption


def get_service_status(hiddify_info: dict, service_db_record: Optional[dict] = None) -> Tuple[str, str, bool]:
    """
    خروجی: (متن وضعیت، تاریخ انقضا، منقضی است؟)
    با دریافت رکورد DB (اختیاری) created_at تازه را در محاسبه لحاظ می‌کند.
    """
    expire_jalali, days_left = _format_expiry_and_days(hiddify_info, service_db_record)
    is_expired = days_left <= 0
    status_field = str(hiddify_info.get('status') or '').lower()
    if status_field in ('disabled', 'limited'):
        is_expired = True

    usage_limit = _to_float(hiddify_info.get('usage_limit_GB'), 0.0)
    current_usage = _to_float(hiddify_info.get('current_usage_GB'), 0.0)
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