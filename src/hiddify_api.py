# filename: hiddify_api.py
# -*- coding: utf-8 -*-
import asyncio
import httpx
import uuid
import random
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

import database as db
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY, SUB_DOMAINS, SUB_PATH, PANEL_SECRET_UUID, HIDDIFY_API_VERIFY_SSL

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0


def _select_server() -> Dict[str, Any]:
    """همیشه تنظیمات پنل اصلی را برمی‌گرداند."""
    return {
        "name": "Main", "panel_domain": PANEL_DOMAIN, "admin_path": ADMIN_PATH,
        "sub_path": SUB_PATH, "api_key": API_KEY, "sub_domains": SUB_DOMAINS or [],
    }

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
                resp = await getattr(client, method.lower())(url, headers=headers, **kwargs)
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
            if retries <= MAX_RETRIES: await asyncio.sleep(BASE_RETRY_DELAY * (2 ** (retries - 1)))
    return None

def _extract_usage_gb(payload: Dict[str, Any]) -> Optional[float]:
    if not isinstance(payload, dict): return None
    for k in ("current_usage_GB", "usage_GB", "used_GB"):
        if k in payload: return float(payload[k])
    return None

def _expanded_api_bases_for_server(server: Dict[str, Any]) -> List[str]:
    domain = server.get("panel_domain") or PANEL_DOMAIN
    cpath = (server.get("sub_path") or SUB_PATH or "sub").strip().strip("/")
    bases: List[str] = []
    if PANEL_SECRET_UUID: bases.append(f"https://{domain}/{cpath}/{PANEL_SECRET_UUID}/api/v1")
    return bases

async def _post_json_noauth(url: str, body: Any, timeout: float = 20.0) -> Tuple[int, Any]:
    try:
        async with await _make_client(timeout) as client:
            resp = await client.post(url, json=body)
            data = None
            try: data = resp.json()
            except Exception: data = None
            if resp.status_code >= 400: logger.warning("POST %s -> %s: %s", url, resp.status_code, data)
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
            if resp.status_code >= 400: logger.warning("GET %s -> %s: %s", url, resp.status_code, data)
            return resp.status_code, data
    except Exception as e:
        logger.debug("GET %s failed: %s", url, e)
        return 0, None

async def _expanded_user_update(user_uuid: str, plan_days: int, plan_gb: float) -> bool:
    server = _select_server()
    bases = _expanded_api_bases_for_server(server)
    if not bases:
        logger.error("Expanded API base URL could not be constructed. Check PANEL_SECRET_UUID in config.")
        return False
    body = {
        "uuid": user_uuid, "package_days": int(plan_days), "usage_limit_GB": float(plan_gb or 0.0),
        "start_date": datetime.now(timezone.utc).isoformat(), "current_usage_GB": 0
    }
    for base in bases:
        status, _ = await _post_json_noauth(f"{base}/user/", body, timeout=20.0)
        if status == 200: return True
    return False

async def _expanded_update_usage() -> bool:
    server = _select_server()
    bases = _expanded_api_bases_for_server(server)
    if not bases: return False
    for base in bases:
        status, _ = await _get_noauth(f"{base}/update_usage/", timeout=45.0)
        if status == 200: return True
    return False

async def create_hiddify_user(plan_days: int, plan_gb: float, user_telegram_id: str, custom_name: str = "") -> Optional[Dict[str, Any]]:
    server = _select_server()
    endpoint = _get_base_url(server) + "user/"
    random_suffix = uuid.uuid4().hex[:4]
    base_name = custom_name if custom_name else f"tg-{user_telegram_id.split(':')[-1]}"
    unique_user_name = f"{base_name}-{random_suffix}"
    payload = {"name": unique_user_name, "package_days": int(plan_days), "comment": user_telegram_id}
    try: usage_limit_gb = float(plan_gb)
    except Exception: usage_limit_gb = 0.0
    if usage_limit_gb > 0: payload["usage_limit_GB"] = usage_limit_gb
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
    exp_ok = await _expanded_user_update(user_uuid, plan_days, plan_gb)
    if not exp_ok:
        logger.error("Expanded user update failed for %s. Check PANEL_SECRET_UUID and sub_path.", user_uuid)
    await _expanded_update_usage()
    await asyncio.sleep(1.5)
    for _ in range(3):
        info = await get_user_info(user_uuid)
        if isinstance(info, dict) and not info.get("_not_found"):
            used = _extract_usage_gb(info) or 0.0
            if used <= 0.01: return info
        await asyncio.sleep(1.0)
    return await get_user_info(user_uuid)

async def delete_user_from_panel(user_uuid: str) -> bool:
    server = _select_server()
    data = await _make_request("delete", f"{_get_base_url(server)}user/{user_uuid}/", server, timeout=15.0)
    if data == {}: return True
    if isinstance(data, dict) and data.get("_not_found"): return True
    if data is None:
        probe = await get_user_info(user_uuid)
        if isinstance(probe, dict) and probe.get("_not_found"): return True
    return False

async def check_api_connection() -> bool:
    try:
        server = _select_server()
        r = await _make_request("get", _get_base_url(server) + "user/?page=1&per_page=1", server, timeout=5.0)
        return r is not None
    except Exception: return False