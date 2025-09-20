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
DEFAULT_ASN = getattr(_cfg, "DEFAULT_ASN", "MCI")

# Unlimited strategy
HIDDIFY_UNLIMITED_STRATEGY = getattr(_cfg, "HIDDIFY_UNLIMITED_STRATEGY", "large_quota")  # "large_quota" | "auto"
HIDDIFY_UNLIMITED_LARGE_GB = float(getattr(_cfg, "HIDDIFY_UNLIMITED_LARGE_GB", 1000.0))
HIDDIFY_UNLIMITED_VALUE = getattr(_cfg, "HIDDIFY_UNLIMITED_VALUE", None)  # -1 | 0 | "null" | "omit" | None

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0
VERIFICATION_RETRIES = 5
VERIFICATION_DELAY = 1.0


def _normalize_host(host: str) -> str:
    h = (host or "").strip()
    if not h:
        return ""
    if not (h.startswith("http://") or h.startswith("https://")):
        h = "https://" + h
    return h.rstrip("/")


def _strip_scheme(host: str) -> str:
    h = (host or "").strip()
    if h.startswith("https://"):
        h = h[len("https://"):]
    elif h.startswith("http://"):
        h = h[len("http://"):]
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
        alt = _normalize_host(SUB_DOMAINS[0] if SUB_DOMAINS else "")
        if alt:
            logger.warning("PANEL_DOMAIN is empty; falling back to %s for API base URL", alt)
            base = alt
        else:
            logger.error("PANEL_DOMAIN and SUB_DOMAINS are empty. Please set PANEL_DOMAIN in config.py.")
            base = "https://localhost"

    clean_admin = str(ADMIN_PATH or "").strip().strip("/")
    if clean_admin:
        return f"{base}/{clean_admin}/api/v2/admin/"
    return f"{base}/api/v2/admin/"


def _get_api_headers() -> dict:
    return {
        "Hiddify-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _make_client(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=HIDDIFY_API_VERIFY_SSL, follow_redirects=True)


def _normalize_unlimited_value(val):
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("omit", "skip", "remove"):
            return "OMIT"
        if s in ("null", "none"):
            return None
        try:
            return float(val)
        except Exception:
            return 0.0
    try:
        return float(val)
    except Exception:
        return 0.0


def _is_unlimited_value(x) -> bool:
    if x is None:
        return True
    try:
        return float(x) <= 0.0
    except Exception:
        return False


def _now_ts() -> int:
    return int(time.time())


async def _make_request(method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
    headers = kwargs.pop("headers", _get_api_headers())
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
            if status == 500 and "404 Not Found" in text:
                logger.warning("Treating 500 with embedded 404 as a 404 for URL %s", url)
                return {"_not_found": True}
            if status == 404:
                return {"_not_found": True}
            if status in (401, 403, 422):
                logger.error("%s to %s failed with %s: %s", method.upper(), url, status, text)
                # Don't break the loop instantly; caller may retry with another payload
                return None
            logger.warning("%s to %s failed with %s: %s (retry %d/%d)", method.upper(), url, status, text, attempt, MAX_RETRIES)
        except Exception as e:
            logger.error("%s to %s failed: %s", method.upper(), url, e, exc_info=True)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(delay)
            delay *= 2
    return None


async def _patch_with_start_fields(user_uuid: str, base_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Try different start-time fields accepted by panel (last_reset_time, start_date).
    """
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    now_ts = _now_ts()

    candidates = [
        {"last_reset_time": now_ts},
        {"start_date": now_ts},
    ]
    for extra in candidates:
        payload = {**base_payload, **extra}
        resp = await _make_request("patch", endpoint, json=payload)
        if resp is not None and not resp.get("_not_found"):
            return resp
    return None


async def create_hiddify_user(
    plan_days: int,
    plan_gb: float,
    user_telegram_id: str,
    custom_name: str = "",
    server_name: Optional[str] = None,
    **kwargs,
) -> Optional[Dict[str, Any]]:

    endpoint = _get_base_url() + "user/"

    random_suffix = uuid.uuid4().hex[:4]
    tg_part = (user_telegram_id or "").split(":")[-1] or "user"
    base_name = str(custom_name or server_name or f"tg-{tg_part}")
    unique_user_name = f"{base_name}-{random_suffix}"

    comment = user_telegram_id or ""
    if server_name:
        safe_srv = str(server_name)[:32]
        if "|srv:" not in comment:
            comment = f"{comment}|srv:{safe_srv}" if comment else f"srv:{safe_srv}"

    # Step 1: create user
    payload_create = {"name": unique_user_name, "comment": comment}
    data = await _make_request("post", endpoint, json=payload_create)
    if not data or not data.get("uuid"):
        logger.error("create_hiddify_user (POST): failed or UUID missing")
        return None
    user_uuid = data.get("uuid")

    # Step 2: apply plan (days, GB, reset start)
    logger.info("User %s created. Applying plan via PATCH...", user_uuid)
    update_success = await _apply_and_verify_plan(user_uuid, plan_days, plan_gb)
    if not update_success:
        logger.error("create_hiddify_user (PATCH): failed to apply plan. Deleting user.")
        await delete_user_from_panel(user_uuid)
        return None

    # Build subscription link
    sub_host = _strip_scheme(random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN)
    client_secret = str(PANEL_SECRET_UUID or "").strip().strip("/")
    if not client_secret:
        sub_path = str(SUB_PATH or "sub").strip().strip("/")
        full_link = f"https://{sub_host}/{sub_path}/{user_uuid}/"
    else:
        full_link = f"https://{sub_host}/{client_secret}/{user_uuid}/sub/"

    return {"full_link": full_link, "uuid": user_uuid, "name": unique_user_name}


async def get_user_info(user_uuid: str, server_name: Optional[str] = None, **kwargs) -> Optional[Dict[str, Any]]:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    return await _make_request("get", endpoint)


async def _apply_and_verify_plan(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    exact_days = int(plan_days)

    base_payload = {"package_days": exact_days, "current_usage_GB": 0}
    # Unlimited or volume
    if plan_gb is None or float(plan_gb) <= 0.0:
        # try unlimited strategies by usage_limit_GB <= 0
        pref = _normalize_unlimited_value(HIDDIFY_UNLIMITED_VALUE)
        candidates = []
        if pref == "OMIT":
            candidates.append("OMIT")
        elif pref is None:
            candidates.append(None)
        elif isinstance(pref, (int, float)):
            candidates.append(float(pref))
        for c in [None, 0.0, -1.0, "OMIT"]:
            if c not in candidates:
                candidates.append(c)
        for idx, cand in enumerate(candidates, 1):
            payload = dict(base_payload)
            if cand != "OMIT":
                payload["usage_limit_GB"] = cand
            logger.info("Unlimited patch try %d/%d...", idx, len(candidates))
            resp = await _patch_with_start_fields(user_uuid, payload)
            if resp is None:
                continue
            # verify by reading user and checking days set
            for attempt in range(VERIFICATION_RETRIES):
                await asyncio.sleep(VERIFICATION_DELAY)
                after_info = await get_user_info(user_uuid)
                if after_info and int(after_info.get("package_days", -1)) == exact_days:
                    return after_info
        return None
    else:
        # Volume plan
        payload = dict(base_payload)
        payload["usage_limit_GB"] = float(plan_gb)
        resp = await _patch_with_start_fields(user_uuid, payload)
        if resp is None:
            logger.error("PATCH (volume) failed for %s", user_uuid)
            return None

        for attempt in range(VERIFICATION_RETRIES):
            await asyncio.sleep(VERIFICATION_DELAY)
            after_info = await get_user_info(user_uuid)
            if after_info and int(after_info.get("package_days", -1)) == exact_days:
                return after_info

        logger.error("Verification failed for UUID %s after %d attempts.", user_uuid, VERIFICATION_RETRIES)
        return None


async def renew_user_subscription(user_uuid: str, plan_days: int, plan_gb: float) -> Optional[Dict[str, Any]]:
    return await _apply_and_verify_plan(user_uuid, plan_days, plan_gb)


async def delete_user_from_panel(user_uuid: str) -> bool:
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    data = await _make_request("delete", endpoint)
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
        endpoint = _get_base_url() + "user/?page=1&per_page=1"
        response = await _make_request("get", endpoint)
        return response is not None
    except Exception:
        return False