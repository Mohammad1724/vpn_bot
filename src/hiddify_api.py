# hiddify_api.py (نسخه اصلاح شده)

import requests
import json
import uuid
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY

def create_hiddify_user(plan_days, plan_gb, user_telegram_id=None):
    BASE_URL = f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"
    HEADERS = {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    endpoint = BASE_URL + "user/"
    
    user_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}" if user_telegram_id else f"test-user-{uuid.uuid4().hex[:8]}"
    comment = f"Telegram user: {user_telegram_id}" if user_telegram_id else "Created by script"
    payload = {"name": user_name, "package_days": int(plan_days), "usage_limit_GB": int(plan_gb), "comment": comment}
    try:
        response = requests.post(endpoint, headers=HEADERS, data=json.dumps(payload), timeout=20)
        if response.status_code in [200, 201]:
            user_data = response.json()
            user_uuid = user_data.get('uuid')
            subscription_url = f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/{user_uuid}/"
            print(f"SUCCESS: User {user_name} created successfully.")
            # حالا یک دیکشنری برمی‌گردانیم
            return {"link": subscription_url, "uuid": user_uuid}
        else:
            print(f"ERROR: Hiddify API returned status {response.status_code} with message: {response.text}")
            return None
    except Exception as e:
        print(f"ERROR: An exception occurred while connecting to Hiddify API: {e}")
        return None