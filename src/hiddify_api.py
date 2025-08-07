# hiddify_api.py (نسخه نهایی با لاگ دقیق برای عیب‌یابی تاریخ)

import httpx
import uuid
import random
import logging

from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _get_base_url():
    """Returns the base URL for the Hiddify Admin API."""
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def _get_api_headers():
    """Returns the required headers for API requests."""
    return {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

# --- Internal Functions (for renewal) ---

async def _delete_user(user_uuid: str, client: httpx.AsyncClient) -> bool:
    """Internal function to delete a user. Returns True on success."""
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        response = await client.delete(endpoint, headers=_get_api_headers())
        response.raise_for_status()
        logger.info(f"Successfully deleted user {user_uuid} for renewal.")
        return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"User {user_uuid} was already deleted or not found. Proceeding with creation.")
            return True
        logger.error(f"Failed to delete user {user_uuid}: {e.response.status_code} - {e.response.text}")
        return False

async def _recreate_user(user_uuid: str, user_name: str, plan_days: int, plan_gb: int, client: httpx.AsyncClient) -> dict:
    """Internal function to recreate a user with the same UUID. Returns user data on success."""
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

# --- Public API Functions ---

async def create_hiddify_user(plan_days: int, plan_gb: int, user_telegram_id: int = None, custom_name: str = "") -> dict:
    """Creates a new user in Hiddify panel asynchronously."""
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
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(endpoint, json=payload, headers=_get_api_headers())
            response.raise_for_status()
            user_data = response.json()
            user_uuid = user_data.get('uuid')
            if not user_uuid:
                logger.error("Hiddify API create_hiddify_user did not return a UUID.")
                return None
            sub_path = SUB_PATH or ADMIN_PATH
            sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
            full_link = f"https://{sub_domain}/{sub_path}/{user_uuid}/"
            logger.info(f"Successfully created Hiddify user '{user_name}' with UUID {user_uuid}")
            return {"full_link": full_link, "uuid": user_uuid}
    except Exception as e:
        logger.error(f"An error occurred in create_hiddify_user: {e}", exc_info=True)
        return None

async def get_user_info(user_uuid: str) -> dict:
    """Fetches user information from Hiddify panel asynchronously."""
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(endpoint, headers=_get_api_headers())
            # <<<<<<< DEBUG LOG ADDED HERE >>>>>>>>>
            logger.info(f"Hiddify get_user_info RAW RESPONSE for {user_uuid}: {response.text}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"User with UUID {user_uuid} not found in Hiddify panel (404).")
        else:
            logger.error(f"Failed to get Hiddify info for UUID {user_uuid}: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"An error occurred in get_user_info: {e}", exc_info=True)
        return None

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: int) -> dict:
    """Renews a user's subscription using the delete-and-recreate strategy."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            current_info = await get_user_info(user_uuid)
            if not current_info:
                logger.error(f"Cannot renew: User {user_uuid} does not exist. Aborting.")
                return None
            user_name = current_info.get("name", f"user-{uuid.uuid4().hex[:4]}")
            delete_success = await _delete_user(user_uuid, client)
            if not delete_success:
                logger.error(f"Renewal failed at delete step for user {user_uuid}.")
                return None
            recreated_user = await _recreate_user(user_uuid, user_name, plan_days, plan_gb, client)
            if not recreated_user:
                logger.error(f"CRITICAL: Deleted user {user_uuid} but failed to recreate them!")
                return None
            return recreated_user
    except Exception as e:
        logger.error(f"An unexpected error occurred in renew_user_subscription: {e}", exc_info=True)
        return None