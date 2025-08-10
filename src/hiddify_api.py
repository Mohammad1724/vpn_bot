# -*- coding: utf-8 -*-

import httpx
import uuid
import random
import logging
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

logger = logging.getLogger(__name__)

def _get_base_url() -> str:
    # URL برای API v2
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def _get_api_headers() -> dict:
    return { "Hiddify-API-Key": API_KEY, "Content-Type": "application/json", "Accept": "application/json" }

async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    try:
        import h2
        http2_support = True
    except ImportError:
        http2_support = False
    return httpx.AsyncClient(timeout=timeout, http2=http2_support)

async def create_hiddify_user(plan_days: int, plan_gb: int, user_telegram_id: str, custom_name: str = "") -> dict | None:
    endpoint = _get_base_url() + "user/"

    random_suffix = uuid.uuid4().hex[:4]
    base_name = custom_name if custom_name else f"tg-{user_telegram_id.split(':')[-1]}"
    unique_user_name = f"{base_name}-{random_suffix}"

    payload = {
        "name": unique_user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
        "comment": user_telegram_id
    }

    try:
        async with await _make_client(timeout=20.0) as client:
            resp = await client.post(endpoint, json=payload, headers=_get_api_headers())
            resp.raise_for_status()
            user_data = resp.json()
    except httpx.HTTPStatusError as e:
        error_details = e.response.text if e.response.status_code == 422 else str(e)
        logger.error("create_hiddify_user error: %s - Details: %s", e, error_details, exc_info=True)
        return None
    except Exception as e:
        logger.error("create_hiddify_user error: %s", e, exc_info=True)
        return None

    user_uuid = user_data.get("uuid")
    if not user_uuid:
        logger.error("create_hiddify_user: UUID missing in response.")
        return None

    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    return {"full_link": f"https://{sub_domain}/{sub_path}/{user_uuid}/", "uuid": user_uuid}

async def get_user_info(user_uuid: str) -> dict | None:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        async with await _make_client(timeout=10.0) as client:
            resp = await client.get(endpoint, headers=_get_api_headers())
            if resp.status_code == 404:
                return {"_not_found": True}
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("get_user_info error: %s", e, exc_info=True)
        return None

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: int) -> dict | None:
    endpoint = f"{_get_base_url()}user/{user_uuid}/renew/"
    payload = {
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
    }
    try:
        async with await _make_client(timeout=30.0) as client:
            resp = await client.post(endpoint, json=payload, headers=_get_api_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("renew_user_subscription failed for %s: %s - %s", user_uuid, e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.error("renew_user_subscription error: %s", e, exc_info=True)
        return None

async def delete_user_from_panel(user_uuid: str) -> bool:
    """
    کاربر را از پنل هیدیفای (API v2) حذف می‌کند.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        async with await _make_client(timeout=15.0) as client:
            resp = await client.delete(endpoint, headers=_get_api_headers())
            # اگر کاربر از قبل حذف شده بود (404)، آن را موفقیت در نظر می‌گیریم.
            if 200 <= resp.status_code < 300 or resp.status_code == 404:
                logger.info(f"Successfully deleted/not-found user {user_uuid} from panel.")
                return True
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Failed to delete user {user_uuid} from panel: {e}", exc_info=True)
        return False