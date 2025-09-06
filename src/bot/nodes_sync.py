# filename: bot/nodes_sync.py
# -*- coding: utf-8 -*-
import logging
import database as db
from config import SUB_PATH
import hiddify_api

logger = logging.getLogger(__name__)

def _domain_for_node(node: dict) -> str:
    subs = node.get("sub_domains") or []
    domain = (subs[0] if subs else node.get("panel_domain") or "").strip()
    return domain

def _node_base_url_for_panel(node: dict) -> str:
    """
    خروجی باید شبیه https://NODE/<client_proxy_path> باشد (بدون UUID).
    در این ساختار، client_proxy_path همان sub_path نود است؛ اگر نبود از SUB_PATH عمومی استفاده می‌کنیم.
    """
    domain = _domain_for_node(node)
    path = (node.get("sub_path") or SUB_PATH or "sub").strip().strip("/")
    return f"https://{domain}/{path}".rstrip("/")

async def sync_nodes_into_panel():
    """
    لیست نودهای فعال را از DB می‌خواند و به nodes.json پنل پوش می‌کند.
    """
    try:
        nodes = db.list_nodes()  # از database.py
        active = [n for n in (nodes or []) if int(n.get("is_active", 1)) == 1]

        bases: list[str] = []
        for n in active:
            try:
                base = _node_base_url_for_panel(n)
                if base and base not in bases:
                    bases.append(base)
            except Exception:
                logger.exception("failed to build base URL for node: %s", n)

        ok = await hiddify_api.push_nodes_to_panel(bases)
        logger.info("push_nodes_to_panel -> %s | success=%s", bases, ok)
    except Exception as e:
        logger.error("sync_nodes_into_panel error: %s", e, exc_info=True)