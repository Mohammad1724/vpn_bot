# filename: bot/panels.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Dict, Optional
from urllib.parse import urlparse

# اگر در آینده بخواهید از DB بخوانید، این ایمپورت حاضر است؛ فعلاً فقط از config می‌خوانیم.
import database as db  # noqa: F401

try:
    import config as _cfg
except Exception:
    class _Cfg: ...
    _cfg = _Cfg()


def _host(s: str) -> str:
    """
    نرمال‌سازی ورودی به صورت hostname خالی از scheme و اسلش.
    مثال: https://sub.example.com/path -> sub.example.com
    """
    s = (s or "").strip()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s
    p = urlparse(s)
    return (p.netloc or "").lower().strip()


def _norm_subdomains(sd) -> List[str]:
    """
    ورودی ممکن است رشته CSV یا لیست باشد. خروجی: لیست hostname‌های معتبر.
    """
    vals: List[str] = []
    if isinstance(sd, str):
        parts = [p.strip() for p in sd.split(",") if p.strip()]
    else:
        parts = [str(x).strip() for x in (sd or []) if str(x).strip()]
    for p in parts:
        h = _host(p)
        if h:
            vals.append(h)
    return vals


def _load_from_config() -> List[Dict]:
    """
    بارگذاری پنل‌ها از config.PANELS.
    اگر تعریف نشده باشد، به تنظیمات تک‌پنلی قدیمی fallback می‌کنیم.
    """
    panels = getattr(_cfg, "PANELS", None)
    if not panels or not isinstance(panels, list):
        # fallback به کانفیگ تک‌پنلی قدیمی
        base = {
            "id": "default",
            "name": "Default",
            "panel_domain": getattr(_cfg, "PANEL_DOMAIN", "") or "",
            "admin_path": getattr(_cfg, "ADMIN_PATH", "") or "",
            "api_key": getattr(_cfg, "API_KEY", "") or "",
            "sub_domains": _norm_subdomains(getattr(_cfg, "SUB_DOMAINS", []) or []),
            "sub_path": getattr(_cfg, "SUB_PATH", "sub") or "sub",
            "panel_secret_uuid": getattr(_cfg, "PANEL_SECRET_UUID", "") or "",
            "verify_ssl": bool(getattr(_cfg, "HIDDIFY_API_VERIFY_SSL", True)),
        }
        return [base]

    # Normalize لیست چندپنلی
    res: List[Dict] = []
    for p in panels:
        res.append({
            "id": str(p.get("id") or ""),
            "name": str(p.get("name") or ""),
            "panel_domain": str(p.get("panel_domain") or ""),
            "admin_path": str(p.get("admin_path") or ""),
            "api_key": str(p.get("api_key") or ""),
            "sub_domains": _norm_subdomains(p.get("sub_domains")),
            "sub_path": str(p.get("sub_path") or "sub"),
            "panel_secret_uuid": str(p.get("panel_secret_uuid") or ""),
            "verify_ssl": bool(p.get("verify_ssl", True)),
        })
    return res


def load_panels() -> List[Dict]:
    """
    فعلاً از config.PANELS می‌خوانیم.
    اگر خواستید مدیریت از داخل ربات باشد، می‌توان از settings (مثلاً panels_json) هم خواند.
    """
    # نمونه پیاده‌سازی خواندن از DB در آینده:
    # raw = db.get_setting("panels_json")
    # if raw:
    #     try:
    #         data = json.loads(raw)
    #         ... (normalize مشابه _load_from_config)
    #         return normalized_list
    #     except Exception:
    #         pass
    return _load_from_config()


def find_panel_by_id(pid: str) -> Optional[Dict]:
    """
    جستجو بر اساس شناسه‌ی تعریف‌شده در config (کلید 'id').
    """
    pid = str(pid or "").strip()
    for p in load_panels():
        if str(p.get("id")) == pid:
            return p
    return None


def find_panel_for_link(link: str) -> Optional[Dict]:
    """
    پنل را از روی host لینک (مانند sub_link ذخیره‌شده در DB) پیدا می‌کند.
    اگر host لینک با panel_domain یا هر یک از sub_domains پنل برابر باشد، همان پنل برگردانده می‌شود.
    """
    lh = _host(link)
    if not lh:
        return None
    for p in load_panels():
        if _host(p.get("panel_domain")) == lh:
            return p
        for sd in p.get("sub_domains") or []:
            if sd == lh:
                return p
    return None