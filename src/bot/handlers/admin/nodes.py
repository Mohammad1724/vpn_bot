# -*- coding: utf-8 -*-

import asyncio
import logging
from typing import Optional

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ParseMode

import database as db
from bot.nodes_api import test_node, push_nodes_to_aggregator
from bot.handlers.admin import common as admin_c
from bot.constants import (
    # استیت‌ها در فایل constants.py اضافه خواهند شد
    NODES_MENU,
    NODE_ADD_NAME,
    NODE_ADD_API_BASE,
    NODE_ADD_SUB_PREFIX,
    NODE_ADD_API_KEY,
    NODE_DELETE_ID,
    NODE_TOGGLE_ID,
)

logger = logging.getLogger(__name__)


def _nodes_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["➕ افزودن نود", "📜 لیست نودها"],
        ["🧪 تست همه نودها", "📤 ارسال به تجمیع‌کننده"],
        ["🗑️ حذف نود", "🔄 تغییر وضعیت نود"],
        ["بازگشت به منوی ادمین"],
    ], resize_keyboard=True)


async def nodes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("node_new", None)
    await update.effective_message.reply_text("مدیریت نودها", reply_markup=_nodes_menu_kb())
    return NODES_MENU


async def list_nodes_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nodes = db.list_nodes()
    if not nodes:
        await update.effective_message.reply_text("هیچ نودی ثبت نشده است.", reply_markup=_nodes_menu_kb())
        return NODES_MENU

    lines = ["📜 فهرست نودها:"]
    for n in nodes:
        lines.append(
            f"- ID: <b>{n['node_id']}</b> | "
            f"نام: <b>{n['name']}</b>\n"
            f"  api_base: <code>{n['api_base']}</code>\n"
            f"  sub_prefix: <code>{n.get('sub_prefix') or '-'}</code>\n"
            f"  وضعیت: {'🟢 فعال' if n.get('enabled') else '🔴 غیرفعال'}"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_nodes_menu_kb())
    return NODES_MENU


# -------- افزودن نود --------

async def add_node_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["node_new"] = {}
    await update.effective_message.reply_text("نام نود را وارد کنید:", reply_markup=_nodes_menu_kb())
    return NODE_ADD_NAME


async def add_node_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.effective_message.text or "").strip()
    if not name or name in ("➕ افزودن نود", "📜 لیست نودها", "🧪 تست همه نودها", "📤 ارسال به تجمیع‌کننده",
                            "🗑️ حذف نود", "🔄 تغییر وضعیت نود", "بازگشت به منوی ادمین"):
        await update.effective_message.reply_text("❌ نام معتبر وارد کنید.")
        return NODE_ADD_NAME
    context.user_data["node_new"]["name"] = name
    await update.effective_message.reply_text("آدرس API Base را وارد کنید (مثال: https://node-a.example.com/ADMIN_PATH/ADMIN_UUID/api/v1):")
    return NODE_ADD_API_BASE


async def add_node_api_base_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    api_base = (update.effective_message.text or "").strip().rstrip("/")
    if not (api_base.startswith("http://") or api_base.startswith("https://")) or "/api/v1" not in api_base:
        await update.effective_message.reply_text("❌ فرمت آدرس API Base نامعتبر است. مثال: https://host/ADMIN_PATH/ADMIN_UUID/api/v1")
        return NODE_ADD_API_BASE
    context.user_data["node_new"]["api_base"] = api_base
    await update.effective_message.reply_text("آدرس SUB Prefix برای تجمیع‌کننده را وارد کنید (مثال: https://node-a.example.com/SUB_SECRET). اگر ندارید، '-' بفرستید:")
    return NODE_ADD_SUB_PREFIX


async def add_node_sub_prefix_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subp = (update.effective_message.text or "").strip()
    if subp != "-" and not (subp.startswith("http://") or subp.startswith("https://")):
        await update.effective_message.reply_text("❌ فرمت sub_prefix نامعتبر است. مثال: https://host/SUB_SECRET یا '-'")
        return NODE_ADD_SUB_PREFIX
    context.user_data["node_new"]["sub_prefix"] = (None if subp == "-" else subp.rstrip("/"))
    await update.effective_message.reply_text("API Key (اگر لازم است). اگر ندارید '-' بفرستید:")
    return NODE_ADD_API_KEY


async def add_node_api_key_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    apikey = (update.effective_message.text or "").strip()
    apikey = None if apikey == "-" else apikey
    nd = context.user_data.get("node_new", {})
    node_id = db.add_node(
        nd.get("name"), nd.get("api_base"), apikey, nd.get("sub_prefix"), True
    )
    context.user_data.pop("node_new", None)
    if node_id:
        await update.effective_message.reply_text(f"✅ نود با شناسه {node_id} ثبت شد.", reply_markup=_nodes_menu_kb())
    else:
        await update.effective_message.reply_text("❌ ثبت نود ناموفق بود.", reply_markup=_nodes_menu_kb())
    return NODES_MENU


# -------- حذف نود --------

async def delete_node_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("شناسه (ID) نود برای حذف را وارد کنید:")
    return NODE_DELETE_ID


async def delete_node_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.effective_message.text or "").strip()
    try:
        node_id = int(txt)
    except Exception:
        await update.effective_message.reply_text("❌ شناسه نامعتبر است. یک عدد وارد کنید.", reply_markup=_nodes_menu_kb())
        return NODES_MENU
    ok = db.delete_node(node_id)
    if ok:
        await update.effective_message.reply_text(f"✅ نود {node_id} حذف شد.", reply_markup=_nodes_menu_kb())
    else:
        await update.effective_message.reply_text("❌ حذف نود ناموفق بود یا نود یافت نشد.", reply_markup=_nodes_menu_kb())
    return NODES_MENU


# -------- تغییر وضعیت نود (فعال/غیرفعال) --------

async def toggle_node_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("شناسه (ID) نود برای تغییر وضعیت را وارد کنید:")
    return NODE_TOGGLE_ID


async def toggle_node_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.effective_message.text or "").strip()
    try:
        node_id = int(txt)
    except Exception:
        await update.effective_message.reply_text("❌ شناسه نامعتبر است. یک عدد وارد کنید.", reply_markup=_nodes_menu_kb())
        return NODES_MENU
    node = db.get_node(node_id)
    if not node:
        await update.effective_message.reply_text("❌ نود یافت نشد.", reply_markup=_nodes_menu_kb())
        return NODES_MENU
    new_val = 0 if node.get("enabled") else 1
    db.update_node(node_id, {"enabled": new_val})
    await update.effective_message.reply_text(
        f"✅ وضعیت نود {node_id} به {'فعال' if new_val else 'غیرفعال'} تغییر کرد.",
        reply_markup=_nodes_menu_kb()
    )
    return NODES_MENU


# -------- تست و ارسال به تجمیع‌کننده --------

async def test_all_nodes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nodes = db.list_nodes(only_enabled=True)
    if not nodes:
        await update.effective_message.reply_text("هیچ نود فعالی وجود ندارد.", reply_markup=_nodes_menu_kb())
        return NODES_MENU
    await update.effective_message.reply_text("⏳ در حال تست اتصال نودها...")
    results = []
    for n in nodes:
        ok = await test_node(n)
        results.append(f"{'🟢' if ok else '🔴'} {n['name']}")
    await update.effective_message.reply_text("\n".join(results), reply_markup=_nodes_menu_kb())
    return NODES_MENU


async def push_nodes_to_agg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    agg_api_base = db.get_setting("aggregator_api_base")
    agg_api_key = db.get_setting("aggregator_api_key")
    if not agg_api_base:
        await update.effective_message.reply_text("❌ تنظیمات تجمیع‌کننده ثبت نشده است (aggregator_api_base, aggregator_api_key).", reply_markup=_nodes_menu_kb())
        return NODES_MENU
    subs = [n["sub_prefix"] for n in db.list_nodes(only_enabled=True) if n.get("sub_prefix")]
    if not subs:
        await update.effective_message.reply_text("❌ هیچ sub_prefix معتبری برای ارسال وجود ندارد.", reply_markup=_nodes_menu_kb())
        return NODES_MENU
    ok = await push_nodes_to_aggregator(agg_api_base, agg_api_key, subs)
    await update.effective_message.reply_text("✅ ارسال شد." if ok else "❌ ارسال ناموفق بود.", reply_markup=_nodes_menu_kb())
    return NODES_MENU


# -------- بازگشت --------

async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await admin_c.admin_entry(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text("❌ عملیات لغو شد.", reply_markup=_nodes_menu_kb())
    return NODES_MENU