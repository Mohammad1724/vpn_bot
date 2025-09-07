# filename: hiddify_api.py
# -*- coding: utf-8 -*-
import asyncio
import httpx
import uuid
import random
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from config import (
    NODELESS_MODE,
    PANEL_INTEGRATION_ENABLED,
    PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH,
    PANEL_SECRET_UUID, HIDDIFY_API_VERIFY_SSL
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0


def _panel_enabled() -> bool:
    """
    True فقط وقتی که واقعا می‌خواهیم به پنل وصل شویم.
    """
    try:
        return (not NODELESS_MODE) and bool(PANEL_INTEGRATION_ENABLED)
    except Exception:
        # برای سازگاری با کانفیگ‌های قدیمی
        return False


def _select_server() -> Dict[str, Any]:
    # پیکربندی تک‌سرور (بدون جدول نود)
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
                    # 204 No Content یا پاسخ بدون JSON
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
    return re.fullmatch(r"[A-Za-z0-9\-_]{8,64}", s) is not None

def _expanded_api_bases_for_server(server: Dict[str, Any]) -> List[str]:
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
        if lc_cpath == lc_secret:
            base_path = f"sub/{secret}"
        else:
            parts = [p.strip() for p in cpath.split("/") if p.strip()]
            parts_l = [p.lower() for p in parts]
            if lc_secret in parts_l:
                base_path = cpath
            else:
                base_path = f"{cpath}/{secret}" if cpath else f"sub/{secret}"
    else:
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

# ----------------------------- Local stubs (NODELESS) -----------------------------
def _make_local_sub_link(uuid_str: str) -> str:
    # لینک محلی امن با host ثابت برای سازگاری با parser ها
    return f"https://local.service/sub/{uuid_str}/"

async def _nodless_create_user(plan_days: int, plan_gb: float, user_telegram_id: str, custom_name: str = "") -> Dict[str, Any]:
    uid = uuid.uuid4().hex
    return {"full_link": _make_local_sub_link(uid), "uuid": uid, "server_name": "Local"}

async def _nodless_get_info(user_uuid: str) -> Dict[str, Any]:
    now_local_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "uuid": user_uuid,
        "start_date": now_local_str,
        "package_days": 0,
        "usage_limit_GB": 0.0,
        "current_usage_GB": 0.0,
    }

async def _nodless_renew(user_uuid: str, plan_days: int, plan_gb: float) -> Dict[str, Any]:
    now_local_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "uuid": user_uuid,
        "start_date": now_local_str,
        "package_days": int(plan_days),
        "usage_limit_GB": float(plan_gb or 0.0),
        "current_usage_GB": 0.0,
    }

# ----------------------------- Public API -----------------------------
async def create_hiddify_user(plan_days: int, plan_gb: float, user_telegram_id: str, custom_name: str = "") -> Optional[Dict[str, Any]]:
    """
    اگر پنل غیرفعال است، یک UUID محلی و لینک محلی برمی‌گرداند.
    در حالت پنل، کاربر را از طریق Admin API می‌سازد.
    """
    if not _panel_enabled():
        return await _nodless_create_user(plan_days, plan_gb, user_telegram_id, custom_name)

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
    return {"full_link": f"https://{sub_domain}/{sub_path}/{user_uuid}/", "uuid": user_uuid, "server_name": server.get("name") or "Main"}

async def get_user_info(user_uuid: str) -> Optional[Dict[str, Any]]:
    if not _panel_enabled():
        return await _nodless_get_info(user_uuid)
    server = _select_server()
    endpoint = f"{_get_base_url(server)}user/{user_uuid}/"
    return await _make_request("get", endpoint, server, timeout=10.0)

def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        try:
            # ISO 8601
            s2 = s.replace("Z", "+00:00")
            return datetime.fromisoformat(s2)
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue
    return None

def _verify_admin_renew(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]], plan_days: int, plan_gb: float, expected_start_str: str) -> bool:
    if not isinstance(after, dict):
        return False
    # 1) اگر start_date تغییر کرده باشد => موفق
    before_start = _parse_dt((before or {}).get("start_date"))
    after_start = _parse_dt(after.get("start_date"))
    if after_start:
        try:
            expected_dt = datetime.strptime(expected_start_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            expected_dt = None
        if not before_start or (after_start and expected_dt and abs((after_start - expected_dt).total_seconds()) <= 5 * 60):
            return True
        if before_start and after_start and (after_start - before_start).total_seconds() > 60:
            return True

    # 2) تغییر در محدودیت حجم یا تعداد روز
    try:
        if float(after.get("usage_limit_GB", -1)) == float(plan_gb):
            return True
    except Exception:
        pass
    try:
        if int(after.get("package_days", -1)) == int(plan_days):
            return True
    except Exception:
        pass

    return False

async def _admin_renew_fallback(user_uuid: str, plan_days: int, plan_gb: float, before_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    تلاش برای تمدید با Admin API:
    - start_date با فرمت "YYYY-MM-DD HH:MM:SS" ست می‌شود.
    """
    if not _panel_enabled():
        return await _nodless_renew(user_uuid, plan_days, plan_gb)

    server = _select_server()
    url = f"{_get_base_url(server)}user/{user_uuid}/"
    now_local_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    payload_variants = [
        {
            "package_days": int(plan_days),
            "usage_limit_GB": float(plan_gb or 0.0),
            "start_date": now_local_str,
            "current_usage_GB": 0,
        },
        {
            "package_days": int(plan_days),
            "usage_limit_GB": float(plan_gb or 0.0),
            "start_date": now_local_str,
        },
        {
            "package_days": int(plan_days),
            "usage_limit_GB": float(plan_gb or 0.0),
        },
    ]

    for method in ("patch", "put"):
        for p in payload_variants:
            resp = await _make_request(method, url, server, json=p, timeout=20.0)
            if resp is None:
                continue
            # تایید با خواندن وضعیت جدید
            after = await get_user_info(user_uuid)
            if _verify_admin_renew(before_info, after, plan_days, plan_gb, now_local_str):
                logger.info("Renewal via Admin API (%s) applied.", method.upper())
                return after if isinstance(after, dict) else resp

    logger.error("Admin API fallback failed for %s", user_uuid)
    return None

# ---------- Expanded API stubs (to avoid runtime errors if enabled) ----------
async def _expanded_user_update(user_uuid: str, plan_days: int, plan_gb: float) -> bool:
    """
    استاب امن برای Expanded API.
    اگر بعداً خواستی فعالش کنی، می‌تونی اینجا درخواست واقعی بسازی.
    """
    bases = _expanded_api_bases_for_server(_select_server())
    if not bases:
        return False
    # تلاش نمادین؛ چون پروتکل دقیق مشخص نیست
    url = f"{bases[0]}/user/{user_uuid}/"
    payload = {
        "package_days": int(plan_days),
        "usage_limit_GB": float(plan_gb or 0.0),
        "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_usage_GB": 0,
    }
    status, _ = await _post_json_noauth(url, payload, timeout=15.0)
    return 200 <= status < 300

async def _expanded_update_usage() -> None:
    # استاب: اگر نیاز شد، می‌توان endpoint مناسب را فراخوانی کرد.
    return None

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    """
    تمدید کاربر:
    - در حالت NODELESS: صرفاً مقدار ساختگی سازگار برمی‌گرداند.
    - در حالت پنل: ابتدا تلاش Expanded (اختیاری)، سپس Admin API fallback با راستی‌آزمایی.
    """
    if not _panel_enabled():
        return await _nodless_renew(user_uuid, plan_days, plan_gb)

    before = await get_user_info(user_uuid)

    # 1) Expanded API (اختیاری)
    exp_ok = False
    bases = _expanded_api_bases_for_server(_select_server())
    if bases:
        exp_ok = await _expanded_user_update(user_uuid, plan_days, plan_gb)
        if not exp_ok:
            logger.error("Expanded user update failed for %s. Check PANEL_SECRET_UUID and sub_path.", user_uuid)

        # تلاش برای بروزرسانی و تایید ریست مصرف
        if exp_ok:
            await _expanded_update_usage()
            await asyncio.sleep(1.0)
            for _ in range(5):
                info = await get_user_info(user_uuid)
                if isinstance(info, dict) and not info.get("_not_found"):
                    used = _extract_usage_gb(info) or 0.0
                    if used <= 0.05:
                        return info
                await asyncio.sleep(1.0)

    # 2) Admin API fallback با راستی‌آزمایی
    logger.info("Falling back to Admin API for renewal...")
    fb = await _admin_renew_fallback(user_uuid, plan_days, plan_gb, before_info=before)
    return fb

async def delete_user_from_panel(user_uuid: str) -> bool:
    if not _panel_enabled():
        return True
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
    if not _panel_enabled():
        return True
    try:
        server = _select_server()
        r = await _make_request("get", _get_base_url(server) + "user/?page=1&per_page=1", server, timeout=5.0)
        return r is not None
    except Exception:
        return False

# --- استاب سازگار برای سازگاری با کدهای قدیمی ---
async def push_nodes_to_panel(bases: Optional[List[str]] = None) -> bool:
    try:
        logger.info("push_nodes_to_panel: nodless mode or single-server setup; skipping.")
        return True
    except Exception as e:
        logger.warning("push_nodes_to_panel stub failed: %s", e)
        return False