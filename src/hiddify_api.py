import requests
import json
import uuid
import random
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

def _get_base_url():
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"
def _get_headers():
    return {"Hiddify-API-Key": API_KEY, "Content-Type": "application/json"}

def create_hiddify_user(plan_days, plan_gb, user_telegram_id=None, custom_name=""):
    endpoint = _get_base_url() + "user/"
    unique_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}"
    comment = f"Custom Name: {custom_name} | TG ID: {user_telegram_id}" if custom_name else f"Telegram user: {user_telegram_id}"
    payload = {"name": unique_name, "package_days": int(plan_days), "usage_limit_GB": int(plan_gb), "comment": comment}
    try:
        response = requests.post(endpoint, headers=_get_headers(), data=json.dumps(payload), timeout=20)
        if response.status_code in [200, 201]:
            user_data = response.json()
            user_uuid = user_data.get('uuid')
            if not user_uuid: return None
            subscription_path = SUB_PATH if SUB_PATH else ADMIN_PATH
            subscription_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
            full_profile_url = f"https://{subscription_domain}/{subscription_path}/{user_uuid}/"
            config_name_fragment = custom_name.replace(" ", "-") if custom_name else unique_name
            return {"full_link": full_profile_url, "uuid": user_uuid, "config_name": config_name_fragment}
        else:
            print(f"ERROR (Create User): Hiddify API returned {response.status_code} -> {response.text}"); return None
    except Exception as e:
        print(f"FATAL ERROR (Create User Exception): {e}"); return None

def get_user_info(user_uuid):
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        response = requests.get(endpoint, headers=_get_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"ERROR (Get Info): Hiddify API returned {response.status_code} for UUID {user_uuid} -> {response.text}"); return None
    except Exception as e:
        print(f"FATAL ERROR (Get Info Exception): {e}"); return None

def renew_user_subscription(user_uuid, plan_days, plan_gb):
    """
    Renews a user's subscription by updating their data and resetting traffic.
    This is more robust than just resetting traffic.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    payload = {
        "package_days": int(plan_days),
        "usage_limit_GB": int(plan_gb)
    }
    
    print(f"--- [DEBUG] Attempting to RENEW user subscription for UUID: {user_uuid} ---")
    print(f"[DEBUG] Endpoint: {endpoint}")
    print(f"[DEBUG] Payload: {json.dumps(payload)}")

    try:
        # Hiddify uses PUT request to update a user
        response = requests.put(endpoint, headers=_get_headers(), json=payload, timeout=10)
        print(f"[DEBUG] Renew User (PUT) - Response Status: {response.status_code}")
        print(f"[DEBUG] Renew User (PUT) - Response Body: {response.text}")

        if response.status_code == 200:
            print(f"[SUCCESS] User {user_uuid} package renewed successfully.")
            # Hiddify automatically resets traffic upon successful package update,
            # but we can call reset endpoint as a fallback.
            reset_endpoint = f"{_get_base_url()}user/{user_uuid}/reset/"
            requests.post(reset_endpoint, headers=_get_headers(), timeout=10)
            return True
        else:
            print(f"[ERROR] Hiddify API returned an unsuccessful status for user renewal.")
            return False
    except Exception as e:
        print(f"FATAL ERROR (Renew User Exception): {e}")
        return False