# filename: bot/webapp_stats.py
# -*- coding: utf-8 -*-

import os
import hmac
import json
import hashlib
from typing import Dict, Any, Optional

from aiohttp import web
import database as db

# Configs (قابل ست‌شدن در config.py)
try:
    import config as _cfg
except Exception:
    class _C: pass
    _cfg = _C()

WEBAPP_HOST = getattr(_cfg, "WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(getattr(_cfg, "WEBAPP_PORT", 8081))
WEBAPP_BASE_URL = getattr(_cfg, "WEBAPP_BASE_URL", f"http://localhost:{WEBAPP_PORT}")
BOT_TOKEN = getattr(_cfg, "BOT_TOKEN", "")

# ---------- Telegram WebApp initData verification ----------
def _verify_init_data(init_data: str) -> bool:
    try:
        if not init_data or not BOT_TOKEN:
            return False
        # Parse query-string like string: "key1=value1&key2=value2&hash=..."
        from urllib.parse import parse_qsl
        data = dict(parse_qsl(init_data, strict_parsing=True))
        received_hash = data.pop("hash", None)
        if not received_hash:
            return False
        # Build data_check_string
        items = sorted([f"{k}={v}" for k, v in data.items()])
        data_check_string = "\n".join(items)
        # secret_key = SHA256(bot_token)
        secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
        hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac_hash == received_hash
    except Exception:
        return False

# ---------- Stats helpers ----------
def _get_stats_payload() -> Dict[str, Any]:
    # Basic stats from db.get_stats
    base = db.get_stats() or {}
    # New users last 7 days
    new_users_7d = db.get_new_users_count(7)
    # Users without any orders
    try:
        from database import get_users_with_no_orders_count
        users_no_orders = get_users_with_no_orders_count()
    except Exception:
        # fallback if not available
        try:
            users_no_orders = len(db.get_users_with_no_orders())
        except Exception:
            users_no_orders = 0
    # Total traffic used (GB)
    try:
        # snapshot of user_traffic table
        import sqlite3
        conn = db._connect_db()
        cur = conn.cursor()
        cur.execute("SELECT SUM(traffic_used) FROM user_traffic")
        total_traffic = float(cur.fetchone()[0] or 0.0)
    except Exception:
        total_traffic = 0.0
    # Active services count
    try:
        conn = db._connect_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(service_id) FROM active_services")
        active_services = int(cur.fetchone()[0] or 0)
    except Exception:
        active_services = 0
    # Revenue today (last 24h)
    try:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        conn = db._connect_db()
        cur = conn.cursor()
        cur.execute("SELECT SUM(price) FROM sales_log WHERE sale_date >= ?", (since,))
        revenue_24h = float(cur.fetchone()[0] or 0.0)
    except Exception:
        revenue_24h = 0.0

    return {
        "total_users": int(base.get("total_users", 0)),
        "banned_users": int(base.get("banned_users", 0)),
        "active_services": int(active_services),
        "total_revenue": float(base.get("total_revenue", 0.0)),
        "revenue_24h": float(revenue_24h),
        "new_users_7d": int(new_users_7d),
        "users_without_orders": int(users_no_orders),
        "total_traffic_gb": float(total_traffic),
    }

# ---------- HTML (Mini App) ----------
STATS_HTML = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>آمار کلی ربات</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  body { font-family: sans-serif; margin: 0; background: var(--tg-theme-bg-color, #111); color: var(--tg-theme-text-color, #fff); }
  .wrap { padding: 16px; }
  .card { background: rgba(255,255,255,0.06); border-radius: 12px; padding: 14px; margin: 10px 0; }
  .title { font-weight: 700; font-size: 18px; margin: 8px 0 16px; }
  .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .item { background: rgba(255,255,255,0.08); border-radius: 10px; padding: 10px; text-align: center; }
  .item .val { font-size: 18px; font-weight: 700; margin-top: 6px; }
  .muted { opacity: 0.8; }
  .footer { margin-top: 20px; font-size: 12px; opacity: 0.7; text-align: center; }
</style>
</head>
<body>
<div class="wrap">
  <div class="title">آمار کلی ربات</div>
  <div class="card">
    <div class="grid">
      <div class="item"><div class="muted">کاربران کل</div><div id="total_users" class="val">—</div></div>
      <div class="item"><div class="muted">کاربران جدید (۷روز)</div><div id="new_users_7d" class="val">—</div></div>
      <div class="item"><div class="muted">کاربران بدون سفارش</div><div id="users_without_orders" class="val">—</div></div>
      <div class="item"><div class="muted">کاربران مسدود</div><div id="banned_users" class="val">—</div></div>
      <div class="item"><div class="muted">سرویس‌های فعال</div><div id="active_services" class="val">—</div></div>
      <div class="item"><div class="muted">حجم کل مصرف (GB)</div><div id="total_traffic_gb" class="val">—</div></div>
      <div class="item"><div class="muted">درآمد کل (ت)</div><div id="total_revenue" class="val">—</div></div>
      <div class="item"><div class="muted">درآمد ۲۴ساعت (ت)</div><div id="revenue_24h" class="val">—</div></div>
    </div>
  </div>
  <div class="footer">Powered by Telegram WebApp</div>
</div>
<script>
(function(){
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.expand();
    tg.ready();
    try { tg.setHeaderColor('secondary_bg_color'); } catch(e){}
  }
  async function loadStats() {
    try {
      const initData = tg ? tg.initData || "" : "";
      const resp = await fetch('/miniapp/api/stats', {
        headers: { 'X-Telegram-Web-App-Init-Data': initData }
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      function set(id, v){ document.getElementById(id).textContent = v; }
      set('total_users', data.total_users);
      set('new_users_7d', data.new_users_7d);
      set('users_without_orders', data.users_without_orders);
      set('banned_users', data.banned_users);
      set('active_services', data.active_services);
      set('total_traffic_gb', (data.total_traffic_gb || 0).toFixed(2));
      // نمایش تومان بدون اعشار
      set('total_revenue', (data.total_revenue || 0).toLocaleString('fa-IR'));
      set('revenue_24h', (data.revenue_24h || 0).toLocaleString('fa-IR'));
    } catch (e) {
      alert('خطا در دریافت آمار: ' + e.message);
    }
  }
  loadStats();
})();
</script>
</body>
</html>
"""

# ---------- Aiohttp server ----------
_app: Optional[web.Application] = None
_runner: Optional[web.AppRunner] = None
_site: Optional[web.TCPSite] = None

async def _handle_stats_page(request: web.Request) -> web.Response:
    return web.Response(text=STATS_HTML, content_type="text/html; charset=utf-8")

async def _handle_stats_api(request: web.Request) -> web.Response:
    init_data = request.headers.get("X-Telegram-Web-App-Init-Data", "")
    if not _verify_init_data(init_data):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
    payload = _get_stats_payload()
    return web.json_response(payload)

async def start_webapp() -> None:
    """
    راه‌اندازی وب‌سرور مینی‌اپ روی پورت مشخص‌شده.
    """
    global _app, _runner, _site
    if _app is not None:
        return
    _app = web.Application()
    _app.router.add_get("/miniapp/stats", _handle_stats_page)
    _app.router.add_get("/miniapp/api/stats", _handle_stats_api)

    _runner = web.AppRunner(_app)
    await _runner.setup()
    _site = web.TCPSite(_runner, WEBAPP_HOST, WEBAPP_PORT)
    await _site.start()
    print(f"[webapp] started on {WEBAPP_HOST}:{WEBAPP_PORT} (base: {WEBAPP_BASE_URL})")

async def stop_webapp() -> None:
    global _app, _runner, _site
    try:
        if _site:
            await _site.stop()
        if _runner:
            await _runner.cleanup()
    finally:
        _site = None
        _runner = None
        _app = None
