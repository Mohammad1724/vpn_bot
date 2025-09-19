# filename: bot/handlers/users.py
# -*- coding: utf-8 -*-

import re
import logging
import math
import asyncio
from datetime import datetime
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.constants import ParseMode

from bot.constants import (
    USER_MANAGEMENT_MENU, BTN_BACK_TO_ADMIN_MENU,
    BROADCAST_MENU, BROADCAST_MESSAGE, BROADCAST_CONFIRM,
    BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE,
    MANAGE_USER_AMOUNT
)
from bot import utils
import database as db
import hiddify_api

logger = logging.getLogger(__name__)

# --- helpers for input normalization ---
_P2E = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_INVIS = '\u200f\u200e\u200c\u200d \t\r\n'

def normalize_id_input(text: str) -> str:
    s = (text or "").translate(_P2E)
    digits_only = "".join(ch for ch in s if ch.isdigit())
    return digits_only

def normalize_username_input(text: str) -> str:
    s = (text or "").strip()
    for ch in _INVIS:
        s = s.replace(ch, "")
    s = re.sub(r'^(?:https?://)?(?:t(?:elegram)?\.me/)', '', s, flags=re.IGNORECASE)
    s = s.lstrip('@')
    s = re.sub(r'[^A-Za-z0-9_]', '', s)
    return s

def _normalize_amount_text(t: str) -> str:
    """
    نرمال‌سازی مبلغ: تبدیل ارقام فارسی به انگلیسی و حذف جداکننده‌ها/حروف
    """
    s = (t or "").strip().translate(_P2E)
    s = s.replace(",", "").replace("٬", "").replace("،", "").replace(" ", "")
    s = re.sub(r"[^\d.]", "", s)
    return s

# -------------------------------
# Helpers (Inline UI)
# -------------------------------

def _user_mgmt_root_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 جستجو با آیدی (یا شناسه عددی)", callback_data="admin_users_ask_id")],
        [InlineKeyboardButton("📃 لیست کاربران", callback_data="admin_users_list")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")],
    ])

def _action_kb(target_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ افزایش موجودی", callback_data=f"admin_user_addbal_{target_id}"),
            InlineKeyboardButton("➖ کاهش موجودی", callback_data=f"admin_user_subbal_{target_id}"),
        ],
        [
            InlineKeyboardButton("📋 سرویس‌های فعال", callback_data=f"admin_user_services_{target_id}"),
            InlineKeyboardButton("🧾 سوابق خرید", callback_data=f"admin_user_purchases_{target_id}"),
        ],
        [
            InlineKeyboardButton("🧪 ریست سرویس تست", callback_data=f"admin_user_trial_reset_{target_id}"),
            InlineKeyboardButton("🔓 آزاد کردن" if is_banned else "🚫 مسدود کردن", callback_data=f"admin_user_toggle_ban_{target_id}"),
        ],
        [InlineKeyboardButton("🔄 بروزرسانی پنل", callback_data=f"admin_user_refresh_{target_id}")],
        [
            InlineKeyboardButton("🔙 مدیریت کاربران", callback_data="admin_users"),
            InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel"),
        ]
    ]
    return InlineKeyboardMarkup(rows)

def _amount_prompt_kb(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 بازگشت به پنل کاربر", callback_data=f"admin_user_amount_cancel_{target_id}"),
        InlineKeyboardButton("❌ انصراف", callback_data=f"admin_user_amount_cancel_{target_id}")
    ]])

def _back_to_user_panel_kb(target_id: int) -> InlineKeyboardMarkup:
    # استفاده از refresh تا نیازی به هندلر جدید نباشد
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل کاربر", callback_data=f"admin_user_refresh_{target_id}")]])

async def _send_new(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb: InlineKeyboardMarkup | None = None, pm: str | None = None):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=pm)
    else:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=pm)

def _sanitize_for_code(s: str) -> str:
    return (s or "").replace("`", "")

# -------------- Panel Cache --------------
def _cache_panel(context: ContextTypes.DEFAULT_TYPE, target_id: int, text: str, ban_state: bool):
    context.user_data[f"panel_cache_{target_id}"] = {"text": text, "ban_state": 1 if ban_state else 0}

def _get_cached_panel(context: ContextTypes.DEFAULT_TYPE, target_id: int):
    return context.user_data.get(f"panel_cache_{target_id}")

# -------------------------------
# User Panel rendering
# -------------------------------

async def _render_user_panel_text(target_id: int) -> tuple[str, bool]:
    info = db.get_user(target_id)
    if not info:
        return "❌ کاربر یافت نشد.", False
    try:
        services = db.get_user_services(target_id) or []
    except Exception:
        services = []

    ban_state = bool(info.get('is_banned'))

    username = info.get('username') or "-"
    if username != "-" and not username.startswith("@"):
        username = f"@{username}"
    username = _sanitize_for_code(username)

    try:
        total_usage_gb = db.get_total_user_traffic(target_id)
    except Exception:
        total_usage_gb = 0.0

    text = (
        f"👤 شناسه: `{_sanitize_for_code(str(target_id))}`\n"
        f"👥 نام کاربری: `{username}`\n"
        f"💰 موجودی: {int(info.get('balance', 0)):,} تومان\n"
        f"🧪 تست: {'استفاده کرده' if info.get('has_used_trial') else 'آزاد'}\n"
        f"🚫 وضعیت: {'مسدود' if ban_state else 'آزاد'}\n"
        f"📋 تعداد سرویس‌ها: {len(services)}\n"
        f"📊 مصرف کل (همه نودها): {total_usage_gb:.2f} GB"
    )
    return text, ban_state

def _ensure_user_exists(user_id: int):
    try:
        if hasattr(db, "get_or_create_user"):
            db.get_or_create_user(user_id)
    except Exception:
        pass

def _update_balance(user_id: int, delta: int) -> bool:
    _ensure_user_exists(user_id)
    try:
        if hasattr(db, "update_balance"):
            db.update_balance(user_id, delta); return True
        if delta >= 0 and hasattr(db, "increase_balance"):
            db.increase_balance(user_id, delta); return True
        if delta < 0 and hasattr(db, "decrease_balance"):
            db.decrease_balance(user_id, -delta); return True
        if delta >= 0 and hasattr(db, "add_balance"):
            db.add_balance(user_id, delta); return True
        if hasattr(db, "get_user") and hasattr(db, "set_balance"):
            info = db.get_user(user_id)
            cur = int(info.get("balance", 0)) if info else 0
            new_bal = max(cur + delta, 0)
            db.set_balance(user_id, new_bal); return True
    except Exception as e:
        logger.warning("Balance update failed: %s", e, exc_info=True)
    return False

# -------------------------------
# Broadcast (Inline)
# -------------------------------

def _broadcast_root_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 ارسال به همه کاربران", callback_data="bcast_all")],
        [InlineKeyboardButton("👤 ارسال به کاربر خاص", callback_data="bcast_user")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

def _bcast_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="bcast_menu")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📩 بخش ارسال پیام\n\nیکی از گزینه‌های زیر را انتخاب کنید:"
    await _send_new(update, context, text, _broadcast_root_kb())
    return BROADCAST_MENU

async def broadcast_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await broadcast_menu(update, context)

async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["broadcast_mode"] = "all"
    text = "📝 متن/رسانه پیام همگانی را ارسال کنید."
    await _send_new(update, context, text, _bcast_cancel_kb())
    return BROADCAST_MESSAGE

async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.effective_message
    total_users = db.get_all_user_ids()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تایید ارسال", callback_data="broadcast_confirm_yes"),
        InlineKeyboardButton("❌ انصراف", callback_data="broadcast_confirm_no")
    ]])
    await update.effective_message.reply_text(
        f"پیش‌نمایش ثبت شد.\nارسال به {len(total_users)} کاربر انجام شود؟",
        reply_markup=keyboard
    )
    return BROADCAST_CONFIRM

async def broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.endswith("no"):
        try:
            await q.edit_message_text("❌ ارسال همگانی لغو شد.")
        except Exception:
            pass
        context.user_data.clear()
        await broadcast_menu(update, context)
        return BROADCAST_MENU

    msg = context.user_data.get("broadcast_message")
    if not msg:
        try:
            await q.edit_message_text("❌ خطا: پیامی برای ارسال یافت نشد.")
        except Exception:
            pass
        context.user_data.clear()
        await broadcast_menu(update, context)
        return BROADCAST_MENU

    user_ids = db.get_all_user_ids()
    ok = fail = 0
    try:
        await q.edit_message_text(f"در حال ارسال به {len(user_ids)} کاربر... ⏳")
    except Exception:
        pass

    for uid in user_ids:
        try:
            await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            ok += 1
        except RetryAfter as e:
            await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
            try:
                await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
                ok += 1
            except Exception:
                fail += 1
        except (Forbidden, BadRequest, TimedOut, NetworkError):
            fail += 1
        except Exception as e:
            logger.warning("Broadcast send failed to %s: %s", uid, e)
            fail += 1
        await asyncio.sleep(0.05)

    summary = f"✅ ارسال همگانی تمام شد.\nموفق: {ok}\nناموفق: {fail}\nکل: {len(user_ids)}"
    try:
        await q.edit_message_text(summary)
    except Exception:
        await q.from_user.send_message(summary)
    context.user_data.clear()
    await broadcast_menu(update, context)
    return BROADCAST_MENU

async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["broadcast_mode"] = "single"
    await _send_new(update, context, "🔎 آیدی کاربر (یوزرنیم مثل @username) یا شناسه عددی را ارسال کنید:", _bcast_cancel_kb())
    return BROADCAST_TO_USER_ID

async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.effective_message.text or ""
    num = normalize_id_input(raw)
    uid = None
    if num:
        try:
            uid = int(num)
        except Exception:
            uid = None
    if uid is None:
        uname = normalize_username_input(raw)
        rec = db.get_user_by_username(uname) if uname else None
        if not rec:
            await update.effective_message.reply_text("❌ شناسه/آیدی معتبر نیست یا کاربر در دیتابیس نیست.", reply_markup=_bcast_cancel_kb())
            return BROADCAST_TO_USER_ID
        uid = int(rec["user_id"])

    context.user_data["target_user_id"] = uid
    await update.effective_message.reply_text("📝 متن/رسانه پیام را ارسال کنید:", reply_markup=_bcast_cancel_kb())
    return BROADCAST_TO_USER_MESSAGE

async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = context.user_data.get("target_user_id")
    if not uid:
        await update.effective_message.reply_text("❌ شناسه کاربر مشخص نیست.", reply_markup=_broadcast_root_kb())
        context.user_data.clear()
        return BROADCAST_MENU

    msg = update.effective_message
    try:
        await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
        await update.effective_message.reply_text("✅ پیام برای کاربر ارسال شد.", reply_markup=_broadcast_root_kb())
    except Exception:
        await update.effective_message.reply_text("❌ ارسال ناموفق بود. احتمالاً کاربر بات را مسدود کرده یا آیدی اشتباه است.", reply_markup=_broadcast_root_kb())
    context.user_data.clear()
    return BROADCAST_MENU

async def broadcast_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    return await broadcast_menu(update, context)

# -------------------------------
# User Management
# -------------------------------

async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "👥 مدیریت کاربران\n\nآیدی کاربر (یوزرنیم مثل @username) یا شناسه عددی را تایپ کنید، یا از دکمه‌های زیر استفاده کنید."
    await _send_new(update, context, text, _user_mgmt_root_inline())
    return USER_MANAGEMENT_MENU

async def user_management_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await user_management_menu(update, context)

async def ask_user_id_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("✅ منتظر ارسال آیدی یا شناسه عددی کاربر هستم...", show_alert=False)
    return USER_MANAGEMENT_MENU

# ---------- Users List (paged) ----------

_USERS_PAGE_SIZE = 18  # 3 ستون * 6 ردیف پیشنهادی

def _user_btn_label(u: dict) -> str:
    banned = bool(u.get("is_banned"))
    dot = "🔴" if banned else "🟡"
    uname = u.get("username") or f"User_{u.get('user_id')}"
    if len(uname) > 12:
        uname = uname[:11] + "…"
    return f"{dot} |{uname}"

def _build_users_list_markup(users: list[dict], page: int, pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for u in users:
        row.append(InlineKeyboardButton(_user_btn_label(u), callback_data=f"admin_user_open_{u['user_id']}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"admin_users_list_page_{page-1}"))
    if page < pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"admin_users_list_page_{page+1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton("بازگشت", callback_data="admin_users")])
    return InlineKeyboardMarkup(rows)

def _users_list_header(total: int, page: int, pages: int, online_count: int = 0) -> str:
    return (
        "لیست کاربران #\n"
        "❕ شما می‌توانید لیست کاربران و اطلاعات آن‌ها را اینجا مشاهده کنید\n"
        f"👥 تعداد کاربران: {total}\n"
        f"🔵 کاربران آنلاین: {online_count}\n"
        f"صفحه: {page}/{pages}"
    )

async def list_users_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    total = db.get_total_users_count()
    pages = max(1, math.ceil(total / _USERS_PAGE_SIZE))
    page = 1
    users = db.get_all_users_paginated(page=page, page_size=_USERS_PAGE_SIZE)
    text = _users_list_header(total, page, pages, online_count=0)
    kb = _build_users_list_markup(users, page, pages)
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb)
    return USER_MANAGEMENT_MENU

async def list_users_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        page = int(q.data.split("_")[-1])
    except Exception:
        page = 1
    total = db.get_total_users_count()
    pages = max(1, math.ceil(total / _USERS_PAGE_SIZE))
    page = max(1, min(page, pages))
    users = db.get_all_users_paginated(page=page, page_size=_USERS_PAGE_SIZE)
    text = _users_list_header(total, page, pages, online_count=0)
    kb = _build_users_list_markup(users, page, pages)
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb)
    return USER_MANAGEMENT_MENU

async def open_user_from_list_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        target_id = int(q.data.split("_")[-1])
    except Exception:
        return USER_MANAGEMENT_MENU
    await _send_user_panel(update, context, target_id)
    return USER_MANAGEMENT_MENU

# ---------- existing panel/send helpers ----------

async def _send_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int):
    q = getattr(update, "callback_query", None)
    text, ban_state = await _render_user_panel_text(target_id)
    _cache_panel(context, target_id, text, ban_state)
    kb = _action_kb(target_id, ban_state)
    if q:
        try:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def admin_user_back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # باقی گذاشته شده؛ در صورت نیاز می‌توان در app.py رجیستر کرد.
    q = update.callback_query
    await q.answer()
    try:
        target_id = int(q.data.split('_')[-1])
    except Exception:
        return USER_MANAGEMENT_MENU

    cached = _get_cached_panel(context, target_id)
    if not cached:
        return await admin_user_refresh_cb(update, context)

    text = cached.get("text") or "پنل کاربر"
    ban_state = bool(cached.get("ban_state", 0))
    kb = _action_kb(target_id, ban_state)
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return USER_MANAGEMENT_MENU

async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    raw = (em.text or "")
    num = normalize_id_input(raw)
    logger.info(f"[ADMIN] manage_user_id_received: raw='{raw}' -> num='{num}'")

    target_id = None
    if num:
        try:
            target_id = int(num)
        except Exception:
            target_id = None

    if target_id is None:
        uname = normalize_username_input(raw)
        logger.info(f"[ADMIN] manage_user_id_received: uname_norm='{uname}'")
        if not uname:
            await em.reply_text("❌ ورودی نامعتبر است. یوزرنیم (مثل @username) یا شناسه عددی ارسال کنید.", reply_markup=_user_mgmt_root_inline())
            return USER_MANAGEMENT_MENU

        try:
            rec = db.get_user_by_username(uname)
        except Exception as e:
            logger.error(f"get_user_by_username failed for '{uname}': {e}")
            rec = None

        if not rec:
            await em.reply_text(f"❌ کاربری با آیدی @{uname} در دیتابیس یافت نشد. کاربر باید قبلاً ربات را استارت کرده باشد.", reply_markup=_user_mgmt_root_inline())
            return USER_MANAGEMENT_MENU

        target_id = int(rec["user_id"])

    if target_id <= 0:
        await em.reply_text("❌ شناسه معتبر نیست. یک عدد مثبت وارد کنید.", reply_markup=_user_mgmt_root_inline())
        return USER_MANAGEMENT_MENU

    await _send_user_panel(update, context, target_id)
    return USER_MANAGEMENT_MENU

async def admin_user_refresh_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    await _send_user_panel(update, context, target_id)

async def admin_user_services_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        target_id = int(q.data.split('_')[-1])
    except Exception:
        try:
            await q.edit_message_text("❌ شناسه کاربر نامعتبر است.")
        except Exception:
            pass
        return

    services = db.get_user_services(target_id) or []

    if not services:
        txt = "📋 سرویس‌های فعال\n\nهیچ سرویس فعالی برای این کاربر ثبت نشده است."
        kb = _back_to_user_panel_kb(target_id)
        try:
            await q.edit_message_text(txt, reply_markup=kb)
        except Exception:
            await q.from_user.send_message(txt, reply_markup=kb)
        return

    lines = []
    kb_rows = []
    MAX_ITEMS = 40
    over_limit = len(services) > MAX_ITEMS

    for s in services[:MAX_ITEMS]:
        sid = s.get('service_id')
        name = s.get('name') or f"سرویس {sid}"
        server_name = s.get('server_name') or "-"
        lines.append(f"• {name} (ID: {sid}) | نود: {server_name}")
        kb_rows.append([InlineKeyboardButton(f"🗑️ حذف {name}", callback_data=f"admin_delete_service_{sid}_{target_id}")])

    if over_limit:
        lines.append(f"\n… و {len(services) - MAX_ITEMS} سرویس دیگر")

    kb_rows.append([InlineKeyboardButton("🔙 بازگشت به پنل کاربر", callback_data=f"admin_user_refresh_{target_id}")])
    kb = InlineKeyboardMarkup(kb_rows)

    text = "📋 سرویس‌های فعال کاربر:\n\n" + "\n".join(lines)
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except Exception:
        await q.from_user.send_message(text, reply_markup=kb)

async def admin_user_purchases_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])

    purchases = db.get_user_sales_history(target_id)
    if not purchases:
        text = "🧾 سوابق خرید\n\nهیچ سابقه خریدی یافت نشد."
        kb = _back_to_user_panel_kb(target_id)
        try:
            await q.edit_message_text(text, reply_markup=kb)
        except Exception:
            await q.from_user.send_message(text, reply_markup=kb)
        return

    lines = []
    for p in purchases[:30]:
        try:
            price = int(float(p.get('price', 0)))
        except Exception:
            price = 0
        ts = p.get('sale_date') or '-'
        plan_name = p.get('plan_name') or '-'
        lines.append(f"• پلن: {plan_name} | مبلغ: {price:,} تومان | تاریخ: {ts}")

    text = "🧾 سوابق خرید (آخرین ۳۰ مورد):\n\n" + "\n".join(lines)
    kb = _back_to_user_panel_kb(target_id)
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except Exception:
        await q.from_user.send_message(text, reply_markup=kb)

async def admin_user_trial_reset_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    target_id = int(q.data.split('_')[-1])
    db.reset_user_trial(target_id)
    await q.answer("✅ وضعیت تست کاربر ریست شد.", show_alert=False)
    await _send_user_panel(update, context, target_id)

async def admin_user_toggle_ban_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    info = db.get_user(target_id)
    if not info:
        await q.edit_message_text("❌ کاربر یافت نشد.", reply_markup=_back_to_user_panel_kb(target_id))
        return
    ban_state = bool(info.get('is_banned'))
    db.set_user_ban_status(target_id, not ban_state)
    await _send_user_panel(update, context, target_id)

async def admin_user_addbal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    context.user_data["muid"] = target_id
    context.user_data["mop"] = "add"
    try:
        await q.edit_message_text(f"➕ مبلغ افزایش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    except BadRequest:
        await context.bot.send_message(chat_id=q.from_user.id, text=f"➕ مبلغ افزایش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    return MANAGE_USER_AMOUNT

async def admin_user_subbal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    context.user_data["muid"] = target_id
    context.user_data["mop"] = "sub"
    try:
        await q.edit_message_text(f"➖ مبلغ کاهش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    except BadRequest:
        await context.bot.send_message(chat_id=q.from_user.id, text=f"➖ مبلغ کاهش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    return MANAGE_USER_AMOUNT

async def admin_user_amount_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        target_id = int(q.data.split('_')[-1])
    except Exception:
        return USER_MANAGEMENT_MENU
    context.user_data.pop("muid", None)
    context.user_data.pop("mop", None)

    cached = _get_cached_panel(context, target_id)
    if cached:
        text = cached.get("text") or "پنل کاربر"
        ban_state = bool(cached.get("ban_state", 0))
        kb = _action_kb(target_id, ban_state)
        try:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await _send_user_panel(update, context, target_id)
    return USER_MANAGEMENT_MENU

async def manage_user_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    txt = _normalize_amount_text(em.text or "")
    target_id = context.user_data.get("muid")

    try:
        amount = int(abs(float(txt)))
    except Exception:
        kb = _back_to_user_panel_kb(int(target_id)) if target_id else _user_mgmt_root_inline()
        await em.reply_text("❌ مبلغ نامعتبر است. یک عدد مثبت وارد کنید.", reply_markup=kb)
        return MANAGE_USER_AMOUNT

    op = context.user_data.get("mop")
    if not target_id or op not in ("add", "sub"):
        await em.reply_text("❌ حالت نامعتبر. دوباره تلاش کنید.", reply_markup=_user_mgmt_root_inline())
        return USER_MANAGEMENT_MENU

    delta = amount if op == "add" else -amount
    ok = _update_balance(int(target_id), delta)

    if ok:
        await em.reply_text("✅ موجودی کاربر به‌روزرسانی شد.", reply_markup=ReplyKeyboardRemove())
        try:
            info2 = db.get_user(int(target_id))
            new_bal = int(info2.get("balance", 0)) if info2 else None
            op_text = "افزایش" if delta >= 0 else "کاهش"
            amount_str = utils.format_toman(abs(delta), persian_digits=True)
            note_txt = f"موجودی فعلی: {utils.format_toman(new_bal, persian_digits=True)}." if new_bal is not None else ""
            await context.bot.send_message(chat_id=int(target_id), text=f"کیف پول شما توسط پشتیبانی {op_text} یافت به مبلغ {amount_str}. {note_txt}")
        except Forbidden:
            pass
        except Exception as e:
            logger.warning("Notify user about balance change failed: %s", e)
    else:
        await em.reply_text("❌ به‌روزرسانی موجودی ناموفق بود یا در DB پشتیبانی نشده است.", reply_markup=ReplyKeyboardRemove())

    context.user_data.pop("muid", None)
    context.user_data.pop("mop", None)
    await _send_user_panel(update, context, int(target_id))
    return USER_MANAGEMENT_MENU

async def admin_delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    raw = q.data.replace("admin_delete_service_", "", 1)
    parts = raw.split("_")
    service_id = target_id = None
    try:
        service_id = int(parts[0])
        if len(parts) > 1:
            target_id = int(parts[1])
    except Exception:
        await q.edit_message_text("❌ شناسه سرویس نامعتبر است.")
        return

    svc = db.get_service(service_id)
    if not svc:
        if target_id:
            await q.edit_message_text("❌ سرویس یافت نشد.", reply_markup=_back_to_user_panel_kb(target_id))
        else:
            await q.edit_message_text("❌ سرویس یافت نشد.")
        return

    try:
        await q.edit_message_text("در حال حذف سرویس از پنل... ⏳")
    except BadRequest:
        pass

    success = await hiddify_api.delete_user_from_panel(svc['sub_uuid'])

    if not success:
        try:
            probe = await hiddify_api.get_user_info(svc['sub_uuid'])
            if isinstance(probe, dict) and probe.get("_not_found"):
                success = True
        except Exception:
            pass

    if success:
        db.delete_service(service_id)
        if target_id:
            await _send_user_panel(update, context, target_id)
        else:
            try:
                await q.edit_message_text(f"✅ سرویس {svc.get('name') or service_id} با موفقیت از پنل و ربات حذف شد.")
            except BadRequest:
                pass
    else:
        try:
            if target_id:
                await q.edit_message_text("❌ حذف سرویس از پنل ناموفق بود.", reply_markup=_back_to_user_panel_kb(target_id))
            else:
                await q.edit_message_text("❌ حذف سرویس از پنل ناموفق بود.")
        except BadRequest:
            pass

# -------------------------------
# Broadcast (confirm/reject charge remain unchanged)
# -------------------------------

async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        charge_id = int(q.data.split('_')[3])
    except (IndexError, ValueError):
        await q.edit_message_caption("❌ اطلاعات دکمه نامعتبر است.")
        return

    req = db.get_charge_request(charge_id)
    if not req:
        await q.edit_message_caption("❌ درخواست شارژ یافت نشد یا قبلاً پردازش شده است.")
        return

    user_id = int(req['user_id'])
    amount = int(float(req['amount']))
    promo_code_in = (req.get('note') or "").strip().upper()

    ok = db.confirm_charge_request(charge_id)
    if not ok:
        await q.edit_message_caption("❌ تایید شارژ ناموفق بود (احتمالاً در DB).")
        return

    bonus_applied = 0
    try:
        if hasattr(db, "get_user_charge_count") and db.get_user_charge_count(user_id) == 1:
            pc = (db.get_setting('first_charge_code') or '').upper()
            pct = int(db.get_setting('first_charge_bonus_percent') or 0)
            exp_raw = db.get_setting('first_charge_expires_at') or ''
            exp_dt = utils.parse_date_flexible(exp_raw) if exp_raw else None
            now = datetime.now().astimezone()

            if promo_code_in and promo_code_in == pc and pct > 0 and (not exp_dt or now <= exp_dt):
                bonus = int(amount * (pct / 100.0))
                if bonus > 0:
                    _update_balance(user_id, bonus)
                    bonus_applied = bonus
    except Exception as e:
        logger.error(f"Error applying first charge bonus: {e}")

    final_text = f"✅ مبلغ {amount:,} تومان برای کاربر `{user_id}` تایید شد."
    if bonus_applied > 0:
        final_text += f"\n🎁 پاداش شارژ اول به مبلغ {bonus_applied:,} تومان نیز اعمال شد."

    await q.edit_message_caption(final_text, parse_mode=ParseMode.MARKDOWN)

    try:
        user_info = db.get_user(user_id)
        new_balance = user_info['balance'] if user_info else 0
        user_message = f"✅ حساب شما به مبلغ {amount:,} تومان شارژ شد."
        if bonus_applied > 0:
            user_message += f"\n🎁 شما {bonus_applied:,} تومان پاداش شارژ اول دریافت کردید."
        user_message += f"\n💰 موجودی جدید شما: {new_balance:,.0f} تومان"
        await context.bot.send_message(chat_id=user_id, text=user_message)
    except Exception as e:
        logger.warning(f"Failed to notify user {user_id} about successful charge: {e}")

async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        charge_id = int(q.data.split('_')[3])
        user_id = int(q.data.split('_')[4])
    except (IndexError, ValueError):
        await q.edit_message_caption("❌ اطلاعات دکمه نامعتبر است.")
        return

    if db.reject_charge_request(charge_id):
        await q.edit_message_caption(f"❌ درخواست شارژ کاربر `{user_id}` رد شد.")
        try:
            await context.bot.send_message(chat_id=user_id, text="❌ متاسفانه درخواست شارژ شما توسط ادمین رد شد.")
        except Exception:
            pass
    else:
        await q.edit_message_caption("❌ عملیات ناموفق بود یا درخواست قبلاً پردازش شده است.")