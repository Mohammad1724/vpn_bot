# -*- coding: utf-8 -*-

import asyncio
import httpx
import uuid
import random
import logging
from typing import Optional, Dict, Any

try:
    from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH, PANEL_SECRET_UUID, HIDDIFY_API_VERIFY_SSL
except ImportError:
    from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH
    PANEL_SECRET_UUID = ""
    HIDDIFY_API_VERIFY_SSL = True

# استراتژی نامحدود و اندازه سقف حجمی (قابل تنظیم در config.py)
try:
    from config import HIDDIFY_UNLIMITED_STRATEGY
except Exception:
    HIDDIFY_UNLIMITED_STRATEGY = "large_quota"  # "large_quota" یا "auto"

try:
    from config import HIDDIFY_UNLIMITED_LARGE_GB
except Exception:
    HIDDIFY_UNLIMITED_LARGE_GB = 1000.0

# برای حالت auto (نامحدود واقعی): -1 یا 0 یا "null" یا "omit" یا None (خودکار)
try:
    from config import HIDDIFY_UNLIMITED_VALUE
except Exception:
    HIDDIFY_UNLIMITED_VALUE = None  # auto-try

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0
VERIFICATION_RETRIES = 5
VERIFICATION_DELAY = 1.0


def _get_base_url() -> str:
    clean_admin = str(ADMIN_PATH or "").strip().strip("/")
    return f"https://{PANEL_DOMAIN}/{clean_admin}/api/v2/admin/"


def _get_api_headers() -> dict:
    return {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=HIDDIFY_API_VERIFY_SSL, follow_redirects=True)


def _normalize_unlimited_value(val):
    """
    HIDDIFY_UNLIMITED_VALUE می‌تواند:
      - عددی (مثل -1 یا 0)
      - "null" -> ارسال null
      - "omit" -> اصلاً usage_limit_GB ارسال نشود
      - None -> عدم ترجیح (auto)
    """
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
    """
    هر مقدار None یا <= 0 را «نامحدود» در نظر می‌گیریم.
    """
    if x is None:
        return True
    try:
        return float(x) <= 0.0
    except Exception:
        return False


# برای سازگاری با buy.py
def _compensate_days(days: int) -> int:
    # قبلاً 30 -> 32 بود؛ الان بدون تغییر.
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


async def create_hiddify_user(
    plan_days: int,
    plan_gb: float,
    user_telegram_id: str,
    custom_name: str = "",
    server_name: Optional[str] = None,
    **kwargs,  # پذیرش پارامترهای اضافه بدون خطا
) -> Optional[Dict[str, Any]]:

    endpoint = _get_base_url() + "user/"

    # ساخت نام کاربر: custom_name > server_name > tg-id
    random_suffix = uuid.uuid4().hex[:4]
    tg_part = (user_telegram_id or "").split(":")[-1] or "user"
    if custom_name:
        base_name = str(custom_name)
    elif server_name:
        base_name = str(server_name)
    else:
        base_name = f"tg-{tg_part}"
    unique_user_name = f"{base_name}-{random_suffix}"

    # کامنت: اطلاعات تلگرام + برچسب سرور (در صورت وجود)
    comment = user_telegram_id or ""
    if server_name:
        safe_srv = str(server_name)[:32]
        if "|srv:" not in comment:
            comment = f"{comment}|srv:{safe_srv}" if comment else f"srv:{safe_srv}"

    # مرحله ۱: ساخت کاربر
    payload_create = {
        "name": unique_user_name,
        "comment": comment,
    }

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

    # ساخت لینک سابسکریپشن
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    client_secret = str(PANEL_SECRET_UUID or "").strip().strip("/")

    if not client_secret:
        logger.error("PANEL_SECRET_UUID is not set in config.py! Subscription links will be incorrect.")
        sub_path = str(SUB_PATH or "sub").strip().strip("/")
        full_link = f"https://{sub_domain}/{sub_path}/{user_uuid}/"
    else:
        full_link = f"https://{sub_domain}/{client_secret}/{user_uuid}/sub/"

    return {"full_link": full_link, "uuid": user_uuid, "name": unique_user_name}


async def get_user_info(user_uuid: str, server_name: Optional[str] = None, **kwargs) -> Optional[Dict[str, Any]]:
    """
    server_name و سایر پارامترهای اضافی را برای سازگاری می‌پذیرد (نادیده گرفته می‌شوند).
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    return await _make_request("get", endpoint)


async def _try_set_unlimited(user_uuid: str, exact_days: int) -> Optional[Dict[str, Any]]:
    """
    حالت auto: چند استراتژی مختلف را برای نامحدود واقعی امتحان می‌کنیم.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    pref = _normalize_unlimited_value(HIDDIFY_UNLIMITED_VALUE)

    # لیست کاندیدها با توجه به ترجیح کاربر
    candidates = []
    if pref == "OMIT":
        candidates.append("OMIT")
    elif pref is None:
        candidates.append(None)
    elif isinstance(pref, (int, float)):
        candidates.append(float(pref))

    # سایر گزینه‌ها (بدون تکرار)
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

        # تایید بعد از هر تلاش
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

    logger.error("All unlimited strategies failed for user %s.", user_uuid)
    return None


async def _set_large_quota(user_uuid: str, exact_days: int, large_gb: float) -> Optional[Dict[str, Any]]:
    """
    نامحدود به‌صورت «سقف حجمی بزرگ» (مثلاً 1000GB).
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
        return None

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

        # اگر پنل خودش نامحدود کرد، یا دقیقاً large_gb ست شد، قبول
        if after_days == exact_days and (
            _is_unlimited_value(after_gb_raw) or (after_gb is not None and abs(after_gb - large_gb) < 1e-6)
        ):
            logger.info("Large-quota unlimited (%.0f GB) verified for UUID %s on attempt %d.", large_gb, user_uuid, attempt + 1)
            return after_info

    logger.error("Large-quota unlimited verification failed for UUID %s", user_uuid)
    return None


async def _apply_and_verify_plan(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    """
    اعمال پلن + تایید چندباره.
    نامحدود:
      - اگر HIDDIFY_UNLIMITED_STRATEGY == "auto": تلاش برای نامحدود واقعی؛ در صورت عدم موفقیت، large_quota.
      - اگر "large_quota": مستقیم large_quota.
    """
    exact_days = int(plan_days)

    # حالت نامحدود
    if plan_gb is None or float(plan_gb) <= 0.0:
        if str(HIDDIFY_UNLIMITED_STRATEGY).lower() == "auto":
            info = await _try_set_unlimited(user_uuid, exact_days)
            if info:
                return info
        return await _set_large_quota(user_uuid, exact_days, HIDDIFY_UNLIMITED_LARGE_GB)

    # حالت حجمی (غیر نامحدود)
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
        return None

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

    logger.error("Verification failed for UUID %s after %d attempts.", user_uuid, VERIFICATION_RETRIES)
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