# -*- coding: utf-8 -*-
# hiddify_api.py (HTTP/2 enabled, cleaner logs, shared AsyncClient in renewal)

import httpx
import uuid
import random
import logging

from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

logger = logging.getLogger(__name__)

def _get_base_url():
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def _get_api_headers():
    return {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

async def _delete_user(user_uuid: str, client: httpx.AsyncClient) -> bool:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        response = await client.delete(endpoint, headers=_get_api_headers())
        response.raise_for_status()
        logger.info(f"Successfully deleted user {user_uuid} for renewal.")
        return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"User {user_uuid} not found (already deleted). Proceeding.")
            return True
        logger.error(f"Failed to delete user {user_uuid}: {e.response.status_code} - {e.response.text}")
        return False

async def _recreate_user(user_uuid: str, user_name: str, plan_days: int, plan_gb: int, client: httpx.AsyncClient) -> dict:
    endpoint = _get_base_url() + "user/"
    payload = {
        "uuid": user_uuid,
        "name": user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
    }
    try:
        response = await client.post(endpoint, json=payload, headers=_get_api_headers())
        response.raise_for_status()
        user_data = response.json()
        logger.info(f"Successfully recreated user {user_uuid} with new plan.")
        return user_data
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to recreate user {user_uuid}: {e.response.status_code} - {e.response.text}")
        return None

async def create_hiddify_user(plan_days: int, plan_gb: int, user_telegram_id: int = None, custom_name: str = "") -> dict:
    endpoint = _get_base_url() + "user/"
    user_name = custom_name or f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}"
    comment = f"TG ID: {user_telegram_id}" if user_telegram_id else ""
    payload = {
        "name": user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
        "comment": comment,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, http2=True) as client:
            response = await client.post(endpoint, json=payload, headers=_get_api_headers())
            response.raise_for_status()
            user_data = response.json()
            user_uuid = user_data.get('uuid')
            if not user_uuid:
                logger.error("Hiddify API did not return a UUID.")
                return None
            sub_path = SUB_PATH or ADMIN_PATH
            sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
            full_link = f"https://{sub_domain}/{sub_path}/{user_uuid}/"
            logger.info(f"Created Hiddify user '{user_name}' with UUID {user_uuid}")
            return {"full_link": full_link, "uuid": user_uuid}
    except Exception as e:
        logger.error(f"create_hiddify_user error: {e}", exc_info=True)
        return None

async def get_user_info(user_uuid: str, client: httpx.AsyncClient = None) -> dict:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    local_client = None
    try:
        if client is None:
            local_client = httpx.AsyncClient(timeout=10.0, http2=True)
        c = client or local_client
        response = await c.get(endpoint, headers=_get_api_headers())
        logger.debug(f"get_user_info {user_uuid} -> {response.status_code} | {response.text[:1000]}")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"User {user_uuid} not found (404).")
        else:
            logger.error(f"get_user_info failed for {user_uuid}: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"get_user_info error: {e}", exc_info=True)
        return None
    finally:
        if local_client is not None:
            await local_client.aclose()

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: int) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0, http2=True) as client:
            current_info = await get_user_info(user_uuid, client=client)
            if not current_info:
                logger.error(f"Cannot renew: user {user_uuid} does not exist.")
                return None
            user_name = current_info.get("name", f"user-{uuid.uuid4().hex[:4]}")
            if not await _delete_user(user_uuid, client):
                logger.error(f"Renewal failed at delete step for {user_uuid}.")
                return None
            recreated_user = await _recreate_user(user_uuid, user_name, plan_days, plan_gb, client)
            if not recreated_user:
                logger.error(f"Deleted {user_uuid} but failed to recreate.")
                return None
            return recreated_user
    except Exception as e:
        logger.error(f"renew_user_subscription error: {e}", exc_info=True)
        return None