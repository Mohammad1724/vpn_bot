# hiddify_api.py (نسخه نهایی و اصلاح شده)

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

# --- Async API Functions ---

async def create_hiddify_user(plan_days: int, plan_gb: int, user_telegram_id: int = None, custom_name: str = "") -> dict:
    """
    Creates a new user in Hiddify panel asynchronously.
    Returns a dictionary with 'full_link' and 'uuid' on success, otherwise None.
    """
    endpoint = _get_base_url() + "user/"

    if custom_name:
        user_name = custom_name
    else:
        user_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}"

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

    except httpx.HTTPStatusError as e:
        logger.error(f"Hiddify API request failed in create_hiddify_user: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"A network-related error occurred in create_hiddify_user: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in create_hiddify_user: {e}", exc_info=True)
        return None


async def get_user_info(user_uuid: str) -> dict:
    """
    Fetches user information from Hiddify panel asynchronously.
    Returns the user data dictionary on success, otherwise None.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(endpoint, headers=_get_api_headers())
            response.raise_for_status()
            # CORRECTED: Return the whole JSON response, as it should be the user object itself.
            return response.json()

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"User with UUID {user_uuid} not found in Hiddify panel (404).")
        else:
            logger.error(f"Failed to get Hiddify info for UUID {user_uuid}: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"A network-related error occurred while getting info for {user_uuid}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_user_info: {e}", exc_info=True)
        return None


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: int) -> dict:
    """
    Renews a user's subscription by updating their package details.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"

    payload = {
        "current_usage_GB": 0,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(endpoint, json=payload, headers=_get_api_headers())
            response.raise_for_status()

            updated_user_info = response.json()
            logger.info(f"Successfully renewed subscription for user {user_uuid} with new plan.")
            return updated_user_info

    except httpx.HTTPStatusError as e:
        logger.error(f"Hiddify API renewal failed for user {user_uuid}: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"A network-related error occurred during renewal for {user_uuid}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in renew_user_subscription: {e}", exc_info=True)
        return None