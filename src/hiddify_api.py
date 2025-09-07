# filename: hiddify_api.py
# -*- coding: utf-8 -*-
"""
Hiddify API client for the bot (async, HTTPX)

Key points:
- Admin API v2 (/api/v2/admin/): create/get/renew/delete user
- Expanded API (panel-side helpers): push nodes.json & hidybotconfigs.json
- Renew fix: after renewing, if usage didn't reset, fallback to Expanded API
  bulk update to force current_usage_GB=0 (works with your API).
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

# Optional multi-server configs (fallbacks if DB nodes are empty)
try:
    from config import MULTI_SERVER_ENABLED, SERVERS, DEFAULT_SERVER_NAME, SERVER_SELECTION_POLICY
except Exception:
    MULTI_SERVER_ENABLED = False
    SERVERS = []
    DEFAULT_SERVER_NAME = None
    SERVER_SELECTION_POLICY = "first"

# Expanded API push helpers
try:
    from config import PANEL_SECRET_UUID
except Exception:
    PANEL_SECRET_UUID = None

try:
    from config import HIDDIFY_API_VERIFY_SSL
except Exception:
    HIDDIFY_API_VERIFY_SSL = True

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
    # Convert DB node row to server dict
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
            # Normalize keys
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
    """Pick node with the most free capacity (capacity - current_users)."""
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
    Selection logic:
    1) If server_name is given: try DB nodes, then config.SERVERS
    2) If DB has active nodes: apply SERVER_SELECTION_POLICY
       - least_loaded/by_name/first
    3) Else: use SERVERS (when MULTI_SERVER_ENABLED) or fallback single server
    """
    if server_name:
        srv = _db_get_server_by_name(server_name)
        if srv:
            return srv
        srv = _get_server_by_name_config(server_name)
        if srv:
            return srv

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
        return db_servers[0]

    if MULTI_SERVER_ENABLED and SERVERS:
        policy = str(SERVER_SELECTION_POLICY or "first").lower()
        if policy == "by_name" and DEFAULT_SERVER_NAME:
            srv = _get_server_by_name_config(DEFAULT_SERVER_NAME)
            if srv:
                return srv
        return _get_server_by_name_config(SERVERS[0].get("name")) or _fallback_server_dict()

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
    HTTP with retries. 404 -> {"_not_found": True}. Empty body -> {}.
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
            logger.warning("%s %s -> %s: %s (retry %d/%d)", method.upper(), url, status, text, retries + 1, MAX_RETRIES)
            if status in (401, 403, 422):
                break
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
    """Try to extract current usage (GB) from various API shapes."""
    if not isinstance(payload, dict):
        return None

    direct_gb_keys = [
        "current_usage_GB", "usage_GB", "total_usage_GB",
        "used_GB", "used_gb", "usageGb", "currentUsageGB"
    ]
    for k in direct_gb_keys:
        if k in payload:
            try:
                return _to_float(payload.get(k), None)
            except Exception:
                pass

    for container_key in ("stats", "usage", "data"):
        sub = payload.get(container_key)
        if isinstance(sub, dict):
            for k in direct_gb_keys:
                if k in sub:
                    try:
                        return _to_float(sub.get(k), None)
                    except Exception:
                        pass

    def pick_from(d: Dict[str, Any]) -> Optional[float]:
        up = d.get("upload"); down = d.get("download")
        up_gb = d.get("upload_GB"); down_gb = d.get("download_GB")
        if up_gb is not None or down_gb is not None:
            return (_to_float(up_gb or 0.0) + _to_float(down_gb or 0.0))
        if up is not None and down is not None:
            up_f = _to_float(up, 0.0); down_f = _to_float(down, 0.0)
            if abs(up_f) > 1024 * 1024 or abs(down_f) > 1024 * 1024:
                return _bytes_to_gb(up_f + down_f)
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

    generic_keys = [
        "current_usage", "usage", "used_traffic",
        "total_used_bytes", "total_bytes", "bytes", "traffic", "used_bytes"
    ]
    for k in generic_keys:
        if k in payload:
            val = _to_float(payload.get(k), 0.0)
            if abs(val) > 1024 * 1024:
                return _bytes_to_gb(val)
            return val
    for container_key in ("stats", "usage", "data"):
        sub = payload.get(container_key)
        if isinstance(sub, dict):
            for k in generic_keys:
                if k in sub:
                    val = _to_float(sub.get(k), 0.0)
                    if abs(val) > 1024 * 1024:
                        return _bytes_to_gb(val)
                    return val
    return None


# ========================= Admin API v2 wrappers =========================
async def create_hiddify_user(
    plan_days: int,
    plan_gb: float,
    user_telegram_id: str,
    custom_name: str = "",
    server_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Create user on target panel."""
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
    sub_path = server.get("sub_path") or SUB_PATH or "sub"
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
    """Get current usage in GB."""
    info = await get_user_info(user_uuid, server_name=server_name)
    if not isinstance(info, dict) or info.get("_not_found"):
        return None
    return _extract_usage_gb(info)


async def _expanded_bulk_zero_usage(user_uuid: str, server: Dict[str, Any]) -> bool:
    """
    Fallback via Expanded API:
    POST /<sub or proxy>/<SECRET>/api/v1/bulkusers/?update=1
    Body: [{"uuid": ..., "current_usage_GB": 0, "start_date": now}]
    """
    bases = _panel_api_base_for_push()
    if not bases:
        return False
    body = [{
        "uuid": user_uuid,
        "current_usage_GB": 0,
        "start_date": datetime.now(timezone.utc).isoformat()
    }]
    for base in bases:
        url = f"{base}/bulkusers/?update=1"
        try:
            status, data = await _post_json_noauth(url, body, timeout=15.0)
            if status == 200:
                return True
        except Exception:
            continue
    return False


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float, server_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Renew subscription and reset quota:
    - PATCH user with package_days and start_date=now (reset period)
    - Send reset flags (if supported by API)
    - If usage didn't reset, use Expanded API bulk update to force current_usage_GB=0
    """
    server = _select_server(server_name)
    endpoint = f"{_get_base_url(server)}user/{user_uuid}/"

    payload: Dict[str, Any] = {
        "package_days": int(plan_days),
        "start_date": datetime.now(timezone.utc).isoformat(),
        "reset_traffic": True,
        "reset_usage": True,
    }
    try:
        usage_limit_gb = float(plan_gb)
    except Exception:
        usage_limit_gb = 0.0
    if usage_limit_gb > 0:
        payload["usage_limit_GB"] = usage_limit_gb

    _ = await _make_request("patch", endpoint, server, json=payload, timeout=30.0)

    info = await get_user_info(user_uuid, server_name=server["name"])
    if not isinstance(info, dict) or info.get("_not_found"):
        return None

    used = _extract_usage_gb(info)
    if used is not None and used > 0.01:
        # Admin API didn't reset; use Expanded API to force 0 GB
        ok = await _expanded_bulk_zero_usage(user_uuid, server)
        if ok:
            info = await get_user_info(user_uuid, server_name=server["name"])

    return info


async def delete_user_from_panel(user_uuid: str, server_name: Optional[str] = None) -> bool:
    """Delete user (idempotent)."""
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
            logger.info("Delete treated as success for %s (verified _not_found).", user_uuid)
            return True

    return False


async def check_api_connection(server_name: Optional[str] = None) -> bool:
    """Quick sanity check."""
    try:
        server = _select_server(server_name)
        endpoint = _get_base_url(server) + "user/?page=1&per_page=1"
        response = await _make_request("get", endpoint, server, timeout=5.0)
        return response is not None
    except Exception as e:
        logger.error("API connection check failed: %s", e, exc_info=True)
        return False


# ========================= Expanded API (push nodes/configs) =========================
def _panel_api_base_for_push() -> List[str]:
    """Candidate bases to push nodes/configs to Expanded API."""
    domain = PANEL_DOMAIN
    cpath = (SUB_PATH or "sub").strip().strip("/")

    bases: List[str] = []
    if PANEL_SECRET_UUID:
        bases.append(f"https://{domain}/{cpath}/{PANEL_SECRET_UUID}/api/v1")
    bases.append(f"https://{domain}/{cpath}/api/v1")

    if PANEL_SECRET_UUID:
        bases.append(f"https://{domain}/{ADMIN_PATH}/{PANEL_SECRET_UUID}/api/v1")
    bases.append(f"https://{domain}/{ADMIN_PATH}/api/v1")

    # Dedup while preserving order
    seen = set()
    uniq = []
    for b in bases:
        b = b.rstrip("/")
        if b not in seen:
            uniq.append(b)
            seen.add(b)
    return uniq


async def _post_json_noauth(url: str, body: Any, timeout: float = 20.0) -> Tuple[int, Any]:
    """Simple POST without special headers (for Expanded API)."""
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=HIDDIFY_API_VERIFY_SSL) as client:
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


async def push_nodes_to_panel(base_urls: List[str]) -> bool:
    """Update nodes.json on main panel."""
    cleaned: List[str] = []
    seen = set()
    for u in base_urls or []:
        u = (u or "").strip().rstrip("/")
        if u and u not in seen:
            cleaned.append(u)
            seen.add(u)

    if not cleaned:
        logger.info("push_nodes_to_panel: empty list, skipping push.")
        return True

    for base in _panel_api_base_for_push():
        status, data = await _post_json_noauth(f"{base}/sub/", cleaned)
        if status == 200 and isinstance(data, dict) and int(data.get("status", 0)) == 200:
            return True
    logger.warning("push_nodes_to_panel failed on all bases.")
    return False


async def push_hidybot_configs(cfg: Dict[str, Any]) -> bool:
    """Update hidybotconfigs.json on main panel."""
    body = cfg or {}
    for base in _panel_api_base_for_push():
        status, data = await _post_json_noauth(f"{base}/configs/", body)
        if status == 200 and isinstance(data, dict) and int(data.get("status", 0)) == 200:
            return True
    logger.warning("push_hidybot_configs failed on all bases.")
    return False