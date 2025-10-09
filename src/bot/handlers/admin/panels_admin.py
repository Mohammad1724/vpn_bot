# filename: bot/handlers/admin/panels_admin.py
# -*- coding: utf-8 -*-

import json
import logging
from typing import Dict, List, Optional

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from bot.ui import btn, nav_row, markup  # همه دکمه‌ها شیشه‌ای (Inline)
from bot import panels as pnl
import database as db

logger = logging.getLogger(__name__)

# ----- Local conversation states (scoped to this module) -----
PANELS_MENU = 9100

ADD_ID = 9110
ADD_NAME = 9111
ADD_DOMAIN = 9112
ADD_ADMIN_PATH = 9113
ADD_API_KEY = 9114
ADD_SUBDOMAINS = 9115
ADD_SUBPATH = 9116
ADD_SECRET = 9117
ADD_VERIFY = 9118

EDIT_MENU = 9120
EDIT_AWAIT_VALUE = 9121


# ---------- Shared Helpers ----------

def _normalize_panels(items: List[Dict]) -> List[Dict]:
    out = []
    for it in items or []:
        out.append({
            "id": str((it.get("id") or "")).strip(),
            "name": str((it.get("name") or "")).strip(),
            "panel_domain": str((it.get("panel_domain") or "")).strip(),
            "admin_path": str((it.get("admin_path") or "")).strip(),
            "api_key": str((it.get("api_key") or "")).strip(),
            "sub_domains": pnl._norm_subdomains(it.get("sub_domains")),
            "sub_path": str((it.get("sub_path") or "sub")).strip() or "sub",
            "panel_secret_uuid": str((it.get("panel_secret_uuid") or "")).strip(),
            "verify_ssl": bool(it.get("verify_ssl", True)),
        })
    # یکتا بودن id
    seen = set()
    uniq = []
    for p in out:
        pid = p["id"] or ""
        if pid and pid not in seen:
            seen.add(pid)
            uniq.append(p)
    return uniq


def _load_panels() -> List[Dict]:
    """
    Prefer DB settings ('panels_json') if present; fallback to config.
    """
    raw = db.get_setting("panels_json")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                return _normalize_panels(data)
        except Exception as e:
            logger.warning("Invalid panels_json in settings: %s", e)
    return pnl.load_panels()


def _save_panels(panels: List[Dict]) -> None:
    db.set_setting("panels_json", json.dumps(_normalize_panels(panels), ensure_ascii=False))


def _find_index(panels: List[Dict], pid: str) -> int:
    for i, p in enumerate(panels):
        if str(p.get("id")) == str(pid):
            return i
    return -1


def _panel_summary(p: Dict) -> str:
    sd = ", ".join(p.get("sub_domains") or [])
    lines = [
        f"ID: <code>{p.get('id','')}</code>",
        f"نام: {p.get('name','')}",
        f"دامنه پنل: {p.get('panel_domain','')}",
        f"مسیر ادمین: {p.get('admin_path','') or '—'}",
        f"sub_domains: {sd or '—'}",
        f"sub_path: {p.get('sub_path','')}",
        f"Secret UUID: {p.get('panel_secret_uuid','') or '—'}",
        f"SSL: {'✅' if p.get('verify_ssl', True) else '❌'}",
    ]
    return "\n".join(lines)


def _inline_nav(back_cb: str = "admin_panels", cancel_cb: str = "panel_cancel"):
    """
    نوار ناوبری شیشه‌ای: بازگشت + لغو
    """
    return markup([[btn("⬅️ بازگشت", back_cb), btn("❌ لغو", cancel_cb)]])


# ---------- Root menu ----------

async def panels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Root menu for panels management: list panels, add, back/cancel.
    """
    q = update.callback_query
    if q:
        await q.answer()

    panels = _load_panels()

    rows = []
    if panels:
        # نمایش هر پنل با کلید ویرایش/حذف
        for p in panels:
            title = f"{p.get('name') or p.get('id') or 'Panel'} ({p.get('id','')})"
            rows.append([btn(title, f"panel_edit_{p.get('id')}")])
            rows.append([
                btn("✏️ ویرایش", f"panel_edit_{p.get('id')}"),
                btn("🗑️ حذف", f"panel_del_{p.get('id')}")
            ])
    rows.append([btn("➕ افزودن پنل جدید", "panel_add")])
    # ناوبری زیر
    rows.append([btn("⬅️ بازگشت به مدیریت پلن‌ها", "admin_plans"), btn("🏠 منوی ادمین", "admin_panel")])

    text = "🧩 مدیریت پنل‌های Hiddify\nیک پنل را برای ویرایش انتخاب کنید یا «افزودن پنل جدید» را بزنید."
    try:
        if q and q.message:
            await q.message.edit_text(text, reply_markup=markup(rows))
        else:
            await update.effective_message.reply_text(text, reply_markup=markup(rows))
    except BadRequest:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=markup(rows))

    return PANELS_MENU


# ---------- Cancel (go back to panels menu) ----------

async def panel_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    لغو جریان فعلی و بازگشت به منوی مدیریت پنل‌ها.
    """
    context.user_data.pop("panel_new", None)
    context.user_data.pop("panel_edit_id", None)
    context.user_data.pop("panel_edit_field", None)
    return await panels_menu(update, context)


# ---------- Add flow (with inline Back/Cancel on each step) ----------

async def add_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["panel_new"] = {}
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 1/9\n"
        "یک شناسه یکتا وارد کنید (مثلاً de/us/at):",
        reply_markup=_inline_nav(back_cb="admin_panels", cancel_cb="panel_cancel")
    )
    return ADD_ID


async def add_panel_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pid = (update.message.text or "").strip()
    if not pid:
        await update.message.reply_text("شناسه نمی‌تواند خالی باشد. دوباره وارد کنید:", reply_markup=_inline_nav("admin_panels", "panel_cancel"))
        return ADD_ID

    panels = _load_panels()
    if _find_index(panels, pid) != -1:
        await update.message.reply_text("این شناسه قبلاً وجود دارد. شناسه‌ی دیگری وارد کنید:", reply_markup=_inline_nav("admin_panels", "panel_cancel"))
        return ADD_ID

    context.user_data["panel_new"]["id"] = pid
    await update.message.reply_text(
        "افزودن پنل جدید - مرحله 2/9\nنام نمایشی (مثلاً 🇩🇪 آلمان):",
        reply_markup=_inline_nav("panel_add_back_id", "panel_cancel")
    )
    return ADD_NAME


async def add_panel_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["panel_new"]["name"] = (update.message.text or "").strip()
    await update.message.reply_text(
        "افزودن پنل جدید - مرحله 3/9\nآدرس دامنه پنل ادمین (مثلاً https://panel-de.example.com):",
        reply_markup=_inline_nav("panel_add_back_name", "panel_cancel")
    )
    return ADD_DOMAIN


async def add_panel_receive_domain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["panel_new"]["panel_domain"] = (update.message.text or "").strip()
    await update.message.reply_text(
        "افزودن پنل جدید - مرحله 4/9\nمسیر ادمین (اگر دارید، مثلاً UA3jz9I...، در غیر این صورت خالی بفرستید):",
        reply_markup=_inline_nav("panel_add_back_domain", "panel_cancel")
    )
    return ADD_ADMIN_PATH


async def add_panel_receive_admin_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["panel_new"]["admin_path"] = (update.message.text or "").strip()
    await update.message.reply_text(
        "افزودن پنل جدید - مرحله 5/9\nAPI Key پنل را وارد کنید:",
        reply_markup=_inline_nav("panel_add_back_admin_path", "panel_cancel")
    )
    return ADD_API_KEY


async def add_panel_receive_api_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["panel_new"]["api_key"] = (update.message.text or "").strip()
    await update.message.reply_text(
        "افزودن پنل جدید - مرحله 6/9\nدامنه‌های سابسکریپشن را با کاما جدا کنید (مثلاً sub1.example.com, sub2.example.com). اگر ندارید خالی بفرستید:",
        reply_markup=_inline_nav("panel_add_back_api_key", "panel_cancel")
    )
    return ADD_SUBDOMAINS


async def add_panel_receive_subdomains(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip()
    context.user_data["panel_new"]["sub_domains"] = pnl._norm_subdomains(raw.split(",") if raw else [])
    await update.message.reply_text(
        "افزودن پنل جدید - مرحله 7/9\nsub_path (معمولاً sub):",
        reply_markup=_inline_nav("panel_add_back_subdomains", "panel_cancel")
    )
    return ADD_SUBPATH


async def add_panel_receive_subpath(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subp = (update.message.text or "").strip() or "sub"
    context.user_data["panel_new"]["sub_path"] = subp
    await update.message.reply_text(
        "افزودن پنل جدید - مرحله 8/9\nSecret UUID (اگر ندارید خالی بفرستید):",
        reply_markup=_inline_nav("panel_add_back_subpath", "panel_cancel")
    )
    return ADD_SECRET


async def add_panel_receive_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["panel_new"]["panel_secret_uuid"] = (update.message.text or "").strip()
    # مرحله 9: SSL yes/no + Back/Cancel
    kb = markup([
        [btn("✅ بلی (SSL فعال)", "panel_add_ssl_yes"), btn("❌ خیر (SSL غیرفعال)", "panel_add_ssl_no")],
        [btn("⬅️ بازگشت", "panel_add_back_secret"), btn("❌ لغو", "panel_cancel")]
    ])
    await update.message.reply_text(
        "افزودن پنل جدید - مرحله 9/9\nبررسی SSL فعال باشد؟",
        reply_markup=kb
    )
    return ADD_VERIFY


# ---------- Add flow: Back handlers (Inline) ----------

async def add_back_to_id_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 1/9\nیک شناسه یکتا وارد کنید (مثلاً de/us/at):",
        reply_markup=_inline_nav("admin_panels", "panel_cancel")
    )
    return ADD_ID


async def add_back_to_name_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 2/9\nنام نمایشی (مثلاً 🇩🇪 آلمان):",
        reply_markup=_inline_nav("panel_add_back_id", "panel_cancel")
    )
    return ADD_NAME


async def add_back_to_domain_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 3/9\nآدرس دامنه پنل ادمین (مثلاً https://panel-de.example.com):",
        reply_markup=_inline_nav("panel_add_back_name", "panel_cancel")
    )
    return ADD_DOMAIN


async def add_back_to_admin_path_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 4/9\nمسیر ادمین (اگر دارید، مثلاً UA3jz9I...، در غیر این صورت خالی بفرستید):",
        reply_markup=_inline_nav("panel_add_back_domain", "panel_cancel")
    )
    return ADD_ADMIN_PATH


async def add_back_to_api_key_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 5/9\nAPI Key پنل را وارد کنید:",
        reply_markup=_inline_nav("panel_add_back_admin_path", "panel_cancel")
    )
    return ADD_API_KEY


async def add_back_to_subdomains_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 6/9\nدامنه‌های سابسکریپشن را با کاما جدا کنید (مثلاً sub1.example.com, sub2.example.com). اگر ندارید خالی بفرستید:",
        reply_markup=_inline_nav("panel_add_back_api_key", "panel_cancel")
    )
    return ADD_SUBDOMAINS


async def add_back_to_subpath_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 7/9\nsub_path (معمولاً sub):",
        reply_markup=_inline_nav("panel_add_back_subdomains", "panel_cancel")
    )
    return ADD_SUBPATH


async def add_back_to_secret_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text(
        "افزودن پنل جدید - مرحله 8/9\nSecret UUID (اگر ندارید خالی بفرستید):",
        reply_markup=_inline_nav("panel_add_back_subpath", "panel_cancel")
    )
    return ADD_SECRET


# ---------- Add verify: yes/no + save ----------

async def add_panel_receive_verify_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    verify = True if q.data.endswith("_yes") else False
    context.user_data["panel_new"]["verify_ssl"] = verify

    # ذخیره
    newp = context.user_data.get("panel_new") or {}
    panels = _load_panels()
    panels.append(newp)
    _save_panels(panels)
    context.user_data.pop("panel_new", None)

    await q.message.edit_text("✅ پنل جدید ذخیره شد.", reply_markup=_inline_nav("admin_panels", "panel_cancel"))
    # بازگشت به منوی پنل‌ها
    return await panels_menu(update, context)


# ---------- Edit/Delete flow (with Back/Cancel inline) ----------

async def edit_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = q.data.split("_")[-1]
    panels = _load_panels()
    idx = _find_index(panels, pid)
    if idx == -1:
        await q.answer("پنل یافت نشد.", show_alert=True)
        return PANELS_MENU
    context.user_data["panel_edit_id"] = pid

    p = panels[idx]
    text = "✏️ ویرایش پنل\n\n" + _panel_summary(p)
    rows = [
        [btn("نام", "panel_edit_field_name"), btn("دامنه پنل", "panel_edit_field_panel_domain")],
        [btn("مسیر ادمین", "panel_edit_field_admin_path"), btn("API Key", "panel_edit_field_api_key")],
        [btn("sub_domains", "panel_edit_field_sub_domains"), btn("sub_path", "panel_edit_field_sub_path")],
        [btn("Secret UUID", "panel_edit_field_panel_secret_uuid"), btn("SSL Toggle", "panel_edit_field_verify_ssl")],
        [btn("⬅️ بازگشت", "admin_panels"), btn("❌ لغو", "panel_cancel")],
    ]
    await q.message.edit_text(text, reply_markup=markup(rows), parse_mode=ParseMode.HTML)
    return EDIT_MENU


async def edit_panel_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    field = q.data.replace("panel_edit_field_", "")
    pid = context.user_data.get("panel_edit_id")
    if not pid:
        return await panels_menu(update, context)

    # Toggle SSL without asking text
    if field == "verify_ssl":
        panels = _load_panels()
        idx = _find_index(panels, pid)
        if idx == -1:
            await q.answer("پنل یافت نشد.", show_alert=True)
            return EDIT_MENU
        panels[idx]["verify_ssl"] = not bool(panels[idx].get("verify_ssl", True))
        _save_panels(panels)
        await q.answer("تنظیم SSL تغییر کرد.", show_alert=False)
        return await edit_panel_start(update, context)

    # Ask for new value (with Back/Cancel inline)
    field_titles = {
        "name": "نام",
        "panel_domain": "دامنه پنل (مثلاً https://panel.example.com)",
        "admin_path": "مسیر ادمین (اگر ندارید خالی بفرستید)",
        "api_key": "API Key",
        "sub_domains": "دامنه‌های سابسکریپشن (با کاما جدا کنید)",
        "sub_path": "sub_path (مثلاً sub)",
        "panel_secret_uuid": "Secret UUID (اگر ندارید خالی بفرستید)",
    }
    title = field_titles.get(field, field)
    context.user_data["panel_edit_field"] = field

    await q.message.edit_text(
        f"✏️ ویرایش فیلد «{title}»\nمقدار جدید را ارسال کنید.",
        reply_markup=_inline_nav("panel_edit_back", "panel_cancel")
    )
    return EDIT_AWAIT_VALUE


async def edit_panel_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    return await edit_panel_start(update, context)


async def edit_panel_receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = (update.message.text or "").strip()
    pid = context.user_data.get("panel_edit_id")
    field = context.user_data.get("panel_edit_field")
    if not pid or not field:
        await update.message.reply_text("❌ جلسه ویرایش منقضی شد.", reply_markup=_inline_nav("admin_panels", "panel_cancel"))
        return ConversationHandler.END

    panels = _load_panels()
    idx = _find_index(panels, pid)
    if idx == -1:
        await update.message.reply_text("❌ پنل یافت نشد.", reply_markup=_inline_nav("admin_panels", "panel_cancel"))
        return ConversationHandler.END

    if field == "sub_domains":
        panels[idx][field] = pnl._norm_subdomains(val.split(",") if val else [])
    else:
        panels[idx][field] = val

    _save_panels(panels)
    await update.message.reply_text("✅ مقدار ذخیره شد.", reply_markup=_inline_nav("admin_panels", "panel_cancel"))
    # برگشت به صفحه ویرایش
    dummy = Update(update.update_id, callback_query=None)
    dummy.effective_chat = update.effective_chat
    return await edit_panel_start(dummy, context)


# ---------- Delete with Confirm ----------

async def delete_panel_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = q.data.split("_")[-1]
    panels = _load_panels()
    idx = _find_index(panels, pid)
    if idx == -1:
        await q.answer("پنل یافت نشد.", show_alert=True)
        return PANELS_MENU
    p = panels[idx]
    text = f"آیا از حذف پنل «{p.get('name') or p.get('id')}» مطمئن هستید؟"
    rows = [
        [btn("✅ بلی، حذف شود", f"panel_del_yes_{pid}")],
        [btn("⬅️ بازگشت", "admin_panels"), btn("❌ لغو", "panel_cancel")]
    ]
    await q.message.edit_text(text, reply_markup=markup(rows))
    return PANELS_MENU


async def delete_panel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = q.data.split("_")[-1]
    panels = _load_panels()
    idx = _find_index(panels, pid)
    if idx == -1:
        await q.answer("پنل یافت نشد.", show_alert=True)
        return PANELS_MENU
    panels.pop(idx)
    _save_panels(panels)
    await q.message.edit_text("🗑️ پنل حذف شد.", reply_markup=_inline_nav("admin_panels", "panel_cancel"))
    return await panels_menu(update, context)