# -*- coding: utf-8 -*-

import logging
from typing import Optional

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
from bot.constants import ADMIN_MENU, AWAIT_SETTING_VALUE
from bot.keyboards import get_admin_menu_keyboard

logger = logging.getLogger(__name__)

# -------------------------
# Helpers
# -------------------------

def _get_bool(key: str, default: bool = False) -> bool:
    v = db.get_setting(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "on", "yes", "y")

def _toggle(key: str, default: bool = False) -> bool:
    new_val = not _get_bool(key, default)
    db.set_setting(key, "1" if new_val else "0")
    return new_val

def _kb(rows):
    return InlineKeyboardMarkup(rows)

def _admin_edit_btn(title: str, key: str):
    return InlineKeyboardButton(title, callback_data=f"admin_edit_setting_{key}")

def _back_to_settings_btn():
    return InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="back_to_settings")

# -------------------------
# Main Settings Menu
# -------------------------

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    text = (
        "⚙️ تنظیمات\n\n"
        "یکی از گزینه‌های زیر را انتخاب کنید:"
    )
    kb = _kb([
        [InlineKeyboardButton("🛠 نگهداری", callback_data="settings_maintenance"),
         InlineKeyboardButton("📎 اجبار عضویت", callback_data="settings_force_join")],
        [InlineKeyboardButton("⏳ یادآور انقضا", callback_data="settings_expiry"),
         InlineKeyboardButton("💳 پرداخت", callback_data="settings_payment")],
        [InlineKeyboardButton("🌐 دامنه‌های ساب", callback_data="settings_subdomains"),
         InlineKeyboardButton("📚 راهنماها", callback_data="settings_guides")],
        # دکمه جدید تنظیمات سرویس تست (به trial_settings_ui وصل شده در app.py)
        [InlineKeyboardButton("🧪 تنظیمات سرویس تست", callback_data="settings_trial")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_to_menu")]
    ])

    if q:
        await q.answer()
        try:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

# -------------------------
# Submenus
# -------------------------

async def maintenance_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    enabled = _get_bool("maintenance_enabled", False)
    status = "روشن ✅" if enabled else "خاموش ❌"
    text = f"🛠 نگهداری\n\nوضعیت فعلی: {status}"
    kb = _kb([
        [InlineKeyboardButton("تغییر وضعیت نگهداری", callback_data="toggle_maintenance")],
        [_admin_edit_btn("✍️ متن پیام نگهداری", "maintenance_message")],
        [_back_to_settings_btn()]
    ])
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def force_join_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    enabled = _get_bool("force_join_enabled", False)
    channel = db.get_setting("force_join_channel") or "ثبت نشده"
    status = "فعال ✅" if enabled else "غیرفعال ❌"
    text = f"📎 اجبار عضویت\n\nوضعیت: {status}\nکانال: {channel}"
    kb = _kb([
        [InlineKeyboardButton("تغییر وضعیت اجبار عضویت", callback_data="toggle_force_join")],
        [_admin_edit_btn("✍️ نام کانال (بدون @)", "force_join_channel")],
        [_back_to_settings_btn()]
    ])
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def expiry_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    enabled = _get_bool("expiry_reminder_enabled", True)
    days = db.get_setting("expiry_reminder_days") or "3"
    status = "فعال ✅" if enabled else "غیرفعال ❌"
    text = f"⏳ یادآور انقضا\n\nوضعیت: {status}\nارسال یادآوری {days} روز قبل از انقضا"
    kb = _kb([
        [InlineKeyboardButton("تغییر وضعیت یادآور", callback_data="toggle_expiry_reminder")],
        [_admin_edit_btn("✍️ تعداد روز یادآوری", "expiry_reminder_days")],
        [_back_to_settings_btn()]
    ])
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def payment_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    instr = db.get_setting("payment_instruction_text") or "راهنمایی ثبت نشده است."
    text = "💳 پرداخت\n\nراهنمای پرداخت/شارژ:"
    kb = _kb([
        [_admin_edit_btn("✍️ ویرایش متن راهنمای پرداخت", "payment_instruction_text")],
        [_back_to_settings_btn()]
    ])
    try:
        await q.edit_message_text(text + f"\n\n{instr[:500]}", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text + f"\n\n{instr[:500]}", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def subdomains_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    vol = db.get_setting("volume_based_sub_domains") or "(خالی)"
    unlim = db.get_setting("unlimited_sub_domains") or "(خالی)"
    gen = db.get_setting("sub_domains") or "(خالی)"
    text = (
        "🌐 دامنه‌های ساب\n\n"
        "دامنه‌ها را با کاما جدا کنید. نمونه: sub1.example.com, sub2.example.com\n\n"
        f"حجمی: {vol}\n"
        f"نامحدود: {unlim}\n"
        f"عمومی: {gen}"
    )
    kb = _kb([
        [_admin_edit_btn("✍️ حجمی", "volume_based_sub_domains"),
         _admin_edit_btn("✍️ نامحدود", "unlimited_sub_domains")],
        [_admin_edit_btn("✍️ عمومی", "sub_domains")],
        [_back_to_settings_btn()]
    ])
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

async def guides_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = "📚 راهنماها\n\nراهنماها را ویرایش کنید."
    kb = _kb([
        [_admin_edit_btn("✍️ راهنمای اتصال", "guide_connection")],
        [_admin_edit_btn("✍️ راهنمای شارژ حساب", "guide_charging")],
        [_admin_edit_btn("✍️ راهنمای خرید از ربات", "guide_buying")],
        [_back_to_settings_btn()]
    ])
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

# -------------------------
# Default link type
# -------------------------

async def edit_default_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    current = db.get_setting("default_sub_link_type") or "sub"
    text = f"🔗 نوع پیش‌فرض لینک اشتراک (فعلی: {current}) را انتخاب کنید:"
    kb = _kb([
        [
            InlineKeyboardButton("V2Ray (sub)", callback_data="set_default_link_sub"),
            InlineKeyboardButton("Auto", callback_data="set_default_link_auto"),
        ],
        [
            InlineKeyboardButton("Base64 (sub64)", callback_data="set_default_link_sub64"),
            InlineKeyboardButton("Sing-Box", callback_data="set_default_link_singbox"),
        ],
        [
            InlineKeyboardButton("Xray", callback_data="set_default_link_xray"),
            InlineKeyboardButton("Clash", callback_data="set_default_link_clash"),
        ],
        [
            InlineKeyboardButton("Clash Meta", callback_data="set_default_link_clashmeta"),
        ],
        [_back_to_settings_btn()]
    ])
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb)

async def set_default_link_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    try:
        link_type = q.data.replace("set_default_link_", "").strip()
        db.set_setting("default_sub_link_type", link_type)
        await q.edit_message_text(f"✅ نوع پیش‌فرض روی «{link_type}» تنظیم شد.", reply_markup=_kb([[ _back_to_settings_btn() ]]))
    except Exception as e:
        logger.error("set_default_link_type error: %s", e, exc_info=True)
        await q.edit_message_text("❌ خطا در تنظیم نوع لینک.", reply_markup=_kb([[ _back_to_settings_btn() ]]))

# -------------------------
# Toggles
# -------------------------

async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    new_val = _toggle("maintenance_enabled", False)
    msg = "🛠 نگهداری: روشن ✅" if new_val else "🛠 نگهداری: خاموش ❌"
    try:
        await q.edit_message_text(msg, reply_markup=_kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="settings_maintenance")]]))
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=msg, reply_markup=_kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="settings_maintenance")]]))

async def toggle_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    new_val = _toggle("force_join_enabled", False)
    msg = "📎 اجبار عضویت: فعال ✅" if new_val else "📎 اجبار عضویت: غیرفعال ❌"
    try:
        await q.edit_message_text(msg, reply_markup=_kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="settings_force_join")]]))
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=msg, reply_markup=_kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="settings_force_join")]]))

async def toggle_expiry_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    new_val = _toggle("expiry_reminder_enabled", True)
    msg = "⏳ یادآور انقضا: فعال ✅" if new_val else "⏳ یادآور انقضا: غیرفعال ❌"
    try:
        await q.edit_message_text(msg, reply_markup=_kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="settings_expiry")]]))
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=msg, reply_markup=_kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="settings_expiry")]]))

async def toggle_report_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    الگوی کلی: toggle_report_<key> → مقدار True/False در DB با کلید همان <key>
    """
    q = update.callback_query; await q.answer()
    try:
        key = q.data.replace("toggle_report_", "").strip()
        new_val = _toggle(key, False)
        msg = f"🗒 {key}: {'فعال ✅' if new_val else 'غیرفعال ❌'}"
    except Exception as e:
        logger.error("toggle_report_setting error: %s", e, exc_info=True)
        msg = "❌ خطا در تغییر وضعیت گزارش."
    try:
        await q.edit_message_text(msg, reply_markup=_kb([[ _back_to_settings_btn() ]]))
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=msg, reply_markup=_kb([[ _back_to_settings_btn() ]]))

# -------------------------
# Edit Any Setting (generic)
# -------------------------

async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    key = q.data.replace("admin_edit_setting_", "").strip()
    context.user_data['editing_setting_key'] = key
    cur = db.get_setting(key)
    tip = ""
    if key in ("sub_domains", "volume_based_sub_domains", "unlimited_sub_domains"):
        tip = "\n(دامنه‌ها را با کاما جدا کنید)"
    elif key == "expiry_reminder_days":
        tip = "\n(یک عدد بین 1 تا 30 پیشنهاد می‌شود)"
    elif key == "force_join_channel":
        tip = "\n(نام کانال را بدون @ وارد کنید)"
    text = f"✍️ مقدار جدید برای «{key}» را ارسال کنید.{tip}\n/cancel برای انصراف\n\nمقدار فعلی:\n{(cur or '(خالی)')}"
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=text, parse_mode=ParseMode.MARKDOWN)
    return AWAIT_SETTING_VALUE

async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get('editing_setting_key')
    if not key:
        await update.message.reply_text("❌ کلید تنظیم نامشخص است. دوباره تلاش کنید.")
        return ConversationHandler.END

    val = (update.message.text or "").strip()
    try:
        db.set_setting(key, val)
        await update.message.reply_text(f"✅ مقدار «{key}» ذخیره شد.")
    except Exception as e:
        logger.error("setting_value_received error: %s", e, exc_info=True)
        await update.message.reply_text("❌ خطا در ذخیره مقدار.")
    finally:
        context.user_data.pop('editing_setting_key', None)

    # بازگشت به منوی تنظیمات
    await settings_menu(update, context)
    return ConversationHandler.END

# -------------------------
# Back to admin menu
# -------------------------

async def back_to_admin_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await q.edit_message_text("🔙 بازگشت به منوی مدیریت", reply_markup=get_admin_menu_keyboard())
    except BadRequest:
        await context.bot.send_message(chat_id=q.from_user.id, text="🔙 بازگشت به منوی مدیریت", reply_markup=get_admin_menu_keyboard())