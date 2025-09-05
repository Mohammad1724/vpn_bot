# -*- coding: utf-8 -*-
from typing import Dict, Any, Tuple
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

import database as db
import hiddify_api
from bot.ui import nav_row, confirm_row, chunk, btn, markup

try:
    from config import MULTI_SERVER_ENABLED as MULTI_SERVER_ENABLED_CONFIG, SERVER_SELECTION_POLICY
except Exception:
    MULTI_SERVER_ENABLED_CONFIG = False
    SERVER_SELECTION_POLICY = "least_loaded"

# States
(
    NODES_MENU, ADD_NAME, ADD_PANEL_DOMAIN, ADD_ADMIN_PATH, ADD_SUB_PATH,
    ADD_API_KEY, ADD_SUB_DOMAINS, ADD_CAPACITY, ADD_LOCATION, ADD_CONFIRM,
    NODE_DETAILS, EDIT_FIELD_PICK, EDIT_FIELD_VALUE, DELETE_CONFIRM,
    NODE_SETTINGS_MENU, EDIT_NODE_SETTING_VALUE
) = range(16)


# --- Helpers from settings.py (moved here) ---
def _get_bool(key: str, default: bool = False) -> bool:
    v = db.get_setting(key)
    return str(v).lower() in ("1", "true", "on", "yes") if v is not None else default

def _toggle(key: str, default: bool = False) -> bool:
    new_val = not _get_bool(key, default)
    db.set_setting(key, "1" if new_val else "0")
    return new_val

def _get(key: str, default: str = "") -> str:
    return db.get_setting(key) or default


# ========== Keyboards ==========
def _nodes_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [btn("➕ افزودن نود جدید", "admin_add_node")],
        [btn("📜 لیست نودها", "admin_list_nodes")],
        [btn("⚙️ تنظیمات نود", "admin_node_settings")],
        nav_row(back_cb="admin_back_to_menu", home_cb="home_menu")
    ]
    return markup(rows)


def _sum_server_usage(server_name: str) -> Tuple[float, int]:
    total, cnt = 0.0, 0
    try:
        conn = db._connect_db()
        cur = conn.cursor()
        cur.execute("SELECT SUM(traffic_used) as total, COUNT(*) as cnt FROM user_traffic WHERE server_name = ?", (server_name,))
        if row := cur.fetchone():
            total = float(row["total"] or 0.0)
            cnt = int(row["cnt"] or 0)
    except Exception: pass
    return total, cnt


def _node_row_buttons(n: Dict[str, Any]) -> list:
    return [
        btn(f"{'🟢' if n.get('is_active') else '🔴'} {n.get('name')}", f"admin_node_{n['id']}"),
        btn("🗑️ حذف", f"admin_delete_node_{n['id']}")
    ]


def _node_details_kb(n_id: int) -> InlineKeyboardMarkup:
    return markup([
        [btn("🔁 فعال/غیرفعال", f"admin_toggle_node_{n_id}")],
        [btn("✏️ ویرایش", f"admin_edit_node_{n_id}"), btn("🔌 تست اتصال", f"admin_node_ping_{n_id}")],
        [btn("🔄 بروزرسانی شمار کاربران", f"admin_node_update_count_{n_id}"), btn("📊 مصرف این نود", f"admin_node_usage_{n_id}")],
        [btn("🗑️ حذف", f"admin_delete_node_{n_id}")],
        nav_row(back_cb="admin_list_nodes", home_cb="home_menu")
    ])


# ========== Entrypoints ==========
async def nodes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = getattr(update, "callback_query", None)
    if q: await q.answer(); await q.edit_message_text("مدیریت نودها:", reply_markup=_nodes_menu_kb())
    else: await update.effective_message.reply_text("مدیریت نودها:", reply_markup=_nodes_menu_kb())
    return NODES_MENU


# ========== Node Settings Menu ==========
async def node_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    
    multi_node_on = "فعال ✅" if _get_bool("multi_server_enabled", MULTI_SERVER_ENABLED_CONFIG) else "غیرفعال ❌"
    nodes_h_on = "فعال ✅" if _get_bool("nodes_health_enabled", True) else "غیرفعال ❌"
    policy = _get("server_selection_policy", SERVER_SELECTION_POLICY)
    
    text = (
        "**⚙️ تنظیمات چندنودی و Health-check**\n\n"
        f"▫️ وضعیت چندنودی: {multi_node_on}\n"
        f"▫️ سیاست انتخاب نود: {policy}\n\n"
        f"▫️ Health-check نودها: {nodes_h_on}"
    )
    keyboard = [
        [btn("تغییر وضعیت چندنودی", "toggle_node_setting_multi_server_enabled")],
        [btn("✍️ ویرایش سیاست انتخاب نود", "edit_node_setting_server_selection_policy")],
        [btn("تغییر وضعیت Health-Check", "toggle_node_setting_nodes_health_enabled")],
        [btn("✍️ بازه Health-Check (دقیقه)", "edit_node_setting_nodes_health_interval_min")],
        [btn("✍️ تعداد خطا تا غیرفعال‌سازی", "edit_node_setting_nodes_auto_disable_after_fails")],
        nav_row(back_cb="admin_nodes", home_cb="home_menu")
    ]
    
    await q.edit_message_text(text, reply_markup=markup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return NODE_SETTINGS_MENU

async def toggle_node_setting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    key = q.data.replace("toggle_node_setting_", "")
    
    default_from_config = False
    if key == "multi_server_enabled":
        default_from_config = MULTI_SERVER_ENABLED_CONFIG
    
    _toggle(key, default=default_from_config)
    return await node_settings_menu(update, context)

async def edit_node_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    key = q.data.replace("edit_node_setting_", "")
    context.user_data['editing_node_setting_key'] = key
    
    cur = _get(key, "(خالی)")
    tip = ""
    if key in ("nodes_health_interval_min", "nodes_auto_disable_after_fails"):
        tip = "\n(یک عدد صحیح مثبت وارد کنید)"
    elif key == "server_selection_policy":
        tip = "\n(یکی از: `first`, `by_name`, `least_loaded`)"
        
    text = f"✍️ مقدار جدید برای **{key}** را ارسال کنید.{tip}\n/cancel برای انصراف\n\n**مقدار فعلی:**\n`{cur}`"
    await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    return EDIT_NODE_SETTING_VALUE

async def edit_node_setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    key = context.user_data.get('editing_node_setting_key')
    if not key:
        await update.message.reply_text("❌ کلید نامشخص است."); return ConversationHandler.END

    val = (update.message.text or "").strip()
    
    if key in ("nodes_health_interval_min", "nodes_auto_disable_after_fails"):
        if not val.isdigit() or int(val) <= 0:
            await update.message.reply_text("❌ عدد صحیح مثبت وارد کنید."); return EDIT_NODE_SETTING_VALUE
    
    if key == "server_selection_policy" and val not in ("first", "by_name", "least_loaded"):
        await update.message.reply_text("❌ مقدار نامعتبر است."); return EDIT_NODE_SETTING_VALUE

    db.set_setting(key, val)
    await update.message.reply_text(f"✅ مقدار «{key}» ذخیره شد.")
    
    dummy_q = type('obj', (), {'data': 'admin_node_settings', 'answer': (lambda *a, **kw: None), 'message': update.message})()
    dummy_update = Update(update.update_id, callback_query=dummy_q)
    return await node_settings_menu(dummy_update, context)


# ========== Add Node flow ==========
async def add_node_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["node_add"] = {}
    await update.callback_query.edit_message_text("نام نود را وارد کنید (مثال: آلمان-۱):")
    return ADD_NAME

async def add_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.message.text or "").strip()
    if not name: await update.message.reply_text("نام معتبر نیست."); return ADD_NAME
    context.user_data["node_add"]["name"] = name
    await update.message.reply_text("دامنه پنل را وارد کنید (مثال: panel.example.com):")
    return ADD_PANEL_DOMAIN

async def add_get_panel_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    panel_domain = (update.message.text or "").strip()
    if not panel_domain: await update.message.reply_text("دامنه معتبر نیست."); return ADD_PANEL_DOMAIN
    context.user_data["node_add"]["panel_domain"] = panel_domain
    await update.message.reply_text("admin_path (مسیر ادمین) را وارد کنید:")
    return ADD_ADMIN_PATH

async def add_get_admin_path(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_path = (update.message.text or "").strip().strip("/")
    if not admin_path: await update.message.reply_text("مقدار معتبر نیست."); return ADD_ADMIN_PATH
    context.user_data["node_add"]["admin_path"] = admin_path
    await update.message.reply_text("sub_path (مسیر سابسکریپشن) را وارد کنید:")
    return ADD_SUB_PATH

async def add_get_sub_path(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sub_path = (update.message.text or "").strip().strip("/")
    if not sub_path: await update.message.reply_text("مقدار معتبر نیست."); return ADD_SUB_PATH
    context.user_data["node_add"]["sub_path"] = sub_path
    await update.message.reply_text("API Key پنل را وارد کنید:")
    return ADD_API_KEY

async def add_get_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    api_key = (update.message.text or "").strip()
    if not api_key: await update.message.reply_text("API Key خالی است."); return ADD_API_KEY
    context.user_data["node_add"]["api_key"] = api_key
    await update.message.reply_text("دامنه‌های ساب را با کاما جدا کنید (اختیاری):")
    return ADD_SUB_DOMAINS

async def add_get_sub_domains(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = (update.message.text or "").strip()
    subs = [s.strip() for s in txt.split(",") if s.strip()] if txt else []
    context.user_data["node_add"]["sub_domains"] = subs
    await update.message.reply_text("ظرفیت نود (حداکثر سرویس همزمان) را وارد کنید:")
    return ADD_CAPACITY

async def add_get_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = (update.message.text or "").strip()
    if not txt.isdigit(): await update.message.reply_text("عدد معتبر وارد کنید."); return ADD_CAPACITY
    context.user_data["node_add"]["capacity"] = int(txt)
    await update.message.reply_text("محل/لوکیشن نود را وارد کنید (اختیاری):")
    return ADD_LOCATION

async def add_get_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["node_add"]["location"] = (update.message.text or "").strip() or None
    return await _add_confirm(update, context)

async def _add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nd = context.user_data["node_add"]
    text = f"تایید افزودن نود جدید:\n- نام: {nd['name']}\n- دامنه پنل: {nd['panel_domain']}\n- admin_path: {nd['admin_path']}\n- sub_path: {nd['sub_path']}\n- ظرفیت: {nd['capacity']}\n- موقعیت: {nd.get('location') or '-'}\n- sub_domains: {', '.join(nd.get('sub_domains') or []) or '-'}"
    kb = markup([confirm_row(yes_cb="node_add_confirm", no_cb="node_add_cancel")])
    await update.message.reply_text(text, reply_markup=kb)
    return ADD_CONFIRM

async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    nd = context.user_data.get("node_add", {})
    try:
        db.add_node(**nd, panel_type="hiddify", is_active=True)
        await q.edit_message_text(f"✅ نود «{nd['name']}» اضافه شد.", reply_markup=_nodes_menu_kb())
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در ذخیره نود: {e}", reply_markup=_nodes_menu_kb())
    context.user_data.pop("node_add", None)
    return ConversationHandler.END

async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if q := update.callback_query: await q.answer(); await q.edit_message_text("عملیات لغو شد.", reply_markup=_nodes_menu_kb())
    return ConversationHandler.END

# ========== List / Details ==========
async def list_nodes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if q := update.callback_query: await q.answer()
    nodes = db.list_nodes()
    if not nodes:
        await update.callback_query.edit_message_text("هیچ نودی ثبت نشده.", reply_markup=markup([nav_row("admin_nodes")]))
        return NODES_MENU
    rows = [_node_row_buttons(n) for n in nodes]
    rows.append(nav_row(back_cb="admin_nodes", home_cb="home_menu"))
    await update.callback_query.edit_message_text("لیست نودها:", reply_markup=markup(rows))
    return NODE_DETAILS

async def node_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    node_id = int(q.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n: await q.edit_message_text("نود پیدا نشد."); return NODES_MENU
    total_gb, users_cnt = _sum_server_usage(n["name"])
    text = f"جزئیات نود #{n['id']}:\n- نام: {n['name']}\n- وضعیت: {'فعال' if n['is_active'] else 'غیرفعال'}\n- دامنه پنل: {n['panel_domain']}\n- admin_path: {n['admin_path']} | sub_path: {n['sub_path']}\n- ظرفیت: {n['capacity']} | شمار کاربران (DB): {n.get('current_users', 0)}\n- مصرف snapshot: {total_gb:.2f} GB (برای {users_cnt} کاربر)\n- sub_domains: {', '.join(n.get('sub_domains') or []) or '-'}\n- موقعیت: {n.get('location') or '-'}"
    await q.edit_message_text(text, reply_markup=_node_details_kb(n["id"]))
    return NODE_DETAILS

# ========== Actions on Node ==========
async def toggle_node_active(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    node_id = int(q.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n: await q.edit_message_text("نود پیدا نشد."); return NODES_MENU
    db.update_node(node_id, {"is_active": 0 if n["is_active"] else 1})
    q.data = f"admin_node_{node_id}"
    return await node_details(update, context)

async def ping_node(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer("در حال تست اتصال...")
    node_id = int(q.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n: await q.edit_message_text("نود پیدا نشد."); return NODES_MENU
    ok = await hiddify_api.check_api_connection(server_name=n["name"])
    await q.answer(f"تست اتصال: {'موفق ✅' if ok else 'ناموفق ❌'}", show_alert=True)
    return NODE_DETAILS

async def update_node_usercount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    node_id = int(q.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n: await q.edit_message_text("نود پیدا نشد."); return NODES_MENU
    try:
        cnt = db.count_services_on_node(n["name"])
        db.update_node(node_id, {"current_users": int(cnt)})
        await q.answer(f"شمار کاربران به‌روز شد: {cnt}", show_alert=True)
    except Exception: await q.answer("خطا در بروزرسانی", show_alert=True)
    q.data = f"admin_node_{node_id}"
    return await node_details(update, context)

async def show_node_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    node_id = int(q.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n: await q.edit_message_text("نود پیدا نشد."); return NODES_MENU
    total_gb, users_cnt = _sum_server_usage(n["name"])
    text = f"📊 مصرف snapshot «{n['name']}»:\n- مجموع مصرف: {total_gb:.2f} GB\n- برای {users_cnt} کاربر\n\nاین مقادیر با جاب زمان‌بندی به‌روز می‌شود."
    await q.edit_message_text(text, reply_markup=_node_details_kb(n["id"]))
    return NODE_DETAILS

# ========== Edit ==========
async def edit_node_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    node_id = int(q.data.split("_")[-1])
    context.user_data["edit_node_id"] = node_id
    buttons = [
        btn("نام", f"admin_edit_field_name_{node_id}"), btn("دامنه پنل", f"admin_edit_field_panel_domain_{node_id}"),
        btn("admin_path", f"admin_edit_field_admin_path_{node_id}"), btn("sub_path", f"admin_edit_field_sub_path_{node_id}"),
        btn("API Key", f"admin_edit_field_api_key_{node_id}"), btn("ظرفیت", f"admin_edit_field_capacity_{node_id}"),
        btn("sub_domains", f"admin_edit_field_sub_domains_{node_id}"), btn("موقعیت", f"admin_edit_field_location_{node_id}")
    ]
    rows = chunk(buttons, cols=2)
    rows.append(nav_row(back_cb=f"admin_node_{node_id}", home_cb="home_menu"))
    await q.edit_message_text("کدام فیلد را ویرایش می‌کنید؟", reply_markup=markup(rows))
    return EDIT_FIELD_PICK

async def edit_field_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    field = "_".join(parts[3:-1])
    context.user_data["edit_field"] = field
    prompts = {
        "name": "نام جدید:", "panel_domain": "دامنه پنل جدید:", "admin_path": "admin_path جدید:",
        "sub_path": "sub_path جدید:", "api_key": "API Key جدید:", "capacity": "ظرفیت جدید (عدد):",
        "sub_domains": "دامنه‌های ساب با کاما جدا:", "location": "موقعیت جدید:",
    }
    await q.edit_message_text(prompts[field])
    return EDIT_FIELD_VALUE

async def edit_field_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    node_id = context.user_data.get("edit_node_id")
    field = context.user_data.get("edit_field")
    value = (update.message.text or "").strip()
    if field == "capacity":
        if not value.isdigit(): await update.message.reply_text("عدد معتبر."); return EDIT_FIELD_VALUE
        value = int(value)
    elif field in ("admin_path", "sub_path"):
        value = value.strip().strip("/")
        if not value: await update.message.reply_text("مقدار معتبر نیست."); return EDIT_FIELD_VALUE
    elif field == "sub_domains": value = [s.strip() for s in value.split(",") if s.strip()] if value else []
    elif field == "location" and value == "": value = None
    db.update_node(node_id, {field: value})
    await update.message.reply_text("✅ تغییرات اعمال شد.")
    q = type('obj', (), {'data': f"admin_node_{node_id}", 'answer': (lambda *a, **kw: None), 'message': update.message})()
    dummy_update = Update(update.update_id, callback_query=q)
    return await node_details(dummy_update, context)

# ========== Delete ==========
async def delete_node_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    node_id = int(q.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n: await q.edit_message_text("نود پیدا نشد."); return NODES_MENU
    kb = markup([confirm_row(yes_cb=f"admin_delete_node_yes_{node_id}", no_cb=f"admin_node_{node_id}")])
    await q.edit_message_text(f"آیا از حذف «{n['name']}» مطمئن هستید؟", reply_markup=kb)
    return DELETE_CONFIRM

async def delete_node_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query; await q.answer()
    node_id = int(q.data.split("_")[-1])
    db.delete_node(node_id)
    await q.edit_message_text("✅ نود حذف شد.", reply_markup=_nodes_menu_kb())
    return ConversationHandler.END

# ========== Misc ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message: await update.message.reply_text("عملیات لغو شد.")
    elif q := update.callback_query: await q.answer(); await q.edit_message_text("عملیات لغو شد.")
    return ConversationHandler.END