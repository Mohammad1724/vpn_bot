# hiddify_api.py

import requests
import config

BASE_URL = f"https://{config.HIDDIFY_DOMAIN}/{config.HIDDIFY_PATH}/{config.HIDDIFY_ADMIN_UUID}/api/v2/"

def get_panel_info():
    """تست اتصال به پنل و دریافت اطلاعات کلی."""
    try:
        api_url = f"{BASE_URL}server/status/"
        headers = {'Accept': 'application/json'}
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status() 
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"خطا در اتصال به Hiddify API: {e}")
        return None
