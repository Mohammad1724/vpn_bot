# filename: hiddify_api.py
# (کل فایل)

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


def _compensate_days(days: int) -> int:
    """
    جبران خطای محاسبه روز در پنل.
    اگر پلن 30 روزه باشد، 32 روز ارسال می‌کنیم تا خروجی 30 روز شود.
    این تابع را می‌توانید برای پلن‌های دیگر نیز تنظیم کنید.
    """
    if days == 30:
        return 32
    # برای سایر پلن‌ها، همان مقدار اصلی را برمی‌گردانیم
    return days


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

    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0

    payload = {
        "name": unique_user_name,
        "package_days": _compensate_days(int(plan_days)),  # **اصلاح کلیدی برای خرید**
        "usage_limit_GB": usage_limit_gb,
        "comment": user_telegram_id,
        "current_usage_GB": 0,
    }

    data = await _make_request("post", endpoint, json=payload)
    if not data or not data.get("uuid"):
        logger.error("create_hiddify_user: failed or UUID missing (check PANEL_DOMAIN/ADMIN_PATH/API_KEY)")
        return None

    user_uuid = data.get("uuid")
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


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    
    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0

    before_info = await get_user_info(user_uuid)
    if not before_info or before_info.get("_not_found"):
        logger.error("Renew failed: user with UUID %s not found in panel.", user_uuid)
        return None

    compensated_days = _compensate_days(int(plan_days)) # **اصلاح کلیدی برای تمدید**
    payload = {
        "package_days": compensated_days,
        "usage_limit_GB": usage_limit_gb,
        "current_usage_GB": 0,
    }

    response = await _make_request("patch", endpoint, json=payload)
    if response is None or response.get("_not_found"):
        logger.error("Renew PATCH request failed or user not found for UUID %s", user_uuid)
        return None
    
    await asyncio.sleep(1)

    after_info = await get_user_info(user_uuid)
    if not after_info:
        logger.error("Renew verification failed: could not get user info after renewal for UUID %s", user_uuid)
        return None

    after_usage = float(after_info.get("current_usage_GB", -1))
    
    if after_usage < 0.1:
        logger.info("Renewal for UUID %s verified successfully.", user_uuid)
        return after_info
    
    logger.error(
        "Renew verification failed for UUID %s. Usage did not reset. After: %s",
        user_uuid,
        {"usage": after_usage}
    )
    return None


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