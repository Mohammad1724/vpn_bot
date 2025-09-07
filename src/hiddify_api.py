# filename: hiddify_api.py
# -*- coding: utf-8 -*-
"""
Hiddify API client for the bot (async, HTTPX)

- Admin API v2 (/api/v2/admin/): create/get/delete user
- Expanded API v1 (/<sub_path>/<SECRET>/api/v1): renew user, push nodes/configs
- Renew Fix: Renewal is done exclusively via the Expanded API on the target node
  to ensure both date and usage are properly reset, bypassing Admin API v2 bugs.
"""

import asyncio
import httpx
import uuid
import random
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

import database as db
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH

# Optional multi-server configs
try:
    from config import MULTI_SERVER_ENABLED, SERVERS, DEFAULT_SERVER_NAME, SERVER_SELECTION_POLICY
except Exception:
    MULTI_SERVER_ENABLED = False
    SERVERS = []
    DEFAULT_SERVER_NAME = None
    SERVER_SELECTION_POLICY = "first"

# Expanded API access
try:
    from config import PANEL_SECRET_UUID
except Exception:
    PANEL_SECRET_UUID = None

try:
    from config import HIDDIFY_API_VERIFY_SSL
except Exception:
    HIDDIFY_API_VERIFY_SSL = True

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0


# ========================= Server selection =========================
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
        return [_db_server_from_node(n) for n in nodes if str(n.get("panel_type", "hiddify")).lower() == "hiddify"]
    except Exception:
        return []

def _db_get_server_by_name(name: str) -> Optional[Dict[str, Any]]:
    try:
        n = db.get_node_by_name(name)
        return _db_server_from_node(n) if n and str(n.get("panel_type", "hiddify")).lower() == "hiddify" else None
    except Exception:
        return None

def _pick_least_loaded(servers: List[Dict[str, Any]]) -> Dict[str, Any]:
    best, best_free = None, -1
    for s in servers:
        cap = int(s.get("capacity") or 0)
        curr = int(s.get("current_users") or 0)
        try:
            live = db.count_services_on_node(s["name"])
            curr = max(curr, live)
        except Exception: pass
        free = cap - curr if cap > 0 else 0
        if free > best_free:
            best, best_free = s, free
    return best or (servers[0] if servers else _fallback_server_dict())

def _select_server(server_name: Optional[str] = None) -> Dict[str, Any]:
    if server_name:
        srv = _db_get_server_by_name(server_name) or _get_server_by_name_config(server_name)
        if srv: return srv
    db_servers = _db_list_active_hiddify_servers()
    if db_servers:
        policy = str(SERVER_SELECTION_POLICY or "first").lower()
        if policy in ("least_loaded", "capacity", "free"):
            return _pick_least_loaded(db_servers)
        if policy == "by_name" and DEFAULT_SERVER_NAME:
            named = _db_get_server_by_name(DEFAULT_SERVER_NAME)
            if named and int(named.get("is_active", 1)) == 1:
                return named
        return db_servers[0]
    if MULTI_SERVER_ENABLED and SERVERS:
        policy = str(SERVER_SELECTION_POLICY or "first").lower()
        if policy == "by_name" and DEFAULT_SERVER_NAME:
            srv = _get_server_by_name_config(DEFAULT_SERVER_NAME)
            if srv: return srv
        return _get_server_by_name_config(SERVERS[0].get("name")) or _fallback_server_dict()
    return _fallback_server_dict()


# ========================= HTTP helpers =========================
def _get_base_url(server: Dict[str, Any]) -> str:
    return f"https://{server['panel_domain']}/{server['admin_path']}/api/v2/admin/"

def _get_api_headers(server: Dict[str, Any]) -> dict:
    return {"Hiddify-API-Key": server["api_key"], "Content-Type": "application/json", "Accept": "application/json"}

async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=HIDDIFY_API_VERIFY_SSL)

async def _make_request(method: str, url: str, server: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
    retries = 0
    headers = kwargs.pop("headers", None) or _get_api_headers(server)
    while retries <= MAX_RETRIES:
        try:
            async with await _make_client(timeout=kwargs.get("timeout", 20.0)) as client:
                resp: httpx.Response = await getattr(client, method.lower())(url, headers=headers, **kwargs)
                resp.raise_for_status()
                try: return resp.json()
                except ValueError: return {}
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            text = e.response.text if e.response is not None else str(e)
            logger.warning("%s %s -> %s: %s (retry %d/%d)", method.upper(), url, status, text, retries+1, MAX_RETRIES)
            if status == 404: return {"_not_found": True}
            if status in (401, 403, 422): break
        except Exception as e:
            logger.error("%s %s unexpected: %s", method.upper(), url, str(e), exc_info=True)
            break
        finally:
            retries += 1
            if retries <= MAX_RETRIES:
                await asyncio.sleep(BASE_RETRY_DELAY * (2 ** (retries - 1)))
    return None


# ========================= Usage extraction =========================
def _extract_usage_gb(payload: Dict[str, Any]) -> Optional[float]:
    if not isinstance(payload, dict):
        return None
    for k in ("current_usage_GB", "usage_GB", "used_GB"):
        if k in payload:
            return float(payload[k])
    return None


# ========================= Expanded API helpers =========================
def _expanded_api_bases_for_server(server: Dict[str, Any]) -> List[str]:
    domain = server.get("panel_domain") or PANEL_DOMAIN
    cpath = (server.get("sub_path") or SUB_PATH or "sub").strip().strip("/")
    bases: List[str] = []
    if PANEL_SECRET_UUID:
        bases.append(f"https://{domain}/{cpath}/{PANEL_SECRET_UUID}/api/v1")
    return bases

async def _post_json_noauth(url: str, body: Any, timeout: float = 20.0) -> Tuple[int, Any]:
    try:
        async with await _make_client(timeout) as client:
            resp = await client.post(url, json=body)
            data = None
            try: data = resp.json()
            except Exception: data = None
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
            try: data = resp.json()
            except Exception: data = None
            if resp.status_code >= 400:
                logger.warning("GET %s -> %s: %s", url, resp.status_code, data)
            return resp.status_code, data
    except Exception as e:
        logger.debug("GET %s failed: %s", url, e)
        return 0, None

async def _expanded_user_update_on_server(user_uuid: str, plan_days: int, plan_gb: float, server: Dict[str, Any]) -> bool:
    bases = _expanded_api_bases_for_server(server)
    if not bases:
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
        if status == 200:
            return True
    return False

async def _expanded_update_usage_on_server(server: Dict[str, Any]) -> bool:
    bases = _expanded_api_bases_for_server(server)
    for base in bases:
        status, _ = await _get_noauth(f"{base}/update_usage/", timeout=45.0)
        if status == 200:
            return True
    return False


# ========================= Admin API v2 wrappers =========================
async def create_hiddify_user(plan_days: int, plan_gb: float, user_telegram_id: str, custom_name: str = "", server_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    server = _select_server(server_name)
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
    return {"full_link": f"https://{sub_domain}/{sub_path}/{user_uuid}/", "uuid": user_uuid, "server_name": server["name"]}

async def get_user_info(user_uuid: str, server_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    server = _select_server(server_name)
    endpoint = f"{_get_base_url(server)}user/{user_uuid}/"
    return await _make_request("get", endpoint, server, timeout=10.0)

async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float, server_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    server = _select_server(server_name)
    # 1. Expanded API POST /user/ on target node to update and reset
    exp_ok = await _expanded_user_update_on_server(user_uuid, plan_days, plan_gb, server)
    if not exp_ok:
        logger.warning("Expanded user update failed for %s on %s", user_uuid, server.get("panel_domain"))

    # 2. Force usage recompute on target node so Admin API reflects changes
    await _expanded_update_usage_on_server(server)
    await asyncio.sleep(1.0)

    # 3. Poll info (up to 3 tries) to verify
    for _ in range(3):
        info = await get_user_info(user_uuid, server_name=server["name"])
        if isinstance(info, dict) and not info.get("_not_found"):
            used = _extract_usage_gb(info) or 0.0
            if used <= 0.01:
                return info
        await asyncio.sleep(0.8)

    # Return latest state, even if >0
    return await get_user_info(user_uuid, server_name=server["name"])

async def delete_user_from_panel(user_uuid: str, server_name: Optional[str] = None) -> bool:
    server = _select_server(server_name)
    data = await _make_request("delete", f"{_get_base_url(server)}user/{user_uuid}/", server, timeout=15.0)
    if data == {}: return True
    if isinstance(data, dict) and data.get("_not_found"): return True
    if data is None:
        probe = await get_user_info(user_uuid, server_name=server["name"])
        if isinstance(probe, dict) and probe.get("_not_found"): return True
    return False

async def check_api_connection(server_name: Optional[str] = None) -> bool:
    try:
        server = _select_server(server_name)
        r = await _make_request("get", _get_base_url(server) + "user/?page=1&per_page=1", server, timeout=5.0)
        return r is not None
    except Exception:
        return False