# filename: hiddify_api.py
# -*- coding: utf-8 -*-

import asyncio
import httpx
import uuid
import random
import logging
from typing import Optional, Dict, Any

from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

# اختیاری: اگر SSL خودامضاست، این کلید را در config.py تعریف کنید (پیش‌فرض True)
try:
    from config import HIDDIFY_API_VERIFY_SSL
except Exception:
    HIDDIFY_API_VERIFY_SSL = True

logger = logging.getLogger(__name__)

# Retry settings
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0


def _get_base_url() -> str:
    # URL برای API v2.x
    clean_admin = str(ADMIN_PATH or "").strip().strip("/")
    return f"https://{PANEL_DOMAIN}/{clean_admin}/api/v2/admin/"


def _get_api_headers() -> dict:
    return {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _client_sub_path() -> str:
    """
    مسیر کلاینت برای لینک اشتراک.
    - اگر SUB_PATH خالی باشد: sub
    - اگر SUB_PATH شامل سکرت/ساختار خاص است، همان را استفاده می‌کنیم (بدون دست‌کاری).
    """
    p = str(SUB_PATH or "sub").strip().strip("/")
    return p or "sub"


async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    # http2 اختیاری
    try:
        import h2  # noqa: F401
        http2_support = True
    except ImportError:
        http2_support = False
    return httpx.AsyncClient(timeout=timeout, http2=http2_support, verify=HIDDIFY_API_VERIFY_SSL)


async def _make_request(method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    اجرای درخواست HTTP با مکانیزم retry و مدیریت خطای پیشرفته.
    404 را به صورت {"_not_found": True} برمی‌گرداند.
    برای پاسخ‌های بدون بدنه (مثلاً 204) یک dict خالی {} برمی‌گرداند.
    """
    client: Optional[httpx.AsyncClient] = None
    retries = 0

    while retries <= MAX_RETRIES:
        try:
            if client is None:
                client = await _make_client(timeout=kwargs.get("timeout", 20.0))

            resp: httpx.Response = await getattr(client, method.lower())(url, **kwargs)
            resp.raise_for_status()

            try:
                return resp.json()
            except ValueError:
                # بدنه خالی (مثل 204)
                return {}

        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            text = e.response.text if e.response is not None else str(e)

            # 404: کاربر/منبع وجود ندارد → حالت موفق برای حذف/چک موجود نبودن
            if status == 404:
                logger.info("%s %s -> 404 Not Found (returning _not_found)", method.upper(), url)
                return {"_not_found": True}

            # 401/403/422: خطاهای غیرقابل retry
            if status in (401, 403, 422):
                logger.error(
                    "%s request to %s failed with status %s: %s",
                    method.upper(),
                    url,
                    status,
                    text,
                )
                break

            # سایر وضعیت‌ها (مانند 5xx): قابل retry
            logger.warning(
                "%s request to %s failed with status %s: %s (retry %d/%d)",
                method.upper(),
                url,
                status,
                text,
                retries + 1,
                MAX_RETRIES,
            )

        except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.TimeoutException) as e:
            logger.warning(
                "%s request to %s network error: %s (retry %d/%d)",
                method.upper(),
                url,
                str(e),
                retries + 1,
                MAX_RETRIES,
            )

        except Exception as e:
            logger.error(
                "%s request to %s unexpected error: %s",
                method.upper(),
                url,
                str(e),
                exc_info=True,
            )
            break

        finally:
            retries += 1
            if retries <= MAX_RETRIES:
                await asyncio.sleep(BASE_RETRY_DELAY * (2 ** (retries - 1)))

    if client:
        await client.aclose()
    return None


async def create_hiddify_user(
    plan_days: int,
    plan_gb: float,
    user_telegram_id: str,
    custom_name: str = "",
) -> Optional[Dict[str, Any]]:
    """
    ساخت کاربر جدید در پنل و برگرداندن uuid + لینک اشتراک صحیح.
    """
    endpoint = _get_base_url() + "user/"

    random_suffix = uuid.uuid4().hex[:4]
    base_name = custom_name if custom_name else f"tg-{user_telegram_id.split(':')[-1]}"
    unique_user_name = f"{base_name}-{random_suffix}"

    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0

    payload = {
        "name": unique_user_name,
        "package_days": int(plan_days),
        "usage_limit_GB": usage_limit_gb,
        "comment": user_telegram_id,
        # کمک به سازگاری برخی پنل‌ها
        "current_usage_GB": 0,
    }

    data = await _make_request("post", endpoint, json=payload, headers=_get_api_headers(), timeout=20.0)
    if not data or not data.get("uuid"):
        logger.error("create_hiddify_user: failed or UUID missing (check PANEL_DOMAIN/ADMIN_PATH/API_KEY/SUB_PATH)")
        return None

    user_uuid = data.get("uuid")
    client_path = _client_sub_path()
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    full_link = f"https://{sub_domain}/{client_path}/{user_uuid}/"
    return {"full_link": full_link, "uuid": user_uuid}


async def get_user_info(user_uuid: str) -> Optional[Dict[str, Any]]:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    return await _make_request("get", endpoint, headers=_get_api_headers(), timeout=10.0)


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    """
    تمدید سرویس کاربر با PATCH به endpoint کاربر (سازگار با Hiddify API v2).
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0

    payload = {
        "package_days": int(plan_days),
        "usage_limit_GB": usage_limit_gb,
        # (در صورت نیاز می‌توان start_date را هم ست کرد)
    }

    return await _make_request("patch", endpoint, json=payload, headers=_get_api_headers(), timeout=30.0)


async def delete_user_from_panel(user_uuid: str) -> bool:
    """
    حذف کاربر از پنل هیدیفای (API v2)
    - اگر 404 برگردد، True برمی‌گردانیم چون کاربر در پنل وجود ندارد (idempotent).
    - اگر خطای شبکه باشد، با یک GET نهایی بررسی می‌کنیم.
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    data = await _make_request("delete", endpoint, headers=_get_api_headers(), timeout=15.0)

    # موفقیت: 200/204 بدون بدنه -> {}
    if data == {}:
        logger.info("Successfully deleted user %s from panel.", user_uuid)
        return True

    # موفقیت: 404 (not found)
    if isinstance(data, dict) and data.get("_not_found"):
        logger.info("Successfully deleted/not-found user %s from panel.", user_uuid)
        return True

    # نامشخص: GET نهایی
    if data is None:
        probe = await get_user_info(user_uuid)
        if isinstance(probe, dict) and probe.get("_not_found"):
            logger.info("Delete treated as success for %s (verified _not_found after delete).", user_uuid)
            return True

    return False


async def check_api_connection() -> bool:
    """
    بررسی اتصال به API و صحت کلید API
    """
    try:
        endpoint = _get_base_url() + "user/?page=1&per_page=1"
        response = await _make_request("get", endpoint, headers=_get_api_headers(), timeout=5.0)
        return response is not None
    except Exception as e:
        logger.error("API connection check failed: %s", e, exc_info=True)
        return False