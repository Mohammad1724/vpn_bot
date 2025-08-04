# hiddify_api.py

import requests
import config

# URL پایه برای API v2 هیدیفای
BASE_URL = f"https://{config.HIDDIFY_DOMAIN}/{config.HIDDIFY_PATH}/api/v2/"

# هدرهای ثابت برای تمام درخواست‌ها
# احراز هویت از طریق کلید API انجام می‌شود
HEADERS = {
    'Accept': 'application/json',
    'Hiddify-API-Key': config.HIDDIFY_API_KEY
}

def get_panel_stats():
    """
    آمار کلی پنل را برای نمایش وضعیت دریافت می‌کند.
    این تابع به عنوان تست اصلی اتصال هم عمل می‌کند.
    """
    try:
        api_url = f"{BASE_URL}server/status/"
        response = requests.get(api_url, headers=HEADERS, timeout=15)
        response.raise_for_status()  # اگر کد خطا بود، استثنا ایجاد می‌کند
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"خطای HTTP در دریافت آمار پنل: {e.response.status_code} - {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"خطای شبکه در دریافت آمار پنل: {e}")
        return None

# --- توابع آینده اینجا اضافه خواهند 