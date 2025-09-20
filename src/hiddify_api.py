# filename: hiddify_api.py
# -*- coding: utf-8 -*-

import asyncio
import httpx
import uuid
import random
import logging
import types
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# --- Robust config loader ---
try:
    import config as _cfg
except Exception:
    _cfg = types.SimpleNamespace()

PANEL_DOMAIN = getattr(_cfg, "PANEL_DOMAIN", "")
ADMIN_PATH = getattr(_cfg, "ADMIN_PATH", "")
API_KEY = getattr(_cfg, "API_KEY", "")
SUB_DOMAINS = getattr(_cfg, "SUB_DOMAINS", []) or []
SUB_PATH = getattr(_cfg, "SUB_PATH", "sub")
PANEL_SECRET_UUID = getattr(_cfg, "PANEL_SECRET_UUID", "")
HIDDIFY_API_VERIFY_SSL = getattr(_cfg, "HIDDIFY_API_VERIFY_SSL", True)
DEFAULT_ASN = getattr(_cfg, "DEFAULT_ASN", "MCI")

# Unlimited strategy
HIDDIFY_UNLIMITED_STRATEGY = getattr(_cfg, "HIDDIFY_UNLIMITED_STRATEGY", "large_quota")  # "large_quota" | "auto"
HIDDIFY_UNLIMITED_LARGE_GB = float(getattr(_cfg, "HIDDIFY_UNLIMITED_LARGE_GB", 1000.0))
HIDDIFY_UNLIMITED_VALUE = getattr(_cfg, "HIDDIFY_UNLIMITED_VALUE", None)  # -1 | 0 | "null" | "omit" | None

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0
VERIFICATION_RETRIES = 5
VERIFICATION_DELAY = 1.0

# زمان مجاز برای نزدیک بودن reset به «الان»
RESET_TOLERANCE_SEC = 6 * 3600  # 6 hours


def _normalize_host(host: str) -> str:
    h = (host or "").strip()
    if not h:
        return ""
    if not (h.startswith("http://") or h.startswith("https://")):
        h = "https://" + h
    return h.rstrip("/")


def _strip_scheme(host: str) -> str:
    h = (host or "").strip()
    if h.startswith("https://"):
        h = h[len("https://"):]
    elif h.startswith("http://"):
        h = h[len("http://"):]
    return h.strip("/")


def _normalize_subdomains(sd):
    if isinstance(sd, str):
        parts = [p.strip() for p in sd.split(",") if p.strip()]
    else:
        parts = [str(x).strip() for x in (sd or []) if str(x).strip()]
    return [_strip_scheme(p) for p in parts]


SUB_DOMAINS = _normalize_subdomains(SUB_DOMAINS)


def _get_base_url() -> str:
    base = _normalize_host(PANEL_DOMAIN)
    if not base:
        alt = _normalize_host(SUB_DOMAINS[0] if SUB_DOMAINS else "")
        if alt:
            logger.warning("PANEL_DOMAIN is empty; falling back to %s for API base URL", alt)
            base = alt
        else:
            logger.error("PANEL_DOMAIN and SUB_DOMAINS are empty. Please set PANEL_DOMAIN in config.py.")
            base = "https://localhost"

    clean_admin = str(ADMIN_PATH or "").strip().strip("/")
    if clean_admin:
        return f"{base}/{clean_admin}/api/v2/admin/"
    return f"{base}/api/v2/admin/"


def _get_api_headers() -> dict:
    return {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=HIDDIFY_API_VERIFY_SSL, follow_redirects=True)


def _normalize_unlimited_value(val):
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("omit", "skip", "remove"):
            return "OMIT"
        if s in ("null", "none"):
            return None
        try:
            return float(val)
        except Exception:
            return 0.0
    try:
        return float(val)
    except Exception:
        return 0.0


def _is_unlimited_value(x) -> bool:
    if x is None:
        return True
    try:
        return float(x) <= 0.0
    except Exception:
        return False


def _compensate_days(days: int) -> int:
    return int(days)


def _now_ts() -> int:
    return int(time.time())


def _now_local_strings():
    """
    خروجی:
    - date_str: YYYY-MM-DD (برای start_date)
    - dt_str: YYYY-MM-DD HH:MM:SS (برای last_reset_time)
    - now_sec: timestamp ثانیه‌ای
    """
    now_sec = int(time.time())
    local = time.localtime(now_sec)
    date_str = time.strftime("%Y-%m-%d", local)
    dt_str = time.strftime("%Y-%m-%d %H:%M:%S", local)
    return date_str, dt_str, now_sec


def _to_sec_ts(v) -> Optional[int]:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            val = float(v)
            if val > 1e12:
                val = val / 1000.0
            return int(val)
        s = str(v).strip()
        # اگر عددی بود
        try:
            val = float(s)
            if val > 1e12:
                val = val / 1000.0
            return int(val)
        except Exception:
            pass
        # تلاش برای ISO
        try:
            iso = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                return int(time.mktime(dt.timetuple()))
            return int(dt.timestamp())
        except Exception:
            pass
        # فرمت‌های رایج
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                return int(time.mktime(dt.timetuple()))
            except Exception:
                continue
    except Exception:
        return None
    return None


def _is_reset_applied(after_info: Dict[str, Any], exact_days: int, ref_ts_sec: int) -> bool:
    """
    بررسی اینکه شروع دوره/انقضا واقعاً از 'الان' ریست شده باشد.
    یا expire ≈ now + exact_days یا start_date/last_reset_time ≈ now (با تلورانس زمانی).
    """
    try:
        # 1) expire keys
        for key in ("expire", "expiry", "expire_time"):
            ts = _to_sec_ts(after_info.get(key))
            if ts:
                days_delta = (ts - ref_ts_sec) / 86400.0
                if days_delta >= (exact_days - 1):
                    return True
        # 2) start/last_reset/created
        for key in ("start_date", "last_reset_time", "created_at", "create_time"):
            ts = _to_sec_ts(after_info.get(key))
            if ts and abs(ts - ref_ts_sec) <= RESET_TOLERANCE_SEC:
                return True
    except Exception:
        pass
    return False


async def _make_request(method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
    headers = kwargs.pop("headers", _get_api_headers())
    delay = BASE_RETRY_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with await _make_client(timeout=kwargs.get("timeout", 20.0)) as client:
                resp = await getattr(client, method.lower())(url, headers=headers, **kwargs)
                resp.raise_for_status()
                try:
                    return resp.json()
                except ValueError:
                    return {}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            text = e.response.text if e.response is not None else str(e)
            if status == 500 and "404 Not Found" in text:
                logger.warning("Treating 500 error with '404 Not Found' message as a 404 for URL %s", url)
                return {"_not_found": True}
            if status == 404:
                return {"_not_found": True}
            if status in (401, 403, 422):
                logger.error("%s to %s failed with %s: %s", method.upper(), url, status, text)
                break
            logger.warning("%s to %s failed with %s: %s (retry %d/%d)", method.upper(), url, status, text, attempt, MAX_RETRIES)
        except Exception as e:
            logger.error("%s to %s failed: %s", method.upper(), url, e, exc_info=True)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(delay)
            delay *= 2
    return None


async def create_hiddify_user(
    plan_days: int,
    plan_gb: float,
    user_telegram_id: str,
    custom_name: str = "",
    server_name: Optional[str] = None,
    **kwargs,
) -> Optional[Dict[str, Any]]:

    endpoint = _get_base_url() + "user/"

    # ساخت نام: custom_name > server_name > tg-id
    random_suffix = uuid.uuid4().hex[:4]
    tg_part = (user_telegram_id or "").split(":")[-1] or "user"
    if custom_name:
        base_name = str(custom_name)
    elif server_name:
        base_name = str(server_name)
    else:
        base_name = f"tg-{tg_part}"
    unique_user_name = f"{base_name}-{random_suffix}"

    # کامنت: اطلاعات تلگرام + سرور
    comment = user_telegram_id or ""
    if server_name:
        safe_srv = str(server_name)[:32]
        if "|srv:" not in comment:
            comment = f"{comment}|srv:{safe_srv}" if comment else f"srv:{safe_srv}"

    # مرحله ۱: ساخت کاربر
    payload_create = {"name": unique_user_name, "comment": comment}
    data = await _make_request("post", endpoint, json=payload_create)
    if not data:
        logger.error("create_hiddify_user (step 1 - POST): request failed (no data)")
        return None
    # برخی پنل‌ها uuid را داخل کلید user برمی‌گردانند
    user_uuid = data.get("uuid") if isinstance(data, dict) else None
    if not user_uuid and isinstance(data, dict):
        user_uuid = (data.get("user") or {}).get("uuid")
    if not user_uuid:
        logger.error("create_hiddify_user (step 1 - POST): UUID missing in response: %s", data)
        return None

    # مرحله ۲: اعمال پلن
    logger.info("User %s created. Now applying plan details via PATCH...", user_uuid)
    update_success = await _apply_and_verify_plan(user_uuid, plan_days, plan_gb)
    if not update_success:
        logger.error("create_hiddify_user (step 2 - PATCH): Failed to apply plan details to user %s. Deleting user.", user_uuid)
        await delete_user_from_panel(user_uuid)
        return None

    # ساخت لینک سابسکریپشن با الگوی .../sub/ (بدون asn)
    sub_host = _strip_scheme(random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN)
    if not sub_host:
        sub_host = "localhost"
    client_secret = str(PANEL_SECRET_UUID or "").strip().strip("/")

    if not client_secret:
        sub_path = str(SUB_PATH or "sub").strip().strip("/")
        full_link = f"https://{sub_host}/{sub_path}/{user_uuid}/"
    else:
        full_link = f"https://{sub_host}/{client_secret}/{user_uuid}/sub/"

    return {"full_link": full_link, "uuid": user_uuid, "name": unique_user_name}


async def get_user_info(user_uuid: str, server_name: Optional[str] = None, **kwargs) -> Optional[Dict[str, Any]]:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    return await _make_request("get", endpoint)


async def _try_set_unlimited(user_uuid: str, exact_days: int) -> Optional[Dict[str, Any]]:
    """
    حالت auto: چند استراتژی مختلف برای نامحدود واقعی.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    pref = _normalize_unlimited_value(HIDDIFY_UNLIMITED_VALUE)

    candidates = []
    if pref == "OMIT":
        candidates.append("OMIT")
    elif pref is None:
        candidates.append(None)
    elif isinstance(pref, (int, float)):
        candidates.append(float(pref))

    for c in [None, 0.0, -1.0, "OMIT"]:
        if c not in candidates:
            candidates.append(c)

    date_str, dt_str, now_sec = _now_local_strings()
    # فقط قالب‌های معتبر برای پنل: start_date = YYYY-MM-DD و last_reset_time = "YYYY-MM-DD HH:MM:SS"
    time_variants = [
        ("last_reset_time", dt_str),
        ("start_date", date_str),
        ("last_reset_time", now_sec),  # برخی پنل‌ها timestamp را هم قبول می‌کنند
    ]

    for idx, cand in enumerate(candidates, start=1):
        show = "OMIT" if cand == "OMIT" else ("null" if cand is None else str(cand))
        for tf, tv in time_variants:
            payload = {"package_days": exact_days, "current_usage_GB": 0, tf: tv}
            if cand != "OMIT":
                payload["usage_limit_GB"] = cand
            logger.info("Trying unlimited strategy %d/%d (%s=%s, usage_limit_GB=%s)", idx, len(candidates), tf, tv, show)
            resp = await _make_request("patch", endpoint, json=payload)
            if resp is None or (isinstance(resp, dict) and resp.get("_not_found")):
                continue

            ref_ts = _to_sec_ts(tv) or now_sec
            for attempt in range(VERIFICATION_RETRIES):
                await asyncio.sleep(VERIFICATION_DELAY)
                after_info = await get_user_info(user_uuid)
                if not after_info:
                    continue

                after_days = int(after_info.get("package_days", -1))
                after_gb_raw = after_info.get("usage_limit_GB", None)

                if after_days == exact_days and _is_unlimited_value(after_gb_raw) and _is_reset_applied(after_info, exact_days, ref_ts):
                    logger.info("Unlimited verified (tf=%s) on attempt %d.", tf, attempt + 1)
                    return after_info

            logger.warning("Unlimited verify failed for (tf=%s). Trying next variant.", tf)

    logger.error("All unlimited strategies failed for user %s.", user_uuid)
    return None


async def _set_large_quota(user_uuid: str, exact_days: int, large_gb: float) -> Optional[Dict[str, Any]]:
    """
    نامحدود به‌صورت سقف حجمی بزرگ (مثلاً 1000GB).
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    large_gb = float(large_gb)
    date_str, dt_str, now_sec = _now_local_strings()
    time_variants = [
        ("last_reset_time", dt_str),
        ("start_date", date_str),
        ("last_reset_time", now_sec),
    ]

    for tf, tv in time_variants:
        payload = {"package_days": exact_days, "usage_limit_GB": large_gb, "current_usage_GB": 0, tf: tv}
        resp = await _make_request("patch", endpoint, json=payload)
        if resp is None or (isinstance(resp, dict) and resp.get("_not_found")):
            continue

        ref_ts = _to_sec_ts(tv) or now_sec
        for attempt in range(VERIFICATION_RETRIES):
            await asyncio.sleep(VERIFICATION_DELAY)
            after_info = await get_user_info(user_uuid)
            if not after_info:
                continue

            after_days = int(after_info.get("package_days", -1))
            after_gb_raw = after_info.get("usage_limit_GB", None)
            try:
                after_gb = float(after_gb_raw)
            except Exception:
                after_gb = None

            if after_days == exact_days and (
                _is_unlimited_value(after_gb_raw) or (after_gb is not None and abs(after_gb - large_gb) < 1e-6)
            ) and _is_reset_applied(after_info, exact_days, ref_ts):
                logger.info("Large-quota (%.0f GB) verified (tf=%s) on attempt %d.", large_gb, tf, attempt + 1)
                return after_info

    logger.error("Large-quota unlimited verification failed for UUID %s", user_uuid)
    return None


async def _apply_and_verify_plan(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    exact_days = int(plan_days)

    if plan_gb is None or float(plan_gb) <= 0.0:
        if str(HIDDIFY_UNLIMITED_STRATEGY).lower() == "auto":
            info = await _try_set_unlimited(user_uuid, exact_days)
            if info:
                return info
        return await _set_large_quota(user_uuid, exact_days, HIDDIFY_UNLIMITED_LARGE_GB)

    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    usage_limit_gb = float(plan_gb)
    date_str, dt_str, now_sec = _now_local_strings()
    time_variants = [
        ("last_reset_time", dt_str),
        ("start_date", date_str),
        ("last_reset_time", now_sec),
    ]

    for tf, tv in time_variants:
        payload = {"package_days": exact_days, "usage_limit_GB": usage_limit_gb, "current_usage_GB": 0, tf: tv}
        response = await _make_request("patch", endpoint, json=payload)
        if response is None or (isinstance(response, dict) and response.get("_not_found")):
            continue

        ref_ts = _to_sec_ts(tv) or now_sec
        for attempt in range(VERIFICATION_RETRIES):
            await asyncio.sleep(VERIFICATION_DELAY)
            after_info = await get_user_info(user_uuid)
            if not after_info:
                continue

            after_days = int(after_info.get("package_days", -1))
            after_gb_raw = after_info.get("usage_limit_GB", None)
            try:
                after_gb = float(after_gb_raw)
            except Exception:
                after_gb = None

            if after_days == exact_days and after_gb is not None and abs(after_gb - usage_limit_gb) < 1e-6 and _is_reset_applied(after_info, exact_days, ref_ts):
                logger.info("Update verified for %s (tf=%s) on attempt %d.", user_uuid, tf, attempt + 1)
                return after_info

        logger.warning("Verification for %s failed with time field '%s'. Trying next variant.", user_uuid, tf)

    logger.error("Verification failed for UUID %s after trying all time variants.", user_uuid)
    return None


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    return await _apply_and_verify_plan(user_uuid, plan_days, plan_gb)


async def delete_user_from_panel(user_uuid: str) -> bool:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    data = await _make_request("delete", endpoint)
    if data == {}:
        return True
    if isinstance(data, dict) and data.get("_not_found"):
        return True
    if data is None:
        probe = await get_user_info(user_uuid)
        if isinstance(probe, dict) and probe.get("_not_found"):
            return True
    return False


async def check_api_connection() -> bool:
    try:
        endpoint = _get_base_url() + "user/?page=1&per_page=1"
        response = await _make_request("get", endpoint)
        return response is not None
    except Exception:
        return False