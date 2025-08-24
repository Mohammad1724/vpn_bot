# -*- coding: utf-8 -*-
"""
Nodes API client for mirroring users to Hiddify nodes (Expanded API) and
pushing subscription aggregation data.

Expected API base per node:
  https://<HOST>/<ADMIN_PATH>/<ADMIN_UUID>/api/v1

Available endpoints (based on your Expanded API blueprints):
  - POST   /user/           {uuid, package_days, usage_limit_GB, ...}
  - DELETE /user/?uuid=...
  - POST   /bulkusers/?update=1     [ {uuid,...}, ... ]
  - GET    /status/
  - GET    /update_usage/
  - POST   /sub/            [ "https://node-a/SUB_SECRET", ... ]  (aggregator only)
  - POST   /configs/        { ... } (optional hidybotconfigs.json for aggregator)

This module is async and uses httpx. Integrate with handlers by awaiting functions.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Sequence, Dict, Any, List

import httpx

import database as db

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
BULK_TIMEOUT = 60.0
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 0.6
CONCURRENCY_LIMIT = 20  # limit simultaneous requests when fanning out to many nodes


def _mk_headers(api_key: Optional[str]) -> dict:
    """
    If your login_required supports API-Key header, set it here.
    Otherwise it will be ignored by server and URL-based ADMIN_UUID auth is used.
    """
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Hiddify-API-Key"] = api_key
    return headers


def _normalize_base(api_base: str) -> str:
    """
    Ensure api_base has no trailing slash.
    Example in DB: https://node-a.example.com/ADMIN_PATH/ADMIN_UUID/api/v1
    """
    return (api_base or "").rstrip("/")


async def _req_json(
    method: str,
    url: str,
    headers: dict,
    *,
    json: dict | list | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
) -> Optional[Dict[str, Any]]:
    attempt = 0
    last_exc = None
    while attempt <= retries:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method.upper(), url, headers=headers, json=json)
                resp.raise_for_status()
                try:
                    return resp.json()
                except Exception:
                    return {}
        except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt == retries:
                logger.warning("HTTP %s %s failed after retries: %s", method.upper(), url, e)
                break
            backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
            await asyncio.sleep(backoff)
        except httpx.HTTPStatusError as e:
            # If unauthorized / forbidden etc., don't retry
            status = e.response.status_code if e.response is not None else None
            text = e.response.text if e.response is not None else str(e)
            logger.warning("HTTP %s %s -> %s: %s", method.upper(), url, status, text)
            if status and status < 500:
                return None
            # retry on 5xx
            if attempt == retries:
                break
            await asyncio.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
        except Exception as e:
            last_exc = e
            logger.error("HTTP %s %s unexpected error: %s", method.upper(), url, e, exc_info=True)
            return None
        finally:
            attempt += 1
    if last_exc:
        logger.debug("Last exception for %s %s: %s", method.upper(), url, last_exc)
    return None


# -------- Node operations (single node) --------

async def test_node(node: dict) -> bool:
    """
    GET /status/ on a node. Returns True if status==200.
    """
    base = _normalize_base(node.get("api_base", ""))
    if not base:
        return False
    url = f"{base}/status/"
    headers = _mk_headers(node.get("api_key"))
    try:
        data = await _req_json("GET", url, headers, timeout=DEFAULT_TIMEOUT)
        return bool(data and data.get("status") == 200)
    except Exception as e:
        logger.warning("test_node %s failed: %s", node.get("name"), e)
        return False


async def upsert_user_on_node(node: dict, user_payload: dict) -> bool:
    """
    POST /user/ to create or update a user with same UUID on node.
    payload keys minimal: uuid, package_days, usage_limit_GB
    """
    base = _normalize_base(node.get("api_base", ""))
    if not base:
        return False
    url = f"{base}/user/"
    headers = _mk_headers(node.get("api_key"))
    try:
        data = await _req_json("POST", url, headers, json=user_payload, timeout=DEFAULT_TIMEOUT)
        ok = bool(data and data.get("status") == 200)
        if not ok:
            logger.warning("upsert_user_on_node %s returned %s", node.get("name"), data)
        return ok
    except Exception as e:
        logger.error("upsert_user_on_node %s failed: %s", node.get("name"), e, exc_info=True)
        return False


async def delete_user_on_node(node: dict, uuid: str) -> bool:
    """
    DELETE /user/?uuid=<UUID>
    """
    base = _normalize_base(node.get("api_base", ""))
    if not base:
        return False
    url = f"{base}/user/"
    headers = _mk_headers(node.get("api_key"))
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.delete(url, headers=headers, params={"uuid": uuid})
            if resp.status_code == 200:
                return True
            logger.warning("delete_user_on_node %s -> %s %s", node.get("name"), resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("delete_user_on_node %s failed: %s", node.get("name"), e, exc_info=True)
        return False


async def get_user_on_node(node: dict, uuid: str) -> Optional[Dict[str, Any]]:
    """
    GET /user/?uuid=<UUID>  (if supported by Expanded API)
    Returns user dict or None.
    """
    base = _normalize_base(node.get("api_base", ""))
    if not base:
        return None
    url = f"{base}/user/"
    headers = _mk_headers(node.get("api_key"))
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=headers, params={"uuid": uuid})
            if resp.status_code == 200:
                return resp.json()
            return None
    except Exception as e:
        logger.warning("get_user_on_node %s failed: %s", node.get("name"), e)
        return None


async def trigger_update_usage(node: dict) -> bool:
    """
    GET /update_usage/ to trigger usage update routine on node (optional).
    """
    base = _normalize_base(node.get("api_base", ""))
    if not base:
        return False
    url = f"{base}/update_usage/"
    headers = _mk_headers(node.get("api_key"))
    try:
        data = await _req_json("GET", url, headers, timeout=BULK_TIMEOUT)
        return bool(data and data.get("status") == 200)
    except Exception as e:
        logger.warning("trigger_update_usage %s failed: %s", node.get("name"), e)
        return False


# -------- Fan-out helpers (many nodes) --------

async def _gather_limited(coros: List, limit: int = CONCURRENCY_LIMIT):
    sem = asyncio.Semaphore(limit)
    async def _wrap(c):
        async with sem:
            return await c
    return await asyncio.gather(*[_wrap(c) for c in coros], return_exceptions=False)


async def bulk_upsert_users(nodes: Sequence[dict], users_payload: list[dict]) -> dict:
    """
    POST /bulkusers/?update=1 on all enabled nodes.
    Returns dict {node_name: bool}
    """
    results: Dict[str, bool] = {}

    async def _one(node: dict):
        if not node.get("enabled"):
            results[node.get("name")] = False
            return
        base = _normalize_base(node.get("api_base", ""))
        url = f"{base}/bulkusers/"
        headers = _mk_headers(node.get("api_key"))
        try:
            async with httpx.AsyncClient(timeout=BULK_TIMEOUT) as client:
                resp = await client.post(url, headers=headers, params={"update": "1"}, json=users_payload)
                ok = resp.status_code == 200
                results[node.get("name")] = ok
                if not ok:
                    logger.warning("bulk_upsert on %s -> %s %s", node.get("name"), resp.status_code, resp.text)
        except Exception as e:
            logger.error("bulk_upsert on %s failed: %s", node.get("name"), e, exc_info=True)
            results[node.get("name")] = False

    await _gather_limited([_one(n) for n in nodes])
    return results


async def replicate_user_to_nodes(user_uuid: str, package_days: int, usage_limit_gb: float) -> dict:
    """
    Create/update the same user on all enabled nodes with same UUID.
    Returns dict {node_name: bool}
    """
    nodes = db.list_nodes(only_enabled=True)
    if not nodes:
        return {}
    payload = {
        "uuid": user_uuid,
        "package_days": int(package_days),
        "usage_limit_GB": float(usage_limit_gb)
    }
    results: Dict[str, bool] = {}
    async def _one(node: dict):
        ok = await upsert_user_on_node(node, payload)
        results[node.get("name")] = ok

    await _gather_limited([_one(n) for n in nodes])
    return results


async def remove_user_from_nodes(user_uuid: str) -> dict:
    """
    Delete the same user UUID from all enabled nodes.
    Returns dict {node_name: bool}
    """
    nodes = db.list_nodes(only_enabled=True)
    if not nodes:
        return {}
    results: Dict[str, bool] = {}
    async def _one(node: dict):
        ok = await delete_user_on_node(node, user_uuid)
        results[node.get("name")] = ok

    await _gather_limited([_one(n) for n in nodes])
    return results


# -------- Aggregator helpers --------

async def push_nodes_to_aggregator(aggregator_api_base: str, api_key: Optional[str], sub_prefixes: list[str]) -> bool:
    """
    Push nodes' SUB prefixes to aggregator (master) API to write nodes.json.
    POST /sub/ with JSON array of SUB_PREFIXes.
    """
    base = _normalize_base(aggregator_api_base)
    url = f"{base}/sub/"
    headers = _mk_headers(api_key)
    try:
        data = await _req_json("POST", url, headers, json=sub_prefixes, timeout=DEFAULT_TIMEOUT)
        ok = bool(data and data.get("status") == 200)
        if not ok:
            logger.warning("push_nodes_to_aggregator -> %s", data)
        return ok
    except Exception as e:
        logger.error("push_nodes_to_aggregator failed: %s", e, exc_info=True)
        return False


async def push_hidybot_configs_to_aggregator(aggregator_api_base: str, api_key: Optional[str], cfg: dict) -> bool:
    """
    Optional: push hidybotconfigs.json to aggregator.
    POST /configs/ with JSON object.
    """
    base = _normalize_base(aggregator_api_base)
    url = f"{base}/configs/"
    headers = _mk_headers(api_key)
    try:
        data = await _req_json("POST", url, headers, json=cfg, timeout=DEFAULT_TIMEOUT)
        ok = bool(data and data.get("status") == 200)
        if not ok:
            logger.warning("push_hidybot_configs_to_aggregator -> %s", data)
        return ok
    except Exception as e:
        logger.error("push_hidybot_configs_to_aggregator failed: %s", e, exc_info=True)
        return False


# -------- Approx usage aggregation helpers (optional; for future enforcer job) --------

async def get_combined_usage_gb(user_uuid: str) -> float:
    """
    (Optional) Read current_usage_GB from all enabled nodes for this UUID and return sum.
    Requires Expanded API to support GET /user/?uuid=... returning current_usage_GB.
    """
    nodes = db.list_nodes(only_enabled=True)
    if not nodes:
        return 0.0

    usages: List[float] = []

    async def _one(node: dict):
        data = await get_user_on_node(node, user_uuid)
        try:
            if data and "current_usage_GB" in data:
                usages.append(float(data["current_usage_GB"]))
        except Exception:
            pass

    await _gather_limited([_one(n) for n in nodes])
    return float(sum(usages))