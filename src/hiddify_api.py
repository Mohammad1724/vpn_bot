# -*- coding: utf-8 -*-
# Hiddify API client with HTTP/2 (if available) and HTTP/1.1 fallback

import logging
import uuid
import random
import httpx

from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

logger = logging.getLogger(__name__)

# Detect HTTP/2 availability
try:
    import h2  # noqa: F401
    _HTTP2_ENABLED = True
except Exception:
    _HTTP2_ENABLED = False

def _get_base_url() -> str:
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def _get_api_headers() -> dict:
    return {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

async def _delete_user(user_uuid: str, client: httpx.AsyncClient) -> bool:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        resp = await client.delete(endpoint, headers=_get_api_headers())
        resp.raise_for_status()
        logger.info("Deleted user %s for renewal.", user_uuid)
        return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("User %s not found (already deleted). Continue.", user_uuid)
            return True
        logger.error("Delete user %s failed: %s - %s", user_uuid, e.response.status_code, e.response.text)
        return False

async def _recreate_user(user_uuid: str, user_name: str, plan_days: int, plan_gb: int, client: httpx.AsyncClient) -> dict | None:
    endpoint = _get_base_url() + "user/"
    payload = {
        "uuid": user_uuid,
        "name": user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
    }
    try:
        resp = await client.post(endpoint, json=payload, headers=_get_api_headers())
        resp.raise_for_status()
        data = resp.json()
        logger.info("Recreated user %s with new plan.", user_uuid)
        return data
    except httpx.HTTPStatusError as e:
        logger.error("Recreate user %s failed: %s - %s", user_uuid, e.response.status_code, e.response.text)
        return None

async def _make_client(timeout: float = 20.0, force_h1: bool = False) -> httpx.AsyncClient:
    # Build AsyncClient with HTTP/2 if available (unless force_h1 is True)
    return httpx.AsyncClient(timeout=timeout, http2=(False if force_h1 else _HTTP2_ENABLED))

# Public API

async def create_hiddify_user(plan_days: int, plan_gb: int, user_telegram_id: int = None, custom_name: str = "") -> dict | None:
    endpoint = _get_base_url() + "user/"
    user_name = custom_name or f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}"
    comment = f"TG ID: {user_telegram_id}" if user_telegram_id else ""
    payload = {
        "name": user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
        "comment": comment,
    }
    # Try with HTTP/2 (if available), otherwise retry with HTTP/1.1
    try:
        async with await _make_client(timeout=20.0) as client:
            resp = await client.post(endpoint, json=payload, headers=_get_api_headers())
            resp.raise_for_status()
            user_data = resp.json()
    except ImportError as e:
        logger.warning("HTTP/2 not available; retry over HTTP/1.1: %s", e)
        async with await _make_client(timeout=20.0, force_h1=True) as client:
            resp = await client.post(endpoint, json=payload, headers=_get_api_headers())
            resp.raise_for_status()
            user_data = resp.json()
    except Exception as e:
        logger.error("create_hiddify_user error: %s", e, exc_info=True)
        return None

    user_uuid = user_data.get("uuid")
    if not user_uuid:
        logger.error("create_hiddify_user: UUID missing in response.")
        return None
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    full_link = f"https://{sub_domain}/{sub_path}/{user_uuid}/"
    logger.info("Created Hiddify user '%s' with UUID %s", user_name, user_uuid)
    return {"full_link": full_link, "uuid": user_uuid}

async def get_user_info(user_uuid: str) -> dict | None:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    # Try with HTTP/2, fallback to HTTP/1.1
    try:
        async with await _make_client(timeout=10.0) as client:
            resp = await client.get(endpoint, headers=_get_api_headers())
            logger.debug("get_user_info %s -> %s | %s", user_uuid, resp.status_code, resp.text[:1000])
            resp.raise_for_status()
            return resp.json()
    except ImportError as e:
        logger.warning("HTTP/2 not available; retry over HTTP/1.1: %s", e)
        async with await _make_client(timeout=10.0, force_h1=True) as client:
            resp = await client.get(endpoint, headers=_get_api_headers())
            logger.debug("get_user_info %s (h1) -> %s | %s", user_uuid, resp.status_code, resp.text[:1000])
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("User %s not found (404).", user_uuid)
        else:
            logger.error("get_user_info failed for %s: %s - %s", user_uuid, e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.error("get_user_info error: %s", e, exc_info=True)
        return None

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: int) -> dict | None:
    try:
        # Try with HTTP/2, fallback to HTTP/1.1
        try:
            client = await _make_client(timeout=30.0)
        except ImportError:
            client = await _make_client(timeout=30.0, force_h1=True)

        async with client as c:
            current_info = await get_user_info(user_uuid)
            if not current_info:
                logger.error("Cannot renew: User %s does not exist.", user_uuid)
                return None
            user_name = current_info.get("name", f"user-{uuid.uuid4().hex[:4]}")
            if not await _delete_user(user_uuid, c):
                logger.error("Renewal failed at delete step for %s.", user_uuid)
                return None
            recreated = await _recreate_user(user_uuid, user_name, plan_days, plan_gb, c)
            if not recreated:
                logger.error("Deleted %s but failed to recreate.", user_uuid)
                return None
            return recreated
    except Exception as e:
        logger.error("renew_user_subscription error: %s", e, exc_info=True)
        return None