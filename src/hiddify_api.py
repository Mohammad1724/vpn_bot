import requests
import json
import uuid
import random
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

def _get_base_url():
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def _get_headers():
    return {"Hiddify-API-Key": API_KEY, "Content-Type": "application/json"}

def create_hiddify_user(plan_days, plan_gb, user_telegram_id=None):
    endpoint = _get_base_url() + "user/"
    user_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}" if user_telegram_id else f"test-user-{uuid.uuid4().hex[:8]}"
    comment = f"Telegram user: {user_telegram_id}" if user_telegram_id else "Created by script"
    payload = {"name": user_name, "package_days": int(plan_days), "usage_limit_GB": int(plan_gb), "comment": comment}
    
    print("--- [DEBUG] Attempting to CREATE user ---")
    print(f"[DEBUG] Endpoint: {endpoint}")
    print(f"[DEBUG] Payload: {json.dumps(payload)}")
    
    try:
        response = requests.post(endpoint, headers=_get_headers(), data=json.dumps(payload), timeout=20)
        print(f"[DEBUG] Create User - Response Status: {response.status_code}")
        print(f"[DEBUG] Create User - Response Body: {response.text}")

        if response.status_code in [200, 201]:
            user_data = response.json()
            user_uuid = user_data.get('uuid')

            if not user_uuid:
                print("[ERROR] 'uuid' not found in Hiddify API response.")
                return None

            subscription_path = SUB_PATH if SUB_PATH else ADMIN_PATH
            subscription_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
            full_profile_url = f"https://{subscription_domain}/{subscription_path}/{user_uuid}/"
            
            print(f"SUCCESS: User '{user_name}' created successfully.")
            return {"full_link": full_profile_url, "uuid": user_uuid}
        else:
            print(f"[ERROR] Hiddify API returned an unsuccessful status for create_user.")
            return None
    except Exception as e:
        print(f"[FATAL ERROR] Exception during create_user API call: {e}")
        return None

def get_user_info(user_uuid):
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    
    print(f"--- [DEBUG] Attempting to GET user info for UUID: {user_uuid} ---")
    print(f"[DEBUG] Endpoint: {endpoint}")
    
    try:
        response = requests.get(endpoint, headers=_get_headers(), timeout=10)
        print(f"[DEBUG] Get Info - Response Status: {response.status_code}")
        print(f"[DEBUG] Get Info - Response Body: {response.text}")

        if response.status_code == 200:
            print("[SUCCESS] User info retrieved successfully.")
            return response.json()
        else:
            print(f"[ERROR] Hiddify API returned an unsuccessful status for get_user_info.")
            return None
    except Exception as e:
        print(f"[FATAL ERROR] Exception during get_user_info API call: {e}")
        return None

def reset_user_traffic(user_uuid, days):
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    payload = {"package_days": int(days)}
    
    print(f"--- [DEBUG] Attempting to RENEW user for UUID: {user_uuid} ---")
    print(f"[DEBUG] Endpoint: {endpoint}")
    print(f"[DEBUG] Payload: {json.dumps(payload)}")
    
    try:
        response = requests.put(endpoint, headers=_get_headers(), json=payload, timeout=10)
        print(f"[DEBUG] Renew User - Response Status: {response.status_code}")
        print(f"[DEBUG] Renew User - Response Body: {response.text}")

        if response.status_code == 200:
            print("[SUCCESS] User renewal successful, attempting to reset traffic.")
            reset_endpoint = f"{_get_base_url()}user/{user_uuid}/reset/"
            # We send this request but don't strictly need to wait for its response
            requests.post(reset_endpoint, headers=_get_headers(), timeout=10)
            return True
        else:
            print(f"[ERROR] Hiddify API returned an unsuccessful status for user renewal.")
            return False
    except Exception as e:
        print(f"[FATAL ERROR] Exception during user renewal API call: {e}")
        return False