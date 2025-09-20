# filename: hiddify_api.py
# -*- coding: utf-8 -*-

import asyncio
import httpx
import uuid
import random
import logging
import types
import time
from typing import Optional, Dict, Any

# --- Robust config loader ---
try:
    import config as _cfg
except Exception:
    _cfg = types.SimpleNamespace()

PANEL_DOMAIN = getattr(_cfg, "PANEL_DOMAIN", "")
ADMIN_PATH = getattr(_cfg, "ADMIN_PATH", "")
API_KEY = getattr(_cfg, "API_KEY", "")
SUB_DOMAINS = getattr(_cfg, "SUB_DOMAINS", []) or []
SUB_PATH = getattr(_cfg, "SUB_PATH", "sub")
PANEL_SECRET_UUID = getattr(_cfg, "PANEL_SECRET_UUID", "")
HIDDIFY_API_VERIFY_SSL = getattr(_cfg, "HIDDIFY_API_VERIFY_SSL", True)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0
VERIFICATION_RETRIES = 3 # کمتر میکنیم تا سریعتر به فاز دوم برسیم
VERIFICATION_DELAY = 1.5


def _normalize_host(host: str) -> str:
    h = (host or "").strip()
    if not h: return ""
    if not (h.startswith("http://") or h.startswith("https://")): h = "https://" + h
    return h.rstrip("/")

def _strip_scheme(host: str) -> str:
    h = (host or "").strip()
    if h.startswith("https://"): h = h[len("https://"):]
    elif h.startswith("http://"): h = h[len("http://"):]
    return h.strip("/")

def _normalize_subdomains(sd):
    if isinstance(sd, str):
        parts = [p.strip() for p in sd.split(",") if p.strip()]
    else:
        parts = [str(x).strip() for x in (sd or []) if str(x).strip()]
    return [_strip_scheme(p) for p in parts]

SUB_DOMAINS = _normalize_subdomains(SUB_DOMAINS)

def _get_base_url() -> str:
    base = _normalize_host(PANEL_DOMAIN)
    if not base:
        logger.error("PANEL_DOMAIN is not set in config.py.")
        base = "https://localhost"
    clean_admin = str(ADMIN_PATH or "").strip().strip("/")
    return f"{base}/{clean_admin}/api/v2/admin/" if clean_admin else f"{base}/api/v2/admin/"

def _get_api_headers() -> dict:
    return {"Hiddify-API-Key": API_KEY, "Content-Type": "application/json", "Accept": "application/json"}

async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=HIDDIFY_API_VERIFY_SSL, follow_redirects=True)

async def _make_request(method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
    headers = kwargs.pop("headers", _get_api_headers())
    delay = BASE_RETRY_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with await _make_client(timeout=kwargs.get("timeout", 20.0)) as client:
                resp = await getattr(client, method.lower())(url, headers=headers, **kwargs)
                resp.raise_for_status()
                try: return resp.json()
                except ValueError: return {}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            text = e.response.text if e.response is not None else str(e)
            if status == 422:
                logger.error("%s to %s failed with 422 Validation Error: %s", method.upper(), url, text)
                break
            logger.warning("%s to %s failed with %s (retry %d/%d)", method.upper(), url, status, attempt, MAX_RETRIES)
        except Exception as e:
            logger.error("%s to %s failed: %s", method.upper(), url, e)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(delay)
            delay *= 2
    return None

async def get_user_info(user_uuid: str, **kwargs) -> Optional[Dict[str, Any]]:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    return await _make_request("get", endpoint)

def _get_start_ts_from_panel(info: Dict[str, Any]) -> Optional[int]:
    for key in ("last_reset_time", "start_date"):
        val = info.get(key)
        if val:
            try:
                ts = float(val)
                return int(ts / 1000) if ts > 1e12 else int(ts)
            except (ValueError, TypeError):
                continue
    return None

async def _apply_and_verify_plan(user_uuid: str, plan_days: int, plan_gb: float, is_new_user: bool = False) -> Optional[Dict[str, Any]]:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    exact_days = int(plan_days)

    # Payload پایه برای حجم و مصرف
    payload = {"current_usage_GB": 0}
    if plan_gb is None or plan_gb <= 0:
        payload["usage_limit_GB"] = 1000.0  # Large quota for unlimited
    else:
        payload["usage_limit_GB"] = float(plan_gb)

    # --- تلاش اول: ریست ساده ---
    if is_new_user:
        payload["package_days"] = exact_days
    else:
        # برای تمدید، فقط روزهای پلن را ست میکنیم به امید اینکه پنل ریست کند
        payload["package_days"] = exact_days
    
    logger.info("Attempt 1 (Simple Reset): Patching user %s with payload %s", user_uuid, payload)
    response = await _make_request("patch", endpoint, json=payload)

    if response is not None:
        for attempt in range(VERIFICATION_RETRIES):
            await asyncio.sleep(VERIFICATION_DELAY)
            after_info = await get_user_info(user_uuid)
            if not after_info: continue

            after_days = int(after_info.get("package_days", -1))
            start_ts = _get_start_ts_from_panel(after_info)
            now_ts = int(time.time())

            # اگر زمان شروع نزدیک به الان بود، یعنی ریست موفق بوده
            if after_days == exact_days and start_ts and (now_ts - start_ts) < 3600: # 1 hour tolerance
                logger.info("Simple Reset successful for %s on attempt %d.", user_uuid, attempt + 1)
                return after_info
        
        logger.warning("Simple Reset for %s failed verification. Proceeding to fallback.", user_uuid)

    # --- تلاش دوم (Fallback): محاسبه و افزایش روزها ---
    if not is_new_user:
        current_info = await get_user_info(user_uuid)
        if not current_info:
            logger.error("Cannot get current info for fallback renewal of %s.", user_uuid)
            return None

        start_ts = _get_start_ts_from_panel(current_info)
        if not start_ts:
            logger.error("Cannot determine start date for fallback renewal of %s.", user_uuid)
            return None # اگر تاریخ شروع نامشخص باشد، نمیتوانیم محاسبه کنیم

        now_ts = int(time.time())
        elapsed_days = int((now_ts - start_ts) / 86400)
        
        # اگر کاربر بیش از یک روز از سرویسش گذشته، روزها را اضافه میکنیم
        if elapsed_days > 0:
            new_package_days = exact_days + elapsed_days
            payload["package_days"] = new_package_days
            logger.info("Attempt 2 (Fallback): Bumping days for %s to %d", user_uuid, new_package_days)
            response = await _make_request("patch", endpoint, json=payload)
            if response is None:
                logger.error("Fallback renewal PATCH failed for %s", user_uuid)
                return None
        else: # اگر کمتر از یک روز گذشته، همان پلن اصلی کافیست
            logger.info("Skipping day bump for %s as elapsed days is not positive.", user_uuid)
            return await get_user_info(user_uuid) # اطلاعات فعلی را برمیگردانیم


        # تایید نهایی بعد از تلاش دوم
        for attempt in range(VERIFICATION_RETRIES):
            await asyncio.sleep(VERIFICATION_DELAY)
            after_info = await get_user_info(user_uuid)
            if after_info and int(after_info.get("package_days", -1)) == new_package_days:
                logger.info("Fallback renewal for %s verified.", user_uuid)
                return after_info
    
    logger.error("All renewal attempts for UUID %s failed.", user_uuid)
    return None


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    return await _apply_and_verify_plan(user_uuid, plan_days, plan_gb, is_new_user=False)


async def delete_user_from_panel(user_uuid: str) -> bool:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    data = await _make_request("delete", endpoint)
    if data == {}: return True
    if isinstance(data, dict) and data.get("_not_found"): return True
    if data is None:
        probe = await get_user_info(user_uuid)
        if isinstance(probe, dict) and probe.get("_not_found"): return True
    return False


async def check_api_connection() -> bool:
    try:
        endpoint = f"{_get_base_url()}user/?page=1&per_page=1"
        response = await _make_request("get", endpoint)
        return response is not None
    except Exception:
        return False