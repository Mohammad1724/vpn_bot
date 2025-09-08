# filename: hiddify_api.py
# (کل فایل - اصلاح شده)

import asyncio
import httpx
import uuid
import random
import logging
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH, PANEL_SECRET_UUID, HIDDIFY_API_VERIFY_SSL
except ImportError:
    from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH
    PANEL_SECRET_UUID = ""
    HIDDIFY_API_VERIFY_SSL = True

try:
    from config import DEFAULT_ASN
except Exception:
    DEFAULT_ASN = "MCI"

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0
VERIFICATION_RETRIES = 5  # تعداد تلاش برای تایید
VERIFICATION_DELAY = 1.0  # تاخیر بین هر تلاش برای تایید (ثانیه)


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
) -> Optional[Dict[str, Any]]:

    endpoint = _get_base_url() + "user/"
    random_suffix = uuid.uuid4().hex[:4]
    base_name = custom_name if custom_name else f"tg-{user_telegram_id.split(':')[-1]}"
    unique_user_name = f"{base_name}-{random_suffix}"

    # مرحله ۱: ساخت کاربر با حداقل اطلاعات
    payload_create = {
        "name": unique_user_name,
        "comment": user_telegram_id,
    }

    data = await _make_request("post", endpoint, json=payload_create)
    if not data or not data.get("uuid"):
        logger.error("create_hiddify_user (step 1 - POST): failed or UUID missing")
        return None

    user_uuid = data.get("uuid")

    # مرحله ۲: بلافاصله کاربر ساخته شده را با پلن صحیح آپدیت می‌کنیم
    logger.info("User %s created. Now applying plan details via PATCH...", user_uuid)
    update_success = await _apply_and_verify_plan(user_uuid, plan_days, plan_gb)

    if not update_success:
        logger.error("create_hiddify_user (step 2 - PATCH): Failed to apply plan details to user %s. Deleting user.", user_uuid)
        await delete_user_from_panel(user_uuid)
        return None

    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    client_secret = str(PANEL_SECRET_UUID or "").strip().strip("/")

    if not client_secret:
        logger.error("PANEL_SECRET_UUID is not set in config.py! Subscription links will be incorrect.")
        sub_path = str(SUB_PATH or "sub").strip().strip("/")
        full_link = f"https://{sub_domain}/{sub_path}/{user_uuid}/"
    else:
        full_link = f"https://{sub_domain}/{client_secret}/{user_uuid}/sub/"

    return {"full_link": full_link, "uuid": user_uuid, "name": unique_user_name}


async def get_user_info(user_uuid: str) -> Optional[Dict[str, Any]]:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    return await _make_request("get", endpoint)


async def _apply_and_verify_plan(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    """
    یک پلن را روی کاربر اعمال می‌کند و با چند بار تلاش، صحت آن را تایید می‌کند.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"

    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0

    # حذف جبران روز - ارسال مقدار دقیق
    payload = {
        "package_days": int(plan_days),
        "usage_limit_GB": usage_limit_gb,
        "current_usage_GB": 0,
    }

    response = await _make_request("patch", endpoint, json=payload)
    if response is None or response.get("_not_found"):
        logger.error("Renew/update PATCH request failed for UUID %s", user_uuid)
        return None

    # **منطق تأیید نهایی و دقیق با حلقه و تأخیر**
    for attempt in range(VERIFICATION_RETRIES):
        await asyncio.sleep(VERIFICATION_DELAY)
        after_info = await get_user_info(user_uuid)

        if not after_info:
            logger.warning("Verification attempt %d: could not get user info.", attempt + 1)
            continue

        after_days = int(after_info.get("package_days", -1))
        after_gb = float(after_info.get("usage_limit_GB", -1))

        if after_days == int(plan_days) and after_gb == usage_limit_gb:
            logger.info("Update for UUID %s verified successfully on attempt %d.", user_uuid, attempt + 1)
            return after_info

        logger.warning(
            "Verification attempt %d for UUID %s failed. Expected (days:%s, gb:%s), Got (days:%s, gb:%s)",
            attempt + 1, user_uuid, int(plan_days), usage_limit_gb, after_days, after_gb
        )

    logger.error("Verification failed for UUID %s after %d attempts.", user_uuid, VERIFICATION_RETRIES)
    return None


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    """
    تمدید سرویس کاربر (که حالا از تابع مشترک _apply_and_verify_plan استفاده می‌کند).
    """
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