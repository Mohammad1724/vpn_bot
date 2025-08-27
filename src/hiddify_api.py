# -*- coding: utf-8 -*-

import asyncio
import httpx
import uuid
import random
import logging
from typing import Optional, Dict, Any, List

import database as db
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

# Optional multi-server configs (fallbacks if DB nodes are empty)
try:
    from config import MULTI_SERVER_ENABLED, SERVERS, DEFAULT_SERVER_NAME, SERVER_SELECTION_POLICY
except Exception:
    MULTI_SERVER_ENABLED = False
    SERVERS = []
    DEFAULT_SERVER_NAME = None
    SERVER_SELECTION_POLICY = "first"

logger = logging.getLogger(__name__)

# Retry settings
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0


# ========================= Server selection (DB-first) =========================
def _fallback_server_dict() -> Dict[str, Any]:
    return {
        "name": DEFAULT_SERVER_NAME or "Main",
        "panel_domain": PANEL_DOMAIN,
        "admin_path": ADMIN_PATH,
        "sub_path": SUB_PATH,
        "api_key": API_KEY,
        "sub_domains": SUB_DOMAINS or [],
        "panel_type": "hiddify",
        "is_active": 1,
        "capacity": 0,
        "current_users": 0,
    }


def _db_server_from_node(n: dict) -> Dict[str, Any]:
    # تبدیل رکورد دیتابیس نود به ساختار سرور
    return {
        "name": n["name"],
        "panel_domain": n["panel_domain"],
        "admin_path": n["admin_path"],
        "sub_path": n["sub_path"],
        "api_key": n["api_key"],
        "sub_domains": n.get("sub_domains") or [],
        "panel_type": n.get("panel_type", "hiddify"),
        "is_active": n.get("is_active", 1),
        "capacity": int(n.get("capacity") or 0),
        "current_users": int(n.get("current_users") or 0),
    }


def _get_server_by_name_config(name: str) -> Optional[Dict[str, Any]]:
    for s in SERVERS or []:
        if str(s.get("name")) == str(name):
            # همگن‌سازی کلیدها برای سازگاری
            return {
                "name": s.get("name"),
                "panel_domain": s.get("panel_domain"),
                "admin_path": s.get("admin_path"),
                "sub_path": (s.get("sub_path") or s.get("admin_path")),
                "api_key": s.get("api_key"),
                "sub_domains": s.get("sub_domains") or [],
                "panel_type": "hiddify",
                "is_active": 1,
                "capacity": 0,
                "current_users": 0,
            }
    return None


def _db_list_active_hiddify_servers() -> List[Dict[str, Any]]:
    try:
        nodes = db.list_nodes(only_active=True)
        servers: List[Dict[str, Any]] = []
        for n in nodes:
            if str(n.get("panel_type", "hiddify")).lower() != "hiddify":
                continue
            servers.append(_db_server_from_node(n))
        return servers
    except Exception:
        return []


def _db_get_server_by_name(name: str) -> Optional[Dict[str, Any]]:
    try:
        n = db.get_node_by_name(name)
        if not n:
            return None
        if str(n.get("panel_type", "hiddify")).lower() != "hiddify":
            return None
        return _db_server_from_node(n)
    except Exception:
        return None


def _pick_least_loaded(servers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    انتخاب نود با بیشترین ظرفیت خالی (capacity - current_users).
    اگر current_users در DB به‌روز نباشد، شمارش زنده سرویس‌ها از active_services گرفته می‌شود.
    """
    best = None
    best_free = -1
    for s in servers:
        cap = int(s.get("capacity") or 0)
        curr = int(s.get("current_users") or 0)
        try:
            live = db.count_services_on_node(s["name"])
            curr = max(curr, live)
        except Exception:
            pass
        free = cap - curr if cap > 0 else 0
        if free > best_free:
            best = s
            best_free = free
    return best or (servers[0] if servers else _fallback_server_dict())


def _select_server(server_name: Optional[str] = None) -> Dict[str, Any]:
    """
    انتخاب نود/سرور برای عملیات:
    1) اگر server_name مشخص باشد: ابتدا بین نودهای DB، سپس در config.SERVERS جست‌وجو می‌شود.
    2) اگر نودهای فعال در DB موجود باشند: طبق SERVER_SELECTION_POLICY انتخاب می‌شود
       - least_loaded: بیشترین ظرفیت خالی
       - by_name: اگر DEFAULT_SERVER_NAME در DB موجود و فعال باشد، همان؛ وگرنه اولین نود
       - first (پیش‌فرض): اولین نود فعال
    3) در صورت نبود نود در DB: از config.SERVERS (اگر MULTI_SERVER_ENABLED) یا تک‌سرور fallback استفاده می‌شود.
    """
    # 1) نام مشخص
    if server_name:
        srv = _db_get_server_by_name(server_name)
        if srv:
            return srv
        srv = _get_server_by_name_config(server_name)
        if srv:
            return srv

    # 2) ترجیح DB
    db_servers = _db_list_active_hiddify_servers()
    if db_servers:
        policy = str(SERVER_SELECTION_POLICY or "first").lower()
        if policy in ("least_loaded", "capacity", "free"):
            picked = _pick_least_loaded(db_servers)
            return picked or db_servers[0]
        if policy == "by_name" and DEFAULT_SERVER_NAME:
            named = _db_get_server_by_name(DEFAULT_SERVER_NAME)
            if named and int(named.get("is_active", 1)) == 1:
                return named
            return db_servers[0]
        # first (default)
        return db_servers[0]

    # 3) fallback config
    if MULTI_SERVER_ENABLED and SERVERS:
        policy = str(SERVER_SELECTION_POLICY or "first").lower()
        if policy == "by_name" and DEFAULT_SERVER_NAME:
            srv = _get_server_by_name_config(DEFAULT_SERVER_NAME)
            if srv:
                return srv
        # first
        return _get_server_by_name_config(SERVERS[0].get("name")) or _fallback_server_dict()

    # 4) تک‌سرور
    return _fallback_server_dict()


# ========================= HTTP helpers =========================
def _get_base_url(server: Dict[str, Any]) -> str:
    return f"https://{server['panel_domain']}/{server['admin_path']}/api/v2/admin/"


def _get_api_headers(server: Dict[str, Any]) -> dict:
    return {
        "Hiddify-API-Key": server["api_key"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    try:
        import h2  # noqa: F401
        http2_support = True
    except ImportError:
        http2_support = False
    return httpx.AsyncClient(timeout=timeout, http2=http2_support)


async def _make_request(method: str, url: str, server: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
    """
    اجرای درخواست HTTP با retry. 404 => {"_not_found": True}. پاسخ بدون بدنه => {}.
    از نشت کلاینت جلوگیری می‌کند.
    """
    retries = 0
    headers = kwargs.pop("headers", None) or _get_api_headers(server)

    while retries <= MAX_RETRIES:
        try:
            async with await _make_client(timeout=kwargs.get("timeout", 20.0)) as client:
                resp: httpx.Response = await getattr(client, method.lower())(url, headers=headers, **kwargs)
                resp.raise_for_status()
                try:
                    return resp.json()
                except ValueError:
                    return {}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            text = e.response.text if e.response is not None else str(e)
            if status == 404:
                logger.info("%s %s -> 404 Not Found (returning _not_found)", method.upper(), url)
                return {"_not_found": True}
            if status in (401, 403, 422):
                logger.error("%s %s -> %s: %s", method.upper(), url, status, text)
                break
            logger.warning("%s %s -> %s: %s (retry %d/%d)", method.upper(), url, status, text, retries + 1, MAX_RETRIES)
        except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.TimeoutException) as e:
            logger.warning("%s %s network: %s (retry %d/%d)", method.upper(), url, str(e), retries + 1, MAX_RETRIES)
        except Exception as e:
            logger.error("%s %s unexpected: %s", method.upper(), url, str(e), exc_info=True)
            break
        finally:
            retries += 1
            if retries <= MAX_RETRIES:
                await asyncio.sleep(BASE_RETRY_DELAY * (2 ** (retries - 1)))
    return None


# ========================= Usage extraction helpers =========================
def _to_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def _bytes_to_gb(n: Any) -> float:
    try:
        return float(n) / (1024.0 ** 3)
    except Exception:
        return 0.0


def _extract_usage_gb(payload: Dict[str, Any]) -> Optional[float]:
    """
    تلاش برای استخراج مصرف کاربر (GB) از پاسخ API هیدیفای با در نظر گرفتن تغییرات نسخه‌ها.
    اولویت:
      1) فیلدهای *_GB
      2) upload/download (bytes یا GB)
      3) فیلدهای کلی usage/used_* (تشخیص خودکار bytes/GB)
    اگر نتوانست تشخیص دهد: None
    """
    if not isinstance(payload, dict):
        return None

    # 1) رایج‌ترین کلیدهای GB
    direct_gb_keys = [
        "current_usage_GB", "usage_GB", "total_usage_GB",
        "used_GB", "used_gb", "usageGb", "currentUsageGB"
    ]
    for k in direct_gb_keys:
        if k in payload:
            return _to_float(payload.get(k), None)

    # برخی APIها دیتا را در یک زیر-آبجکت می‌گذارند (مثل "stats" یا "usage")
    for container_key in ("stats", "usage", "data"):
        sub = payload.get(container_key)
        if isinstance(sub, dict):
            for k in direct_gb_keys:
                if k in sub:
                    return _to_float(sub.get(k), None)

    # 2) upload/download
    # تلاش برای تشخیص حتی اگر در زیر-آبجکت باشند
    def pick_from(d: Dict[str, Any]) -> Optional[float]:
        up = d.get("upload"); down = d.get("download")
        up_gb = d.get("upload_GB"); down_gb = d.get("download_GB")
        if up_gb is not None or down_gb is not None:
            return (_to_float(up_gb or 0.0) + _to_float(down_gb or 0.0))
        if up is not None and down is not None:
            # اگر مقدار بزرگ بود، bytes فرض می‌کنیم
            up_f = _to_float(up, 0.0); down_f = _to_float(down, 0.0)
            if abs(up_f) > 1024 * 1024 or abs(down_f) > 1024 * 1024:
                return _bytes_to_gb(up_f + down_f)
            # در غیر اینصورت GB فرض می‌کنیم
            return up_f + down_f
        return None

    v = pick_from(payload)
    if v is None:
        for container_key in ("stats", "usage", "data"):
            sub = payload.get(container_key)
            if isinstance(sub, dict):
                v = pick_from(sub)
                if v is not None:
                    break
    if v is not None:
        return v

    # 3) فیلدهای کلی
    generic_keys = [
        "current_usage", "usage", "used_traffic",
        "total_used_bytes", "total_bytes", "bytes", "traffic", "used_bytes"
    ]
    for k in generic_keys:
        if k in payload:
            val = _to_float(payload.get(k), 0.0)
            if abs(val) > 1024 * 1024:  # bytes
                return _bytes_to_gb(val)
            return val  # GB فرضی
    for container_key in ("stats", "usage", "data"):
        sub = payload.get(container_key)
        if isinstance(sub, dict):
            for k in generic_keys:
                if k in sub:
                    val = _to_float(sub.get(k), 0.0)
                    if abs(val) > 1024 * 1024:  # bytes
                        return _bytes_to_gb(val)
                    return val

    return None


# ========================= API wrappers =========================
async def create_hiddify_user(
    plan_days: int,
    plan_gb: float,
    user_telegram_id: str,
    custom_name: str = "",
    server_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    ساخت کاربر در هیدیفای.
    - اگر server_name مشخص نباشد، از بین نودهای فعال DB انتخاب می‌شود (سیاست انتخاب قابل تنظیم است).
    - اگر DB خالی باشد، به config برمی‌گردد.
    """
    server = _select_server(server_name)
    endpoint = _get_base_url(server) + "user/"

    random_suffix = uuid.uuid4().hex[:4]
    base_name = custom_name if custom_name else f"tg-{user_telegram_id.split(':')[-1]}"
    unique_user_name = f"{base_name}-{random_suffix}"

    payload = {
        "name": unique_user_name,
        "package_days": int(plan_days),
        "comment": user_telegram_id,
    }

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
    sub_path = server.get("sub_path") or server.get("admin_path")
    sub_domains = server.get("sub_domains") or []
    sub_domain = random.choice(sub_domains) if sub_domains else server["panel_domain"]
    return {
        "full_link": f"https://{sub_domain}/{sub_path}/{user_uuid}/",
        "uuid": user_uuid,
        "server_name": server["name"]
    }


async def get_user_info(user_uuid: str, server_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    server = _select_server(server_name)
    endpoint = f"{_get_base_url(server)}user/{user_uuid}/"
    return await _make_request("get", endpoint, server, timeout=10.0)


async def get_user_usage_gb(user_uuid: str, server_name: Optional[str] = None) -> Optional[float]:
    """
    دریافت مصرف کاربر (GB) به‌صورت دقیق و مقاوم در برابر تغییرات API:
      - ابتدا current_usage_GB/… را می‌خواند
      - سپس upload/download (bytes یا GB)
      - سپس فیلدهای کلی usage/bytes با تشخیص خودکار
    """
    info = await get_user_info(user_uuid, server_name=server_name)
    if not isinstance(info, dict) or info.get("_not_found"):
        return None
    return _extract_usage_gb(info)


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float, server_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    تمدید سرویس. اگر plan_gb <= 0 باشد، usage_limit_GB ارسال نمی‌شود تا نامحدود بماند.
    """
    server = _select_server(server_name)
    endpoint = f"{_get_base_url(server)}user/{user_uuid}/"

    payload = {"package_days": int(plan_days)}
    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0
    if usage_limit_gb > 0:
        payload["usage_limit_GB"] = usage_limit_gb

    return await _make_request("patch", endpoint, server, json=payload, timeout=30.0)


async def delete_user_from_panel(user_uuid: str, server_name: Optional[str] = None) -> bool:
    """
    حذف کاربر از پنل هیدیفای (idempotent):
      - 204/بدون بدنه => True
      - 404 => True
      - خطای شبکه => با یک GET نهایی بررسی می‌کنیم
    """
    server = _select_server(server_name)
    endpoint = f"{_get_base_url(server)}user/{user_uuid}/"
    data = await _make_request("delete", endpoint, server, timeout=15.0)

    if data == {}:
        logger.info("Successfully deleted user %s from panel.", user_uuid)
        return True

    if isinstance(data, dict) and data.get("_not_found"):
        logger.info("Successfully deleted/not-found user %s from panel.", user_uuid)
        return True

    if data is None:
        probe = await get_user_info(user_uuid, server_name=server["name"])
        if isinstance(probe, dict) and probe.get("_not_found"):
            logger.info("Delete treated as success for %s (verified _not_found after delete).", user_uuid)
            return True

    return False


async def check_api_connection(server_name: Optional[str] = None) -> bool:
    """
    بررسی اتصال به API و صحت کلید API
    """
    try:
        server = _select_server(server_name)
        endpoint = _get_base_url(server) + "user/?page=1&per_page=1"
        response = await _make_request("get", endpoint, server, timeout=5.0)
        return response is not None
    except Exception as e:
        logger.error("API connection check failed: %s", e, exc_info=True)
        return False