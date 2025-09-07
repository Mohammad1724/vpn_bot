# filename: hiddify_api.py
# -*- coding: utf-8 -*-
import asyncio
import httpx
import uuid
import random
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

from config import (
    PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH,
    PANEL_SECRET_UUID, HIDDIFY_API_VERIFY_SSL
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0


def _select_server() -> Dict[str, Any]:
    """برگشت تنظیمات پنل اصلی."""
    return {
        "name": "Main",
        "panel_domain": PANEL_DOMAIN,
        "admin_path": ADMIN_PATH,
        "sub_path": SUB_PATH,
        "api_key": API_KEY,
        "sub_domains": SUB_DOMAINS or [],
    }

def _get_base_url(server: Dict[str, Any]) -> str:
    return f"https://{server['panel_domain']}/{server['admin_path']}/api/v2/admin/"

def _get_api_headers(server: Dict[str, Any]) -> dict:
    return {
        "Hiddify-API-Key": server["api_key"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=HIDDIFY_API_VERIFY_SSL)

async def _make_request(method: str, url: str, server: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
    headers = kwargs.pop("headers", None) or _get_api_headers(server)
    delay = BASE_RETRY_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with await _make_client(timeout=kwargs.get("timeout", 20.0)) as client:
                resp = await getattr(client, method.lower())(url, headers=headers, **kwargs)
                resp.raise_for_status()
                try:
                    return resp.json()
                except ValueError:
                    return {}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            text = e.response.text if e.response is not None else str(e)
            logger.warning("%s %s -> %s: %s (attempt %d/%d)", method.upper(), url, status, text, attempt, MAX_RETRIES)
            if status == 404:
                return {"_not_found": True}
            if status in (401, 403, 422):
                break
        except Exception as e:
            logger.error("%s %s unexpected: %s", method.upper(), url, str(e), exc_info=True)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(delay)
            delay *= 2
    return None

def _extract_usage_gb(payload: Dict[str, Any]) -> Optional[float]:
    if not isinstance(payload, dict):
        return None
    for k in ("current_usage_GB", "usage_GB", "used_GB"):
        if k in payload:
            try:
                return float(payload[k])
            except Exception:
                return None
    return None

def _looks_like_secret(s: str) -> bool:
    s = (s or "").strip().strip("/")
    if not s or s.lower() in ("sub", "api", "v1", "v2", "admin"):
        return False
    # توکن Secret معمولاً از کاراکترهای الفبایی-عددی و - یا _ با طول مناسب تشکیل می‌شود
    return re.fullmatch(r"[A-Za-z0-9\-_]{8,64}", s) is not None

def _expanded_api_bases_for_server(server: Dict[str, Any]) -> List[str]:
    """
    ساخت امن مسیر Expanded API:
    - اگر SUB_PATH == SECRET باشد، از sub/SECRET استفاده می‌کنیم.
    - اگر SECRET از قبل در SUB_PATH هست، دوباره اضافه نمی‌کنیم.
    - اگر PANEL_SECRET_UUID خالی بود و SUB_PATH شبیه SECRET بود، از SUB_PATH به‌عنوان SECRET استفاده می‌کنیم.
    """
    domain = (server.get("panel_domain") or PANEL_DOMAIN or "").strip()
    raw_cpath = (server.get("sub_path") or SUB_PATH or "sub")
    cpath = str(raw_cpath).strip().strip("/")
    secret = (PANEL_SECRET_UUID or "").strip().strip("/")

    bases: List[str] = []
    if not domain:
        return bases

    lc_cpath = cpath.lower()
    lc_secret = secret.lower()
    base_path: Optional[str] = None

    if secret:
        # SECRET مشخص است
        if lc_cpath == lc_secret:
            base_path = f"sub/{secret}"
        else:
            parts = [p.strip() for p in cpath.split("/") if p.strip()]
            parts_l = [p.lower() for p in parts]
            if lc_secret in parts_l:
                base_path = cpath  # SECRET از قبل در مسیر حضور دارد
            else:
                base_path = f"{cpath}/{secret}" if cpath else f"sub/{secret}"
    else:
        # SECRET خالی است: سعی می‌کنیم از SUB_PATH استخراج کنیم
        parts = [p.strip() for p in cpath.split("/") if p.strip()]
        if not parts:
            return bases
        if parts[0].lower() == "sub":
            if len(parts) >= 2 and _looks_like_secret(parts[1]):
                base_path = f"sub/{parts[1]}"
            else:
                return bases
        else:
            if _looks_like_secret(parts[0]):
                base_path = f"sub/{parts[0]}"
            else:
                return bases

    if not base_path:
        return bases

    bases.append(f"https://{domain}/{base_path}/api/v1")
    return bases

async def _post_json_noauth(url: str, body: Any, timeout: float = 20.0) -> Tuple[int, Any]:
    try:
        async with await _make_client(timeout) as client:
            resp = await client.post(url, json=body)
            data = None
            try:
                data = resp.json()
            except Exception:
                data = None
            if resp.status_code >= 400:
                logger.warning("POST %s -> %s: %s", url, resp.status_code, data)
            return resp.status_code, data
    except Exception as e:
        logger.debug("POST %s failed: %s", url, e)
        return 0, None

async def _get_noauth(url: str, timeout: float = 20.0) -> Tuple[int, Any]:
    try:
        async with await _make_client(timeout) as client:
            resp = await client.get(url)
            data = None
            try:
                data = resp.json()
            except Exception:
                data = None
            if resp.status_code >= 400:
                logger.warning("GET %s -> %s: %s", url, resp.status_code, data)
            return resp.status_code, data
    except Exception as e:
        logger.debug("GET %s failed: %s", url, e)
        return 0, None

async def _expanded_user_update(user_uuid: str, plan_days: int, plan_gb: float) -> bool:
    server = _select_server()
    bases = _expanded_api_bases_for_server(server)
    if not bases:
        logger.error("Expanded API base URL could not be constructed. Check PANEL_SECRET_UUID/SUB_PATH in config.")
        return False
    body = {
        "uuid": user_uuid,
        "package_days": int(plan_days),
        "usage_limit_GB": float(plan_gb or 0.0),
        "start_date": datetime.now(timezone.utc).isoformat(),
        "current_usage_GB": 0
    }
    for base in bases:
        status, _ = await _post_json_noauth(f"{base}/user/", body, timeout=20.0)
        if 200 <= status < 300:
            return True
    return False

async def _expanded_update_usage() -> bool:
    server = _select_server()
    bases = _expanded_api_bases_for_server(server)
    if not bases:
        return False
    for base in bases:
        status, _ = await _get_noauth(f"{base}/update_usage/", timeout=45.0)
        if 200 <= status < 300:
            return True
    return False

async def _admin_renew_fallback(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    """
    وقتی Expanded API در دسترس نیست: با Admin API پلن را به‌روزرسانی می‌کنیم.
    چند payload مختلف تست می‌شود تا با نسخه‌های مختلف پنل سازگار باشد.
    """
    server = _select_server()
    url = f"{_get_base_url(server)}user/{user_uuid}/"
    payloads = [
        {  # کامل
            "package_days": int(plan_days),
            "usage_limit_GB": float(plan_gb or 0.0),
            "start_date": datetime.now(timezone.utc).isoformat(),
            "current_usage_GB": 0
        },
        {  # بدون current_usage_GB
            "package_days": int(plan_days),
            "usage_limit_GB": float(plan_gb or 0.0),
            "start_date": datetime.now(timezone.utc).isoformat()
        },
        {  # حداقلی
            "package_days": int(plan_days),
            "usage_limit_GB": float(plan_gb or 0.0)
        },
    ]
    for p in payloads:
        resp = await _make_request("patch", url, server, json=p, timeout=20.0)
        if resp is not None:
            info = await get_user_info(user_uuid)
            return info if isinstance(info, dict) else resp
    return None

async def create_hiddify_user(plan_days: int, plan_gb: float, user_telegram_id: str, custom_name: str = "") -> Optional[Dict[str, Any]]:
    server = _select_server()
    endpoint = _get_base_url(server) + "user/"
    random_suffix = uuid.uuid4().hex[:4]
    base_name = custom_name if custom_name else f"tg-{user_telegram_id.split(':')[-1]}"
    unique_user_name = f"{base_name}-{random_suffix}"
    payload = {"name": unique_user_name, "package_days": int(plan_days), "comment": user_telegram_id}
    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0
    if usage_limit_gb > 0:
        payload["usage_limit_GB"] = usage_limit_gb
    data = await _make_request("post", endpoint, server, json=payload, timeout=20.0)
    if not data or not data.get("uuid"):
        logger.error("create_hiddify_user: failed or UUID missing")
        return None
    user_uuid = data.get("uuid")
    sub_path = server.get("sub_path") or SUB_PATH or "sub"
    sub_domains = server.get("sub_domains") or []
    sub_domain = random.choice(sub_domains) if sub_domains else server["panel_domain"]
    return {"full_link": f"https://{sub_domain}/{sub_path}/{user_uuid}/", "uuid": user_uuid, "server_name": "Main"}

async def get_user_info(user_uuid: str) -> Optional[Dict[str, Any]]:
    server = _select_server()
    endpoint = f"{_get_base_url(server)}user/{user_uuid}/"
    return await _make_request("get", endpoint, server, timeout=10.0)

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    """
    تمدید کاربر:
    - اگر Expanded API در دسترس باشد، با آن ریست کامل انجام می‌دهیم و انتظار داریم مصرف ~0 شود.
    - اگر در دسترس نباشد یا شکست بخورد، با Admin API پلن را به‌روزرسانی می‌کنیم (fallback).
    - در نهایت اطلاعات کاربر را برمی‌گردانیم (None یعنی شکست قطعی).
    """
    # تلاش با Expanded API
    exp_ok = await _expanded_user_update(user_uuid, plan_days, plan_gb)
    if not exp_ok:
        logger.error("Expanded user update failed for %s. Check PANEL_SECRET_UUID and sub_path.", user_uuid)

    if exp_ok:
        await _expanded_update_usage()
        await asyncio.sleep(1.0)
        last_info: Optional[Dict[str, Any]] = None
        for _ in range(5):
            info = await get_user_info(user_uuid)
            if isinstance(info, dict) and not info.get("_not_found"):
                last_info = info
                used = _extract_usage_gb(info) or 0.0
                if used <= 0.05:
                    return info
            await asyncio.sleep(1.0)
        # اگر نتوانستیم ریست را تایید کنیم، همان اطلاعات آخر را برگردانیم
        return last_info

    # Fallback با Admin API
    fb = await _admin_renew_fallback(user_uuid, plan_days, plan_gb)
    return fb

async def delete_user_from_panel(user_uuid: str) -> bool:
    server = _select_server()
    data = await _make_request("delete", f"{_get_base_url(server)}user/{user_uuid}/", server, timeout=15.0)
    if data == {}:
        return True
    if isinstance(data, dict) and data.get("_not_found"):
        return True
    if data is None:
        probe = await get_user_info(user_uuid)
        if isinstance(probe, dict) and probe.get("_not_found"):
            return True
    return False

async def check_api_connection() -> bool:
    try:
        server = _select_server()
        r = await _make_request("get", _get_base_url(server) + "user/?page=1&per_page=1", server, timeout=5.0)
        return r is not None
    except Exception:
        return False

# --- استاب برای بی‌خیال شدن از نودها در همگام‌سازی ---
async def push_nodes_to_panel(bases: Optional[List[str]] = None) -> bool:
    """
    استاب ساده برای جلوگیری از خطای AttributeError در nodes_sync.
    اگر بعداً نیاز به همگام‌سازی واقعی داشتید، پیاده‌سازی را اینجا اضافه کنید.
    """
    try:
        if bases is None:
            bases = _expanded_api_bases_for_server(_select_server())
        if not bases:
            logger.info("push_nodes_to_panel: no bases to push; skipping.")
            return True
        logger.info("push_nodes_to_panel: stub called; bases=%s", bases)
        return True
    except Exception as e:
        logger.warning("push_nodes_to_panel stub failed: %s", e)
        return False