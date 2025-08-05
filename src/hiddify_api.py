# src/hiddify_api.py

import requests
import json
import uuid
import random # <<< ماژول جدید برای انتخاب تصادفی
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS

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

            # --- اصلاحیه نهایی برای ساخت لینک اشتراک ---
            # 1. تعیین دامنه مورد استفاده
            if SUB_DOMAINS:
                # یک دامنه به صورت تصادفی از لیست انتخاب کن
                subscription_domain = random.choice(SUB_DOMAINS)
            else:
                # اگر لیست خالی بود، از دامنه اصلی پنل استفاده کن
                subscription_domain = PANEL_DOMAIN
            
            # 2. ساخت لینک مستقیم اشتراک با فرمت /sub/
            subscription_url = f"https://{subscription_domain}/{ADMIN_PATH}/{user_uuid}/sub/"
            
            print(f"SUCCESS: User {user_name} created. Sub Link: {subscription_url}")
            return {"link": subscription_url, "uuid": user_uuid}
        else:
            print(f"ERROR (Create User): Hiddify API returned {response.status_code} -> {response.text}")
            return None
    except Exception as e:
        print(f"ERROR (Create User): {e}"); return None

# ... (بقیه توابع get_user_info و reset_user_traffic بدون تغییر باقی می‌مانند) ...
def get_user_info(user_uuid):
    # این تابع بدون تغییر است
    pass
def reset_user_traffic(user_uuid, days):
    # این تابع بدون تغییر است
    pass