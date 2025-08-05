import requests
import json
import uuid
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY

def _get_base_url():
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def _get_headers():
    return {"Hiddify-API-Key": API_KEY, "Content-Type": "application/json"}

def create_hiddify_user(plan_days, plan_gb, user_telegram_id=None):
    endpoint = _get_base_url() + "user/"
    user_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}" if user_telegram_id else f"test-user-{uuid.uuid4().hex[:8]}"
    comment = f"Telegram user: {user_telegram_id}" if user_telegram_id else "Created by script"
    payload = {"name": user_name, "package_days": int(plan_days), "usage_limit_GB": int(plan_gb), "comment": comment}
    try:
        response = requests.post(endpoint, headers=_get_headers(), data=json.dumps(payload), timeout=20)
        if response.status_code in [200, 201]:
            user_data = response.json()
            user_uuid = user_data.get('uuid')
            subscription_url = f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/{user_uuid}/"
            return {"link": subscription_url, "uuid": user_uuid}
        else:
            print(f"ERROR (Create User): Hiddify API returned {response.status_code} -> {response.text}")
            return None
    except Exception as e:
        print(f"ERROR (Create User): {e}"); return None

def get_user_info(user_uuid):
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        response = requests.get(endpoint, headers=_get_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"ERROR (Get Info): Hiddify API returned {response.status_code} for UUID {user_uuid} -> {response.text}")
            return None
    except Exception as e:
        print(f"ERROR (Get Info): {e}"); return None

def reset_user_traffic(user_uuid, days):
    """Resets user traffic and updates expiry date."""
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    payload = {"package_days": int(days)} # We just need to update the days to reset the sub
    try:
        response = requests.put(endpoint, headers=_get_headers(), json=payload, timeout=10)
        # Hiddify Expanded API might use PUT for updates and returns 200
        if response.status_code == 200:
             # Also reset the traffic explicitly if there's an endpoint
            reset_endpoint = f"{_get_base_url()}user/{user_uuid}/reset/"
            requests.post(reset_endpoint, headers=_get_headers(), timeout=10)
            return True
        else:
            print(f"ERROR (Reset/Renew): Hiddify API returned {response.status_code} -> {response.text}")
            return False
    except Exception as e:
        print(f"ERROR (Reset/Renew): {e}"); return False