# -*- coding: utf-8 -*-

import httpx
import uuid
import random
import logging
import asyncio
from typing import Optional, Dict, Any, Union
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

logger = logging.getLogger(__name__)

# تعداد تلاش‌های مجدد برای درخواست‌های ناموفق
MAX_RETRIES = 3
# تأخیر پایه بین تلاش‌های مجدد (در ثانیه)
BASE_RETRY_DELAY = 1.0

def _get_base_url() -> str:
    # URL برای API v2.2.0
    return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"

def _get_api_headers() -> dict:
    return {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    try:
        import h2
        http2_support = True
    except ImportError:
        http2_support = False
    return httpx.AsyncClient(timeout=timeout, http2=http2_support)

async def _make_request(method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    اجرای درخواست HTTP با مکانیزم retry و مدیریت خطای پیشرفته
    """
    client = None
    retries = 0
    while retries <= MAX_RETRIES:
        try:
            if client is None:
                client = await _make_client(timeout=kwargs.get('timeout', 20.0))
            
            response = await getattr(client, method.lower())(url, **kwargs)
            response.raise_for_status()
            return response.json()
        
        except httpx.HTTPStatusError as e:
            error_details = e.response.text if hasattr(e, 'response') and e.response.status_code == 422 else str(e)
            logger.error("%s request to %s failed with status %s: %s", 
                        method, url, getattr(e.response, 'status_code', 'unknown'), error_details)
            
            # در برخی خطاها نیازی به تلاش مجدد نیست
            if hasattr(e, 'response') and e.response.status_code in (401, 403, 404, 422):
                if e.response.status_code == 404:
                    return {"_not_found": True}
                break
                
        except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.TimeoutException) as e:
            # خطاهای شبکه که احتمالاً با تلاش مجدد رفع می‌شوند
            logger.warning("%s request to %s failed with network error: %s (retry %d/%d)", 
                        method, url, str(e), retries + 1, MAX_RETRIES)
            
        except Exception as e:
            logger.error("%s request to %s failed with unexpected error: %s", 
                        method, url, str(e), exc_info=True)
            break
            
        finally:
            retries += 1
            if client and retries > MAX_RETRIES:
                await client.aclose()
                client = None
            elif retries <= MAX_RETRIES:
                # استراتژی exponential backoff برای تلاش مجدد
                await asyncio.sleep(BASE_RETRY_DELAY * (2 ** (retries - 1)))
    
    if client:
        await client.aclose()
    return None

async def create_hiddify_user(plan_days: int, plan_gb: float, user_telegram_id: str, custom_name: str = "") -> Optional[Dict[str, Any]]:
    """
    ایجاد کاربر جدید در پنل Hiddify
    """
    endpoint = _get_base_url() + "user/"

    random_suffix = uuid.uuid4().hex[:4]
    base_name = custom_name if custom_name else f"tg-{user_telegram_id.split(':')[-1]}"
    unique_user_name = f"{base_name}-{random_suffix}"

    # اجازه حجم اعشاری (زیر 1GB) => float
    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0

    payload = {
        "name": unique_user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": usage_limit_gb,
        "comment": user_telegram_id
    }

    response_data = await _make_request(
        'post', 
        endpoint, 
        json=payload, 
        headers=_get_api_headers(),
        timeout=20.0
    )
    
    if not response_data or not response_data.get("uuid"):
        logger.error("create_hiddify_user: Failed to create user or UUID missing in response")
        return None
        
    user_uuid = response_data.get("uuid")
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    return {"full_link": f"https://{sub_domain}/{sub_path}/{user_uuid}/", "uuid": user_uuid}

async def get_user_info(user_uuid: str) -> Optional[Dict[str, Any]]:
    """
    دریافت اطلاعات کاربر از پنل Hiddify
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    return await _make_request('get', endpoint, headers=_get_api_headers(), timeout=10.0)

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    """
    تمدید سرویس کاربر با PATCH به endpoint کاربر (سازگار با Hiddify API v2.2.0)
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0

    payload = {
        "package_days": int(plan_days),
        "usage_limit_GB": usage_limit_gb,
    }
    
    return await _make_request('patch', endpoint, json=payload, headers=_get_api_headers(), timeout=30.0)

async def delete_user_from_panel(user_uuid: str) -> bool:
    """
    حذف کاربر از پنل هیدیفای (API v2.2.0)
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    response = await _make_request('delete', endpoint, headers=_get_api_headers(), timeout=15.0)
    
    # اگر کاربر با موفقیت حذف شد یا از قبل وجود نداشت
    if response is not None or response == {"_not_found": True}:
        logger.info(f"Successfully deleted/not-found user {user_uuid} from panel.")
        return True
    return False

async def check_api_connection() -> bool:
    """
    بررسی اتصال به API و صحت کلید API
    """
    try:
        # تلاش برای دریافت لیست کاربران (فقط اولین صفحه)
        endpoint = _get_base_url() + "user/?page=1&per_page=1"
        response = await _make_request('get', endpoint, headers=_get_api_headers(), timeout=5.0)
        return response is not None
    except Exception as e:
        logger.error(f"API connection check failed: {e}", exc_info=True)
        return False