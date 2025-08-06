import requests
import json
import uuid
import random
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

def _get_base_url(): return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"
def _get_headers(): return {"Hiddify-API-Key": API_KEY, "Content-Type": "application/json"}

def create_hiddify_user(plan_days, plan_gb, user_telegram_id=None, custom_name=""):
    endpoint = _get_base_url() + "user/"
    unique_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}"
    comment = f"Custom Name: {custom_name} | TG ID: {user_telegram_id}" if custom_name else f"Telegram user: {user_telegram_id}"
    payload = {"name": unique_name, "package_days": int(plan_days), "usage_limit_GB": int(plan_gb), "comment": comment}
    try:
        response = requests.post(endpoint, headers=_get_headers(), json=payload, timeout=20)
        if response.status_code in [200, 201]:
            user_data = response.json()
            user_uuid = user_data.get('uuid')
            if not user_uuid: return None
            sub_path = SUB_PATH or ADMIN_PATH
            sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
            full_link = f"https://{sub_domain}/{sub_path}/{user_uuid}/"
            config_name_fragment = custom_name.replace(" ", "-") if custom_name else unique_name
            return {"full_link": full_link, "uuid": user_uuid, "config_name": config_name_fragment}
        else:
            print(f"ERROR (Create User): {response.status_code} -> {response.text}"); return None
    except Exception as e:
        print(f"ERROR (Create User Exception): {e}"); return None

def get_user_info(user_uuid):
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        response = requests.get(endpoint, headers=_get_headers(), timeout=10)
        if response.status_code == 200: return response.json()
        else: print(f"ERROR (Get Info): {response.status_code} for UUID {user_uuid} -> {response.text}"); return None
    except Exception as e:
        print(f"ERROR (Get Info Exception): {e}"); return None

def renew_user_subscription(user_uuid, plan_days, plan_gb):
    endpoint_update = f"{_get_base_url()}user/{user_uuid}/"
    # For renewal, Hiddify needs package_days to be reset from today.
    # The usage_limit_GB should also be part of the update.
    payload = { "package_days": int(plan_days), "usage_limit_GB": int(plan_gb) }
    print(f"--- [DEBUG] Attempting to RENEW user subscription for UUID: {user_uuid} ---")
    print(f"[DEBUG] Endpoint: {endpoint_update}")
    print(f"[DEBUG] Payload: {json.dumps(payload)}")
    try:
        # Hiddify uses PUT request to update an existing user.
        response_update = requests.put(endpoint_update, headers=_get_headers(), json=payload, timeout=15)
        print(f"[DEBUG] Renew User (PUT) - Response Status: {response_update.status_code}")
        print(f"[DEBUG] Renew User (PUT) - Response Body: {response_update.text}")

        if response_update.status_code == 200:
            print(f"[SUCCESS] User {user_uuid} package renewed. Attempting to reset traffic.")
            # Resetting traffic is a separate, crucial step after renewal.
            endpoint_reset = f"{_get_base_url()}user/{user_uuid}/reset/"
            response_reset = requests.post(endpoint_reset, headers=_get_headers(), timeout=15)
            print(f"[DEBUG] Reset Traffic (POST) - Response Status: {response_reset.status_code}")
            return True # Even if reset fails, renewal of date is the main success.
        else:
            print(f"[ERROR] Hiddify API returned an unsuccessful status for user renewal.")
            return False
    except Exception as e:
        print(f"ERROR (Renew Exception): {e}"); return False