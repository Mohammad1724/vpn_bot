import requests
import json
import uuid
import random
import logging

from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

# Get the logger instance (configured in bot.py)
logger = logging.getLogger(__name__)

# --- API Session for Performance ---
# Use a single session to reuse TCP connections (Keep-Alive)
api_session = requests.Session()
api_session.headers.update({
    "Hiddify-API-Key": API_KEY,
    "Content-Type": "application/json"
})

def _get_base_url():
    """Constructs the base URL for the Hiddify Admin API."""
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def create_hiddify_user(plan_days, plan_gb, user_telegram_id=None, custom_name=""):
    """Creates a new user in Hiddify panel."""
    if custom_name:
        user_name = custom_name.replace(" ", "-")
    else:
        # Generate a unique name if no custom name is provided
        user_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}"
    
    comment = f"TG ID: {user_telegram_id}" if user_telegram_id else ""
    
    payload = {
        "name": user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb),
        "comment": comment
    }
    
    endpoint = _get_base_url() + "user/"
    
    try:
        response = api_session.post(endpoint, json=payload, timeout=20)
        response.raise_for_status()  # This will raise an HTTPError for 4xx/5xx responses
        
        user_data = response.json()
        user_uuid = user_data.get('uuid')
        
        if not user_uuid:
            logger.error("Hiddify API created a user but did not return a UUID.")
            return None
            
        sub_path = SUB_PATH or ADMIN_PATH
        sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
        full_link = f"https://{sub_domain}/{sub_path}/{user_uuid}/"
        
        logger.info(f"Successfully created Hiddify user '{user_name}' with UUID {user_uuid}")
        
        # Return only the necessary data
        return {"full_link": full_link, "uuid": user_uuid}
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Hiddify API request failed in create_hiddify_user: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in create_hiddify_user: {e}")
        return None

def get_user_info(user_uuid):
    """Retrieves information for a specific user from Hiddify."""
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    
    try:
        response = api_session.get(endpoint, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to get Hiddify info for UUID {user_uuid}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in get_user_info: {e}")
        return None

def renew_user_subscription(user_uuid, plan_days, plan_gb):
    """
    Renews a user's subscription by updating their plan and resetting their usage.
    This is now a transactional-like operation.
    """
    endpoint_update = f"{_get_base_url()}user/{user_uuid}/"
    payload = {
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb)
    }
    
    try:
        # Step 1: Update the user's package
        response_update = api_session.put(endpoint_update, json=payload, timeout=15)
        response_update.raise_for_status()
        logger.info(f"Successfully updated package for user {user_uuid}.")

        # Step 2: Reset the user's traffic
        endpoint_reset = f"{_get_base_url()}user/{user_uuid}/reset/"
        response_reset = api_session.post(endpoint_reset, timeout=15)
        response_reset.raise_for_status()
        logger.info(f"Successfully reset traffic for user {user_uuid}.")
        
        # Only return True if both steps were successful
        return True
        
    except requests.exceptions.RequestException as e:
        # The whole renewal process failed.
        logger.error(f"Hiddify API renewal failed for UUID {user_uuid}: {e}")
        # If the first step succeeded but the second failed, we should log a critical error.
        if 'response_update' in locals() and response_update.ok:
            logger.critical(f"CRITICAL: User {user_uuid} was renewed BUT FAILED TO RESET. Manual intervention required!")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred in renew_user_subscription: {e}")
        return False