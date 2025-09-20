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


def _normalize_host(host: str) -> str:
    """
    - اگر scheme ندارد، https:// اضافه می‌کنیم
    - اسلش پایانی را حذف می‌کنیم
    """
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
    """
    SUB_DOMAINS ممکن است رشته یا لیست باشد؛ خروجی لیست hostname بدون scheme
    """
    if isinstance(sd, str):
        parts = [p.strip() for p in sd.split(",") if p.strip()]
    else:
        parts = [str(x).strip() for x in (sd or []) if str(x).strip()]
    return [_strip_scheme(p) for p in parts]


SUB_DOMAINS = _normalize_subdomains(SUB_DOMAINS)


def _get_base_url() -> str:
    """
    URL پایه API. PANEL_DOMAIN را در config ست کنید.
    اگر خالی بود، سعی با SUB_DOMAINS[0]؛ در نهایت فقط برای جلوگیری از کرش به localhost می‌افتد.
    """
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


# سازگاری با buy.py
def _compensate_days(days: int) -> int:
    return int(days)


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


# --------- Helpers for fallback reset ---------
def _now_ts() -> int:
    return int(time.time())

def _to_float_ts(x) -> Optional[float]:
    try:
        v = float(x)
        return v/1000.0 if v > 1e12 else v
    except Exception:
        return None

def _calc_start_ts(info: Dict[str, Any]) -> Optional[int]:
    """
    تلاش برای به‌دست‌آوردن زمان شروع دوره از پاسخ پنل:
    - last_reset_time
    - start_date
    - یا از روی expire - package_days*86400
    """
    for key in ("last_reset_time", "start_date"):
        v = _to_float_ts(info.get(key))
        if v is not None:
            return int(v)
    exp = _to_float_ts(info.get("expire"))
    try:
        pkg_days = int(float(info.get("package_days") or 0))
    except Exception:
        pkg_days = 0
    if exp is not None and pkg_days > 0:
        return int(exp - pkg_days * 86400)
    return None

async def _bump_days_to_now(user_uuid: str, plan_days: int, plan_gb: Optional[float]) -> Optional[Dict[str, Any]]:
    """
    اگر پنل start/last_reset را تغییر نداد، با بزرگ کردن package_days کاری می‌کنیم
    که expiry ≈ now + plan_days شود.
    """
    try:
        info = await get_user_info(user_uuid)
        if not info:
            return None
        start_ts = _calc_start_ts(info)
        if start_ts is None:
            return None
        now = _now_ts()
        elapsed = max(0, now - start_ts)
        elapsed_days = int(elapsed // 86400)
        if elapsed_days <= 0:
            return None
        target_days = int(plan_days) + elapsed_days

        endpoint = f"{_get_base_url()}user/{user_uuid}/"
        payload = {"package_days": target_days}
        if plan_gb is not None:
            try:
                payload["usage_limit_GB"] = float(plan_gb)
            except Exception:
                pass

        resp = await _make_request("patch", endpoint, json=payload)
        if resp is None or resp.get("_not_found"):
            return None

        # verify
        after = await get_user_info(user_uuid)
        if after and int(after.get("package_days", -1)) >= target_days:
            logger.info("Package days bumped to %s for %s to simulate reset-from-now.", target_days, user_uuid)
            return after
    except Exception as e:
        logger.warning("bump_days_to_now failed for %s: %s", user_uuid, e)
    return None
# ----------------------------------------------


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
    if not data or not data.get("uuid"):
        logger.error("create_hiddify_user (step 1 - POST): failed or UUID missing")
        return None

    user_uuid = data.get("uuid")

    # مرحله ۲: اعمال پلن
    logger.info("User %s created. Now applying plan details via PATCH...", user_uuid)
    update_success = await _apply_and_verify_plan(user_uuid, plan_days, plan_gb)
    if not update_success:
        logger.error("create_hiddify_user (step 2 - PATCH): Failed to apply plan details to user %s. Deleting user.", user_uuid)
        await delete_user_from_panel(user_uuid)
        return None

    # ساخت لینک سابسکریپشن با الگوی .../sub/ (بدون asn)
    sub_host = _strip_scheme(random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN)
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

    for idx, cand in enumerate(candidates, start=1):
        payload = {"package_days": exact_days, "current_usage_GB": 0}
        if cand != "OMIT":
            payload["usage_limit_GB"] = cand
            show = "null" if cand is None else str(cand)
        else:
            show = "OMIT"

        logger.info("Trying unlimited strategy %d/%d: usage_limit_GB=%s", idx, len(candidates), show)
        resp = await _make_request("patch", endpoint, json=payload)
        if resp is None or resp.get("_not_found"):
            logger.warning("Unlimited strategy %s: PATCH failed (skipping).", show)
            continue

        for attempt in range(VERIFICATION_RETRIES):
            await asyncio.sleep(VERIFICATION_DELAY)
            after_info = await get_user_info(user_uuid)
            if not after_info:
                continue

            after_days = int(after_info.get("package_days", -1))
            after_gb_raw = after_info.get("usage_limit_GB", None)

            if after_days == exact_days and _is_unlimited_value(after_gb_raw):
                logger.info("Unlimited strategy '%s' verified on attempt %d.", show, attempt + 1)
                return after_info

        logger.warning("Unlimited strategy '%s' did not verify; trying next.", show)

    # Fallback: بزرگ‌کردن روزها تا expiry ≈ now + days
    logger.info("Unlimited fallback: bumping package_days to simulate reset-from-now.")
    bumped = await _bump_days_to_now(user_uuid, exact_days, None)
    if bumped:
        return bumped

    logger.error("All unlimited strategies failed for user %s.", user_uuid)
    return None


async def _set_large_quota(user_uuid: str, exact_days: int, large_gb: float) -> Optional[Dict[str, Any]]:
    """
    نامحدود به‌صورت سقف حجمی بزرگ (مثلاً 1000GB).
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    large_gb = float(large_gb)
    payload = {
        "package_days": exact_days,
        "usage_limit_GB": large_gb,
        "current_usage_GB": 0,
    }
    resp = await _make_request("patch", endpoint, json=payload)
    if resp is None or resp.get("_not_found"):
        logger.error("Large-quota PATCH failed for UUID %s", user_uuid)
        # Fallback
        bumped = await _bump_days_to_now(user_uuid, exact_days, large_gb)
        return bumped

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
        ):
            logger.info("Large-quota unlimited (%.0f GB) verified for UUID %s on attempt %d.", large_gb, user_uuid, attempt + 1)
            return after_info

    # Fallback: bump days
    logger.info("Large-quota fallback: bumping package_days to simulate reset-from-now.")
    return await _bump_days_to_now(user_uuid, exact_days, large_gb)


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
    payload = {
        "package_days": exact_days,
        "usage_limit_GB": usage_limit_gb,
        "current_usage_GB": 0,
    }

    response = await _make_request("patch", endpoint, json=payload)
    if response is None or response.get("_not_found"):
        logger.error("Renew/update PATCH request failed for UUID %s", user_uuid)
        # Fallback bump
        return await _bump_days_to_now(user_uuid, exact_days, usage_limit_gb)

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

        if after_days == exact_days and after_gb is not None and abs(after_gb - usage_limit_gb) < 1e-6:
            logger.info("Update for UUID %s verified successfully on attempt %d.", user_uuid, attempt + 1)
            return after_info

        logger.warning(
            "Verification attempt %d for UUID %s failed. Expected (days:%s, gb:%s), Got (days:%s, gb:%s)",
            attempt + 1, user_uuid, exact_days, usage_limit_gb, after_days, after_gb_raw
        )

    # Fallback: bump days
    logger.info("Volume fallback: bumping package_days to simulate reset-from-now.")
    return await _bump_days_to_now(user_uuid, exact_days, usage_limit_gb)


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