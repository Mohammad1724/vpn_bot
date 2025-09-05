# -*- coding: utf-8 -*-
from typing import Dict, Any, Tuple
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import hiddify_api
from bot.ui import nav_row, confirm_row, chunk, btn, markup

# States
NODES_MENU, ADD_NAME, ADD_PANEL_DOMAIN, ADD_ADMIN_PATH, ADD_SUB_PATH, ADD_API_KEY, ADD_SUB_DOMAINS, ADD_CAPACITY, ADD_LOCATION, ADD_CONFIRM, \
NODE_DETAILS, EDIT_FIELD_PICK, EDIT_FIELD_VALUE, DELETE_CONFIRM = range(14)


# ========== Helpers ==========
def _nodes_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [btn("➕ افزودن نود جدید", "admin_add_node")],
        [btn("📜 لیست نودها", "admin_list_nodes")],
        nav_row(back_cb="admin_back_to_menu", home_cb="home_menu")
    ]
    return markup(rows)


def _sum_server_usage(server_name: str) -> Tuple[float, int]:
    """
    جمع مصرف snapshot از جدول user_traffic برای این نود.
    خروجی: (جمع مصرف به GB، تعداد کاربران دارای رکورد)
    """
    total = 0.0
    cnt = 0
    try:
        conn = db._connect_db()
        cur = conn.cursor()
        cur.execute("SELECT SUM(traffic_used) as total, COUNT(*) as cnt FROM user_traffic WHERE server_name = ?", (server_name,))
        row = cur.fetchone()
        if row:
            total = float(row["total"] or 0.0)
            cnt = int(row["cnt"] or 0)
    except Exception:
        pass
    return total, cnt


def _node_row_buttons(n: Dict[str, Any]) -> list:
    node_id = n["id"]
    status_icon = "🟢" if n.get("is_active") else "🔴"
    return [
        btn(f"{status_icon} {n.get('name')}", f"admin_node_{node_id}"),
        btn("🗑️ حذف", f"admin_delete_node_{node_id}")
    ]


def _node_details_kb(n_id: int) -> InlineKeyboardMarkup:
    return markup([
        [btn("🔁 فعال/غیرفعال", f"admin_toggle_node_{n_id}")],
        [btn("✏️ ویرایش", f"admin_edit_node_{n_id}"), btn("🔌 تست اتصال", f"admin_node_ping_{n_id}")],
        [btn("🔄 بروزرسانی شمار کاربران", f"admin_node_update_count_{n_id}"),
         btn("📊 مصرف این نود", f"admin_node_usage_{n_id}")],
        [btn("🗑️ حذف", f"admin_delete_node_{n_id}")],
        nav_row(back_cb="admin_list_nodes", home_cb="home_menu")
    ])


# ========== Entrypoints ==========
async def nodes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        await q.edit_message_text("مدیریت نودها:", reply_markup=_nodes_menu_kb())
    else:
        await update.effective_message.reply_text("مدیریت نودها:", reply_markup=_nodes_menu_kb())
    return NODES_MENU


# ========== Add Node flow ==========
async def add_node_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data["node_add"] = {}
    await update.callback_query.edit_message_text("نام نود را وارد کنید (مثال: آلمان-۱):")
    return ADD_NAME


async def add_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("نام معتبر نیست. دوباره وارد کنید:")
        return ADD_NAME
    context.user_data["node_add"]["name"] = name
    await update.message.reply_text("دامنه پنل را وارد کنید (مثال: panel.example.com):")
    return ADD_PANEL_DOMAIN


async def add_get_panel_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    panel_domain = (update.message.text or "").strip()
    if not panel_domain:
        await update.message.reply_text("دامنه معتبر نیست. دوباره وارد کنید:")
        return ADD_PANEL_DOMAIN
    context.user_data["node_add"]["panel_domain"] = panel_domain
    await update.message.reply_text("admin_path (مسیر ادمین) را وارد کنید (مثال: admin):")
    return ADD_ADMIN_PATH


async def add_get_admin_path(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_path = (update.message.text or "").strip().strip("/")
    if not admin_path:
        await update.message.reply_text("مقدار معتبر نیست. دوباره وارد کنید:")
        return ADD_ADMIN_PATH
    context.user_data["node_add"]["admin_path"] = admin_path
    await update.message.reply_text("sub_path (مسیر سابسکریپشن) را وارد کنید (مثال: sub):")
    return ADD_SUB_PATH


async def add_get_sub_path(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sub_path = (update.message.text or "").strip().strip("/")
    if not sub_path:
        await update.message.reply_text("مقدار معتبر نیست. دوباره وارد کنید:")
        return ADD_SUB_PATH
    context.user_data["node_add"]["sub_path"] = sub_path
    await update.message.reply_text("API Key پنل را وارد کنید:")
    return ADD_API_KEY


async def add_get_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    api_key = (update.message.text or "").strip()
    if not api_key:
        await update.message.reply_text("API Key خالی است. دوباره وارد کنید:")
        return ADD_API_KEY
    context.user_data["node_add"]["api_key"] = api_key
    await update.message.reply_text("دامنه‌های ساب را با کاما جدا کنید (در صورت نداشتن خالی بفرستید):")
    return ADD_SUB_DOMAINS


async def add_get_sub_domains(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = (update.message.text or "").strip()
    subs = [s.strip() for s in txt.split(",") if s.strip()] if txt else []
    context.user_data["node_add"]["sub_domains"] = subs
    await update.message.reply_text("ظرفیت نود (حداکثر سرویس همزمان) را وارد کنید (مثلا 100):")
    return ADD_CAPACITY


async def add_get_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = (update.message.text or "").strip()
    if not txt.isdigit():
        await update.message.reply_text("عدد معتبر وارد کنید:")
        return ADD_CAPACITY
    context.user_data["node_add"]["capacity"] = int(txt)
    await update.message.reply_text("محل/لوکیشن نود را وارد کنید (مثال: DE یا Germany). اگر نمی‌خواهید: خالی بفرستید")
    return ADD_LOCATION


async def add_get_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["node_add"]["location"] = (update.message.text or "").strip() or None
    return await _add_confirm(update, context)


async def _add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nd = context.user_data["node_add"]
    text = (
        "تایید افزودن نود جدید:\n"
        f"- نام: {nd['name']}\n"
        f"- دامنه پنل: {nd['panel_domain']}\n"
        f"- admin_path: {nd['admin_path']}\n"
        f"- sub_path: {nd['sub_path']}\n"
        f"- ظرفیت: {nd['capacity']}\n"
        f"- موقعیت: {nd.get('location') or '-'}\n"
        f"- sub_domains: {', '.join(nd.get('sub_domains') or []) or '-'}\n"
    )
    kb = markup([confirm_row(yes_cb="node_add_confirm", no_cb="node_add_cancel")])
    await update.message.reply_text(text, reply_markup=kb)
    return ADD_CONFIRM


async def add_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    nd = context.user_data.get("node_add", {})
    try:
        db.add_node(
            name=nd["name"],
            panel_type="hiddify",
            panel_domain=nd["panel_domain"],
            admin_path=nd["admin_path"],
            sub_path=nd["sub_path"],
            api_key=nd["api_key"],
            sub_domains=nd.get("sub_domains"),
            capacity=nd["capacity"],
            location=nd.get("location"),
            is_active=True
        )
        await update.callback_query.edit_message_text(f"✅ نود «{nd['name']}» اضافه شد.", reply_markup=_nodes_menu_kb())
    except Exception as e:
        await update.callback_query.edit_message_text(f"❌ خطا در ذخیره نود: {e}", reply_markup=_nodes_menu_kb())
    context.user_data.pop("node_add", None)
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("عملیات افزودن نود لغو شد.", reply_markup=_nodes_menu_kb())
    return ConversationHandler.END


# ========== List / Details ==========
async def list_nodes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    nodes = db.list_nodes()  # dicts with id, name, ...
    if not nodes:
        kb = markup([nav_row(back_cb="admin_nodes", home_cb="home_menu")])
        await update.callback_query.edit_message_text("هیچ نودی ثبت نشده است.", reply_markup=kb)
        return NODES_MENU

    rows = [_node_row_buttons(n) for n in nodes]
    rows.append(nav_row(back_cb="admin_nodes", home_cb="home_menu"))
    kb = markup(rows)
    await update.callback_query.edit_message_text("لیست نودها:", reply_markup=kb)
    return NODE_DETAILS


async def node_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    node_id = int(update.callback_query.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n:
        await update.callback_query.edit_message_text("نود پیدا نشد.")
        return NODES_MENU

    total_gb, users_cnt = _sum_server_usage(n["name"])
    total_gb_str = f"{total_gb:.2f} GB" if total_gb > 0 else "0 GB"

    text = (
        f"جزئیات نود #{n['id']}:\n"
        f"- نام: {n['name']}\n"
        f"- وضعیت: {'فعال' if n['is_active'] else 'غیرفعال'}\n"
        f"- دامنه پنل: {n['panel_domain']}\n"
        f"- admin_path: {n['admin_path']} | sub_path: {n['sub_path']}\n"
        f"- ظرفیت: {n['capacity']} | شمار کاربران (DB): {n.get('current_users', 0)}\n"
        f"- مصرف snapshot: {total_gb_str} (برای {users_cnt} کاربر)\n"
        f"- sub_domains: {', '.join(n.get('sub_domains') or []) or '-'}\n"
        f"- موقعیت: {n.get('location') or '-'}\n"
    )
    await update.callback_query.edit_message_text(text, reply_markup=_node_details_kb(n["id"]))
    return NODE_DETAILS


# ========== Actions on Node ==========
async def toggle_node_active(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    node_id = int(update.callback_query.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n:
        await update.callback_query.edit_message_text("نود پیدا نشد.")
        return NODES_MENU
    db.update_node(node_id, {"is_active": 0 if n["is_active"] else 1})
    update.callback_query.data = f"admin_node_{node_id}"
    return await node_details(update, context)


async def ping_node(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    node_id = int(update.callback_query.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n:
        await update.callback_query.edit_message_text("نود پیدا نشد.")
        return NODES_MENU
    ok = await hiddify_api.check_api_connection(server_name=n["name"])
    status = "موفق ✅" if ok else "ناموفق ❌"
    await update.callback_query.answer(f"تست اتصال: {status}", show_alert=True)
    update.callback_query.data = f"admin_node_{node_id}"
    return await node_details(update, context)


async def update_node_usercount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    شمار کاربران فعلی (سرویس‌های فعال) روی این نود را از active_services شمرده و در DB نود ذخیره می‌کند.
    """
    await update.callback_query.answer()
    node_id = int(update.callback_query.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n:
        await update.callback_query.edit_message_text("نود پیدا نشد.")
        return NODES_MENU
    try:
        cnt = db.count_services_on_node(n["name"])
        db.update_node(node_id, {"current_users": int(cnt)})
        await update.callback_query.answer(f"به‌روزرسانی شمار کاربران: {cnt}", show_alert=True)
    except Exception:
        await update.callback_query.answer("خطا در بروزرسانی شمار کاربران", show_alert=True)
    update.callback_query.data = f"admin_node_{node_id}"
    return await node_details(update, context)


async def show_node_usage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    نمایش مصرف snapshot این نود (از جدول user_traffic).
    """
    await update.callback_query.answer()
    node_id = int(update.callback_query.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n:
        await update.callback_query.edit_message_text("نود پیدا نشد.")
        return NODES_MENU

    total_gb, users_cnt = _sum_server_usage(n["name"])
    text = (
        f"📊 مصرف snapshot برای «{n['name']}»:\n"
        f"- مجموع مصرف: {total_gb:.2f} GB\n"
        f"- تعداد کاربران دارای رکورد: {users_cnt}\n\n"
        f"توضیح: این مقادیر از جدول user_traffic خوانده می‌شود و با جاب زمان‌بندی به‌روز می‌شود."
    )
    await update.callback_query.edit_message_text(text, reply_markup=_node_details_kb(n["id"]))
    return NODE_DETAILS


# ========== Edit ==========
async def edit_node_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    node_id = int(update.callback_query.data.split("_")[-1])
    context.user_data["edit_node_id"] = node_id
    buttons = [
        btn("نام", f"admin_edit_field_name_{node_id}"),
        btn("دامنه پنل", f"admin_edit_field_panel_domain_{node_id}"),
        btn("admin_path", f"admin_edit_field_admin_path_{node_id}"),
        btn("sub_path", f"admin_edit_field_sub_path_{node_id}"),
        btn("API Key", f"admin_edit_field_api_key_{node_id}"),
        btn("ظرفیت", f"admin_edit_field_capacity_{node_id}"),
        btn("sub_domains", f"admin_edit_field_sub_domains_{node_id}"),
        btn("موقعیت", f"admin_edit_field_location_{node_id}"),
    ]
    rows = chunk(buttons, cols=2)
    rows.append(nav_row(back_cb=f"admin_node_{node_id}", home_cb="home_menu"))
    kb = markup(rows)
    await update.callback_query.edit_message_text("کدام فیلد را ویرایش می‌کنید؟", reply_markup=kb)
    return EDIT_FIELD_PICK


async def edit_field_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    parts = update.callback_query.data.split("_")
    # admin_edit_field_<field>_<id>
    field = "_".join(parts[3:-1])
    context.user_data["edit_field"] = field
    prompts = {
        "name": "نام جدید را وارد کنید:",
        "panel_domain": "دامنه پنل جدید را وارد کنید:",
        "admin_path": "admin_path جدید را وارد کنید:",
        "sub_path": "sub_path جدید را وارد کنید:",
        "api_key": "API Key جدید را وارد کنید:",
        "capacity": "ظرفیت جدید را وارد کنید (عدد):",
        "sub_domains": "دامنه‌های ساب را با کاما جدا کنید (برای حذف خالی بفرستید):",
        "location": "موقعیت جدید را وارد کنید (یا خالی برای حذف):",
    }
    await update.callback_query.edit_message_text(prompts[field])
    return EDIT_FIELD_VALUE


async def edit_field_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    node_id = context.user_data.get("edit_node_id")
    field = context.user_data.get("edit_field")
    value = (update.message.text or "").strip()

    if field == "capacity":
        if not value.isdigit():
            await update.message.reply_text("عدد معتبر وارد کنید:")
            return EDIT_FIELD_VALUE
        value = int(value)
    elif field in ("admin_path", "sub_path"):
        value = value.strip().strip("/")
        if not value:
            await update.message.reply_text("مقدار معتبر نیست:")
            return EDIT_FIELD_VALUE
    elif field == "sub_domains":
        value = [s.strip() for s in value.split(",") if s.strip()] if value else []
    elif field == "location" and value == "":
        value = None

    db.update_node(node_id, {field: value})
    await update.message.reply_text("✅ تغییرات اعمال شد.")
    update.callback_query = type("obj", (), {"data": f"admin_node_{node_id}"})
    return await node_details(update, context)


# ========== Delete ==========
async def delete_node_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    node_id = int(update.callback_query.data.split("_")[-1])
    n = db.get_node(node_id)
    if not n:
        await update.callback_query.edit_message_text("نود پیدا نشد.")
        return NODES_MENU
    kb = markup([confirm_row(yes_cb=f"admin_delete_node_yes_{node_id}", no_cb=f"admin_node_{node_id}")])
    await update.callback_query.edit_message_text(f"آیا از حذف «{n['name']}» مطمئن هستید؟", reply_markup=kb)
    return DELETE_CONFIRM


async def delete_node_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    node_id = int(update.callback_query.data.split("_")[-1])
    db.delete_node(node_id)
    await update.callback_query.edit_message_text("✅ نود حذف شد.", reply_markup=_nodes_menu_kb())
    return ConversationHandler.END


# ========== Misc ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("عملیات لغو شد.")
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("عملیات لغو شد.")
    return ConversationHandler.END