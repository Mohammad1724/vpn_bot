# hiddify_api.py
import requests
import os
import logging
import uuid

logger = logging.getLogger(__name__)

class HiddifyAPI:
    def __init__(self, panel_domain, admin_uuid, admin_user, admin_pass):
        if not panel_domain.startswith(('http://', 'https://')):
            self.panel_domain_https = f"https://{panel_domain}"
        else:
            self.panel_domain_https = panel_domain

        self.api_base_url = f"{self.panel_domain_https}/{admin_uuid}/api/v2/admin"
        self.login_url = f"{self.panel_domain_https}/{admin_uuid}/api/v2/admin/login/"
        
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self.access_token = None

        if not self._login():
            raise ConnectionError("Login به پنل Hiddify ناموفق بود. لطفاً اطلاعات دامنه، UUID، نام کاربری و رمز عبور را در فایل .env بررسی کنید.")

    def _login(self):
        login_data = {'username': self.admin_user, 'password': self.admin_pass}
        try:
            response = requests.post(self.login_url, data=login_data, timeout=10)
            response.raise_for_status()
            self.access_token = response.json().get('access_token')
            if self.access_token:
                logger.info("Successfully logged in to Hiddify and got access token.")
                return True
            logger.error("Login successful but no access token found in response.")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Hiddify login failed: {e}")
            if hasattr(e, 'response') and e.response: logger.error(f"Response body: {e.response.text}")
            return False

    def _get_auth_headers(self):
        if not self.access_token:
            self._login()
        if self.access_token:
            return {'Accept': 'application/json', 'Authorization': f'Bearer {self.access_token}'}
        raise ConnectionError("Cannot get auth headers because access token is missing.")

    def _make_request(self, method, endpoint, **kwargs):
        try:
            headers = self._get_auth_headers()
            response = requests.request(method, f"{self.api_base_url}{endpoint}", headers=headers, timeout=15, **kwargs)
            
            if response.status_code == 401:
                logger.warning("Access token expired or invalid. Attempting to re-login...")
                if self._login():
                    headers = self._get_auth_headers()
                    response = requests.request(method, f"{self.api_base_url}{endpoint}", headers=headers, timeout=15, **kwargs)

            response.raise_for_status()
            # برای متد DELETE که ممکن است پاسخ خالی برگرداند
            if response.status_code == 204: return True
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error for {method} {endpoint}: {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Exception for {method} {endpoint}: {e}")
        return None

    def create_user(self, name, package_days, package_size_gb, telegram_id=None):
        user_uuid = str(uuid.uuid4())
        data = { "name": name, "uuid": user_uuid, "data_limit_GB": package_size_gb, "package_days": package_days, "telegram_id": str(telegram_id) if telegram_id else "" }
        
        user_data = self._make_request("post", "/user/", json=data)
        if user_data:
            sub_link = f"{self.panel_domain_https}/{os.getenv('HIDDIFY_ADMIN_UUID')}/{user_uuid}/"
            return {"uuid": user_uuid, "subscription_link": sub_link}
        return None

    def get_user(self, user_uuid):
        return self._make_request("get", f"/user/{user_uuid}/")
    
    def get_all_users(self):
        return self._make_request("get", "/user/")

    def modify_user(self, user_uuid, new_data_limit_gb, new_package_days):
        current_data = self.get_user(user_uuid)
        if not current_data: return None
        current_data['data_limit_GB'] = new_data_limit_gb
        current_data['package_days'] = new_package_days
        current_data['current_usage_GB'] = 0
        return self._make_request("put", f"/user/{user_uuid}/", json=current_data)
        
    def delete_user(self, user_uuid):
        return self._make_request("delete", f"/user/{user_uuid}/")