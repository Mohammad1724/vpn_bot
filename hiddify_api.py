# hiddify_api.py

import requests
import uuid
import os
import logging

logger = logging.getLogger(__name__)

class HiddifyAPI:
    def __init__(self, panel_domain, admin_uuid):
        if not panel_domain.startswith(('http://', 'https://')):
            panel_domain = f"https://{panel_domain}"
        
        self.base_url = f"{panel_domain}/{admin_uuid}/api/v2/admin"
        self.headers = {'Accept': 'application/json'}
        logger.info(f"Hiddify API client initialized for base URL: {self.base_url.replace(admin_uuid, '*****')}")

    def _make_request(self, method, endpoint, **kwargs):
        """یک تابع کمکی برای ارسال تمام درخواست‌ها و مدیریت خطا."""
        try:
            response = requests.request(method, f"{self.base_url}{endpoint}", headers=self.headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error for {method} {endpoint}: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Exception for {method} {endpoint}: {e}")
        return None

    def create_user(self, name, package_days, package_size_gb, telegram_id=None):
        """یک کاربر جدید در Hiddify ایجاد می‌کند."""
        user_uuid = str(uuid.uuid4())
        data = {
            "name": name,
            "uuid": user_uuid,
            "data_limit_GB": package_size_gb,
            "package_days": package_days,
            "telegram_id": str(telegram_id) if telegram_id else ""
        }
        
        user_data = self._make_request("post", "/user/", json=data)
        if user_data:
            # لینک اشتراک را به صورت دستی می‌سازیم چون API آن را برنمی‌گرداند
            sub_link = f"https://{os.getenv('HIDDIFY_PANEL_DOMAIN')}/{os.getenv('HIDDIFY_ADMIN_UUID')}/{user_uuid}/"
            return {"uuid": user_uuid, "subscription_link": sub_link}
        return None

    def get_user(self, user_uuid):
        """اطلاعات یک کاربر خاص را از Hiddify دریافت می‌کند."""
        return self._make_request("get", f"/user/{user_uuid}/")

    def modify_user(self, user_uuid, new_data_limit_gb, new_package_days):
        """حجم و زمان کاربر را برای تمدید، ریست و به‌روزرسانی می‌کند."""
        current_data = self.get_user(user_uuid)
        if not current_data:
            return None

        current_data['data_limit_GB'] = new_data_limit_gb
        current_data['package_days'] = new_package_days
        current_data['current_usage_GB'] = 0  # ریست کردن مصرف فعلی

        return self._make_request("put", f"/user/{user_uuid}/", json=current_data)
        
    def delete_user(self, user_uuid):
        """یک کاربر را از پنل حذف می‌کند."""
        return self._make_request("delete", f"/user/{user_uuid}/")
