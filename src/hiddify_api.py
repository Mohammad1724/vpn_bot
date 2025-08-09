# -*- coding: utf-8 -*-

import httpx
import uuid
import random
import logging
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

logger = logging.getLogger(__name__)

try:
    import h2
    _HTTP2_ENABLED = True
except ImportError:
    _HTTP2_ENABLED = False

def _get_base_url() -> str:
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def _get_api_headers() -> dict:
    return { "Hiddify-API-Key": API_KEY, "Content-Type": "application/json", "Accept": "application/json" }

async def _make_client(timeout: float = 20.0, force_h1: bool = False) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, http2=(False if force_h1 else _HTTP2_ENABLED))

async def create_hiddify_user(plan_days: int, plan_gb: int, device_limit: int, user_telegram_id: int = None, custom_name: str = "") -> dict | None:
    endpoint = _get_base_url() + "user/"
    
    # <<< FIX for 422 Error: Ensure username is unique >>>
    # Append a short random hex to the name to avoid conflicts.
    random_suffix = uuid.uuid4().hex[:4]
    base_name = custom_name if custom_name else f"tg-{user_telegram_id}"
    unique_user_name = f"{base_name}-{random_suffix}"
    
    payload = {
        "name": unique_user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
        "device_limit": int(device_limit) if device_limit > 0 else 0,
        "comment": f"TG ID: {user_telegram_id}" if user_telegram_id else ""
    }
    try:
        async with await _make_client(timeout=20.0) as client:
            resp = await client.post(endpoint, json=payload, headers=_get_api_headers())
            resp.raise_for_status()
            user_data = resp.json()
    except ImportError:
        async with await _make_client(timeout=20.0, force_h1=True) as client:
            resp = await client.post(endpoint, json=payload, headers=_get_api_headers())
            resp.raise_for_status()
            user_data = resp.json()
    except httpx.HTTPStatusError as e:
        # Provide more details for 422 errors
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
            resp.raise_for_status()
            return resp.json()
    except ImportError:
        async with await _make_client(timeout=10.0, force_h1=True) as client:
            resp = await client.get(endpoint, headers=_get_api_headers())
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"_not_found": True}
        logger.error("get_user_info failed for %s: %s - %s", user_uuid, e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.error("get_user_info error: %s", e, exc_info=True)
        return None

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: int, device_limit: int) -> dict | None:
    async def _delete(u: str, client: httpx.AsyncClient) -> bool:
        url = f"{_get_base_url()}user/{u}/"
        try: r = await client.delete(url, headers=_get_api_headers()); r.raise_for_status(); return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404: return True
            logger.error("delete user %s failed: %s - %s", u, e.response.status_code, e.response.text); return False

    async def _recreate(u: str, name: str, days: int, gb: int, limit: int, client: httpx.AsyncClient) -> dict | None:
        url = _get_base_url() + "user/"
        payload = {"uuid": u, "name": name, "package_days": int(days), "usage_limit_GB": int(gb), "device_limit": int(limit) if limit > 0 else 0}
        try: r = await client.post(url, json=payload, headers=_get_api_headers()); r.raise_for_status(); return r.json()
        except httpx.HTTPStatusError as e:
            logger.error("recreate user %s failed: %s - %s", u, e.response.status_code, e.response.text); return None

    try:
        try: client = await _make_client(timeout=30.0)
        except ImportError: client = await _make_client(timeout=30.0, force_h1=True)

        async with client as c:
            info = await get_user_info(user_uuid)
            if not info or info.get('_not_found'):
                return None
            name = info.get("name", f"user-{uuid.uuid4().hex[:4]}")
            if not await _delete(user_uuid, c):
                return None
            return await _recreate(user_uuid, name, plan_days, plan_gb, device_limit, c)
    except Exception as e:
        logger.error("renew_user_subscription error: %s", e, exc_info=True)
        return None