# hiddify_api.py (نسخه اصلاح‌شده، غیرهمزمان و امن)

import httpx  # جایگزین requests
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
        # Generate a unique name if no custom name is provided
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
            response.raise_for_status()  # Raises an exception for 4xx/5xx responses
            
            user_data = response.json()
            user_uuid = user_data.get('uuid')
            
            if not user_uuid:
                logger.error("Hiddify API create_hiddify_user did not return a UUID.")
                return None
            
            # Construct the full subscription link
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
            # The actual user data is often nested inside a 'user' key
            return response.json().get('user')
            
    except httpx.HTTPStatusError as e:
        logger.warning(f"Failed to get Hiddify info for UUID {user_uuid}: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.warning(f"A network-related error occurred while getting info for {user_uuid}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_user_info: {e}", exc_info=True)
        return None


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: int) -> dict:
    """
    Renews a user's subscription by updating their package details.
    This is the SAFE method, using PATCH/POST to modify the user instead of deleting.
    Returns the updated user info dictionary on success, otherwise None.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    
    # Payload for updating the user. We reset the usage and set new package details.
    # The 'current_usage_GB': 0 might not be necessary if Hiddify resets it on package change, but it's safer.
    payload = {
        "current_usage_GB": 0,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
        # You can add other fields to update here if needed
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Hiddify API v2 uses POST to update a user.
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

# The dangerous "delete_user" function is no longer needed for renewals.
# If you need it for other admin purposes, you can convert it to async like the others.
# async def delete_user(user_uuid: str) -> bool:
#     ...