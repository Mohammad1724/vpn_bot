# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
from bot import utils
from bot.constants import ADMIN_MENU, AWAIT_SETTING_VALUE, ADMIN_SETTINGS_MENU, GIFT_CODES_MENU
from bot.keyboards import get_admin_menu_keyboard
from bot.ui import nav_row, btn

try:
    from config import USAGE_AGGREGATION_ENABLED as USAGE_AGGREGATION_ENABLED_CONFIG, USAGE_UPDATE_INTERVAL_MIN
except Exception:
    USAGE_AGGREGATION_ENABLED_CONFIG = False
    USAGE_UPDATE_INTERVAL_MIN = 10

logger = logging.getLogger(__name__)

def _get_bool(key: str, default: bool = False) -> bool:
    v = db.get_setting(key)
    return str(v).lower() in ("1", "true", "on", "yes") if v is not None else default

def _toggle(key: str, default: bool = False) -> bool:
    new_val = not _get_bool(key, default)
    db.set_setting(key, "1" if new_val else "0")
    return new_val

def _get(key: str, default: str = "") -> str:
    return db.get_setting(key) or default

def _kb(rows): return InlineKeyboardMarkup(rows)
def _admin_edit_btn(title: str, key: str): return InlineKeyboardButton(title, callback_data=f"admin_edit_setting_{key}")
def _back_to_settings_btn(): return InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="back_to_settings")

async def _send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as e:
            emsg = str(e).lower()
            if "can't parse entities" in emsg or "can't find end of the entity" in emsg:
                try:
                    await q.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
                except Exception:
                    pass
            else:
                try:
                    await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
                except BadRequest as e2:
                    emsg2 = str(e2).lower()
                    if "can't parse entities" in emsg2 or "can't find end of the entity" in emsg2:
                        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup, parse_mode=None)
        except Exception:
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        try:
            await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as e:
            emsg = str(e).lower()
            if "can't parse entities" in emsg or "can't find end of the entity" in emsg:
                await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=None)

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "⚙️ **تنظیمات ربات**\n\nلطفاً بخش مورد نظر را انتخاب کنید:"
    keyboard = _kb([
        [InlineKeyboardButton("🛠 نگهداری و عضویت", callback_data="settings_maint_join")],
        [InlineKeyboardButton("💳 پرداخت و راهنماها", callback_data="settings_payment_guides")],
        [InlineKeyboardButton("⚙️ تنظیمات سرویس", callback_data="settings_service_configs")],
        [InlineKeyboardButton("📊 گزارش‌ها و یادآورها", callback_data="settings_reports_reminders")],
        [InlineKeyboardButton("💡 مصرف کاربران", callback_data="settings_usage_aggregation")],
        [nav_row(back_cb="admin_back_to_menu", home_cb="home_menu")[0]],
    ])
    await _send_or_edit(update, context, text, keyboard, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_SETTINGS_MENU

async def maintenance_and_join_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    maint_status = "روشن ✅" if _get_bool("maintenance_enabled") else "خاموش ❌"
    join_status = "فعال ✅" if _get_bool("force_join_enabled") else "غیرفعال ❌"
    channel = _get("force_join_channel", "ثبت نشده")
    text = f"**🛠 نگهداری و عضویت**\n\n- وضعیت نگهداری: {maint_status}\n- وضعیت عضویت اجباری: {join_status}\n- کانال: @{channel}"
    kb = _kb([
        [InlineKeyboardButton("تغییر وضعیت نگهداری", callback_data="toggle_maintenance")],
        [_admin_edit_btn("✍️ ویرایش پیام نگهداری", "maintenance_message")],
        [InlineKeyboardButton("تغییر وضعیت عضویت", callback_data="toggle_force_join")],
        [_admin_edit_btn("✍️ ویرایش کانال عضویت", "force_join_channel")],
        [_back_to_settings_btn()],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_SETTINGS_MENU

async def payment_and_guides_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "**💳 پرداخت و راهنماها**\n\nاز گزینه‌های زیر برای ویرایش استفاده کنید."
    kb = _kb([
        [InlineKeyboardButton("✍️ ویرایش اطلاعات پرداخت", callback_data="payment_info_submenu")],
        [InlineKeyboardButton("🎁 مدیریت کد شارژ اول", callback_data="first_charge_promo_submenu")],
        [_admin_edit_btn("✍️ راهنمای اتصال", "guide_connection")],
        [_admin_edit_btn("✍️ راهنمای خرید", "guide_buying")],
        [_admin_edit_btn("✍️ راهنمای شارژ", "guide_charging")],
        [_back_to_settings_btn()],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_SETTINGS_MENU

async def first_charge_promo_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = _get("first_charge_code", "ثبت نشده")
    percent = _get("first_charge_bonus_percent", "0")
    expires_raw = _get("first_charge_expires_at", "ثبت نشده")
    expires_at = "همیشگی"
    if expires_raw and expires_raw != "ثبت نشده":
        try:
            dt = utils.parse_date_flexible(expires_raw)
            expires_at = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else expires_raw
        except Exception:
            expires_at = expires_raw
    text = f"🎁 **مدیریت کد شارژ اول**\n\n- کد: `{code}`\n- درصد پاداش: {percent}%\n- تاریخ انقضا: {expires_at}"
    kb = _kb([
        [_admin_edit_btn("✍️ ویرایش کد", "first_charge_code")],
        [_admin_edit_btn("✍️ ویرایش درصد", "first_charge_bonus_percent")],
        [_admin_edit_btn("✍️ ویرایش تاریخ انقضا", "first_charge_expires_at")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_payment_guides")],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_SETTINGS_MENU

async def payment_info_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    instr = _get("payment_instruction_text", "راهنمایی ثبت نشده است.")
    lines = []
    for i in range(1, 4):
        if num := _get(f"payment_card_{i}_number"):
            name = _get(f"payment_card_{i}_name")
            bank = _get(f"payment_card_{i}_bank")
            lines.append(f"**کارت {i}:** `{num}` | {name} | {bank or '-'}")
    text = f"**💳 اطلاعات پرداخت**\n\nراهنمای پرداخت:\n{instr}\n\n" + "\n".join(lines)
    rows = [[_admin_edit_btn("✍️ ویرایش راهنمای پرداخت", "payment_instruction_text")]]
    for i in range(1, 4):
        rows.append([
            _admin_edit_btn(f"کارت {i}", f"payment_card_{i}_number"),
            _admin_edit_btn(f"صاحب کارت {i}", f"payment_card_{i}_name"),
            _admin_edit_btn(f"بانک {i}", f"payment_card_{i}_bank"),
        ])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_payment_guides")])
    await _send_or_edit(update, context, text, _kb(rows), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_SETTINGS_MENU

async def service_configs_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    default_link = _get("default_sub_link_type", "sub")
    text = f"**⚙️ تنظیمات سرویس**\n\n- نوع لینک پیش‌فرض: {default_link}"
    kb = _kb([
        [InlineKeyboardButton("🔗 ویرایش نوع لینک پیش‌فرض", callback_data="edit_default_link_type")],
        [InlineKeyboardButton("🧪 ویرایش تنظیمات سرویس تست", callback_data="settings_trial")],
        [InlineKeyboardButton("🌐 ویرایش دامنه‌های ساب", callback_data="settings_subdomains")],
        [_back_to_settings_btn()],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_SETTINGS_MENU

async def subdomains_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vol = _get("volume_based_sub_domains", "(خالی)")
    unlim = _get("unlimited_sub_domains", "(خالی)")
    gen = _get("sub_domains", "(خالی)")
    text = f"**🌐 دامنه‌های ساب**\n\n- حجمی: `{vol}`\n- نامحدود: `{unlim}`\n- عمومی: `{gen}`"
    kb = _kb([
        [_admin_edit_btn("✍️ ویرایش دامنه‌های حجمی", "volume_based_sub_domains")],
        [_admin_edit_btn("✍️ ویرایش دامنه‌های نامحدود", "unlimited_sub_domains")],
        [_admin_edit_btn("✍️ ویرایش دامنه‌های عمومی", "sub_domains")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_service_configs")],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_SETTINGS_MENU

async def reports_and_reminders_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    daily_on = "فعال ✅" if _get_bool("report_daily_enabled") else "غیرفعال ❌"
    weekly_on = "فعال ✅" if _get_bool("report_weekly_enabled") else "غیرفعال ❌"
    expiry_on = "فعال ✅" if _get_bool("expiry_reminder_enabled", True) else "غیرفعال ❌"
    expiry_days = _get("expiry_reminder_days", "3")
    min_gb = _get("expiry_reminder_min_remaining_gb", "0")
    text = f"**📊 گزارش‌ها و یادآورها**\n\n- گزارش روزانه: {daily_on}\n- گزارش هفتگی: {weekly_on}\n- یادآور انقضا: {expiry_on} ({expiry_days} روز قبل, حداقل {min_gb}GB)"
    kb = _kb([
        [InlineKeyboardButton("تغییر گزارش روزانه", callback_data="toggle_report_report_daily_enabled"),
         InlineKeyboardButton("تغییر گزارش هفتگی", callback_data="toggle_report_report_weekly_enabled")],
        [InlineKeyboardButton("تغییر یادآور انقضا", callback_data="toggle_expiry_reminder")],
        [_admin_edit_btn("✍️ ویرایش روزهای یادآور", "expiry_reminder_days"),
         _admin_edit_btn("✍️ ویرایش حداقل حجم یادآور", "expiry_reminder_min_remaining_gb")],
        [_back_to_settings_btn()],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_SETTINGS_MENU

async def usage_aggregation_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usage_agg_on = "فعال ✅" if _get_bool("usage_aggregation_enabled", USAGE_AGGREGATION_ENABLED_CONFIG) else "غیرفعال ❌"
    interval_min = _get("usage_update_interval_min", str(USAGE_UPDATE_INTERVAL_MIN))
    text = f"💡 **تنظیمات مصرف کاربران**\n\n▫️ تجمیع مصرف: {usage_agg_on}\n▫️ بازه به‌روزرسانی مصرف: {interval_min} دقیقه"
    kb = _kb([
        [InlineKeyboardButton("تغییر وضعیت تجمیع مصرف", callback_data="toggle_usage_aggregation")],
        [_admin_edit_btn("✍️ بازه به‌روزرسانی (دقیقه)", "usage_update_interval_min")],
        [_back_to_settings_btn()],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=None)
    return ADMIN_SETTINGS_MENU

async def global_discount_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    enabled = "فعال ✅" if _get_bool("global_discount_enabled") else "غیرفعال ❌"
    percent = _get("global_discount_percent", "0")
    days = _get("global_discount_days", "0")
    starts_raw = _get("global_discount_starts_at", "")
    expires_raw = _get("global_discount_expires_at", "")

    def _fmt(ts: str) -> str:
        if not ts:
            return "(تعریف نشده)"
        try:
            dt = utils.parse_date_flexible(ts)
            if dt:
                return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        return ts

    text = (
        f"٪ **تخفیف همگانی** (مدت‌محور)\n\n"
        f"- وضعیت: {enabled}\n"
        f"- درصد: {percent}%\n"
        f"- مدت: {days} روز\n"
        f"- شروع از: {_fmt(starts_raw)}\n"
        f"- پایان در: {_fmt(expires_raw)}\n\n"
        f"راهنما:\n"
        f"- فقط «درصد» و «مدت (روز)» را تنظیم کنید. با روشن‌کردن، از همین لحظه به مدت تعیین‌شده فعال می‌شود.\n"
        f"- اگر «مدت» صفر باشد، تخفیف تا زمانی که خاموش کنید نامحدود است."
    )

    kb = _kb([
        [InlineKeyboardButton("تغییر وضعیت تخفیف همگانی", callback_data="toggle_global_discount")],
        [_admin_edit_btn("✍️ درصد تخفیف", "global_discount_percent")],
        [_admin_edit_btn("✍️ مدت (روز)", "global_discount_days")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_gift")],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=ParseMode.MARKDOWN)
    return GIFT_CODES_MENU

async def toggle_global_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    currently_on = _get_bool("global_discount_enabled")
    if not currently_on:
        db.set_setting("global_discount_enabled", "1")
        try:
            days = int(float(_get("global_discount_days", "0") or 0))
        except Exception:
            days = 0
        now = datetime.now().astimezone()
        db.set_setting("global_discount_starts_at", now.isoformat())
        if days > 0:
            db.set_setting("global_discount_expires_at", (now + timedelta(days=days)).isoformat())
        else:
            db.set_setting("global_discount_expires_at", "")
    else:
        db.set_setting("global_discount_enabled", "0")
    return await global_discount_submenu(update, context)

def _infer_return_target(key: str) -> str:
    if key.startswith("payment_card_") or key == "payment_instruction_text": return "payment_info"
    if key.startswith("first_charge_"): return "first_charge_promo"
    if key.startswith("guide_"): return "payment_guides"
    if key.endswith("sub_domains"): return "subdomains"
    if key in ("maintenance_message", "force_join_channel"): return "maintenance_join"
    if key.startswith("expiry_reminder_"): return "reports_reminders"
    if key.startswith("usage_"): return "usage_aggregation"
    if key.startswith("global_discount_"): return "global_discount"
    return "settings_root"

async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    key = (q.data if q else "").replace("admin_edit_setting_", "").strip()
    context.user_data['editing_setting_key'] = key
    context.user_data['settings_return_to'] = _infer_return_target(key)
    cur = _get(key, "(خالی)")
    tip = ""
    if key.startswith("payment_card_"): tip = "\n(برای پاک کردن، `-` ارسال کنید)"
    elif "sub_domains" in key: tip = "\n(دامنه‌ها را با کاما جدا کنید)"
    elif key in ("first_charge_expires_at"): tip = "\n(فرمت: 2025-12-31T23:59:59+03:30 یا 2025-12-31 23:59)"
    elif key == "usage_update_interval_min": tip = "\n(عدد صحیح مثبت)"
    elif key == "global_discount_percent": tip = "\n(عدد درصد؛ مثال: 10)"
    elif key == "global_discount_days": tip = "\n(تعداد روز؛ مثال: 5. اگر 0 بزنید، نامحدود می‌شود.)"
    text = f"✍️ مقدار جدید برای **{key}** را ارسال کنید.{tip}\n/cancel برای انصراف\n\n**مقدار فعلی:**\n`{cur}`"
    await _send_or_edit(update, context, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    return AWAIT_SETTING_VALUE

async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get('editing_setting_key')
    if not key:
        await update.message.reply_text("❌ کلید نامشخص است.")
        return ConversationHandler.END

    val = (update.message.text or "").strip()
    if val == "-":
        val = ""

    if key == "usage_update_interval_min":
        try:
            intval = int(float(val)); assert intval > 0; val = str(intval)
        except Exception:
            await update.message.reply_text("❌ عدد صحیح مثبت وارد کنید.")
            return AWAIT_SETTING_VALUE

    if key == "global_discount_percent":
        try:
            p = float(val); assert p >= 0; val = str(int(p))
        except Exception:
            await update.message.reply_text("❌ درصد نامعتبر است.")
            return AWAIT_SETTING_VALUE

    if key == "global_discount_days":
        try:
            d = int(float(val)); assert d >= 0; val = str(int(d))
        except Exception:
            await update.message.reply_text("❌ تعداد روز نامعتبر است.")
            return AWAIT_SETTING_VALUE

    db.set_setting(key, val)

    if key == "global_discount_days" and _get_bool("global_discount_enabled"):
        try:
            d = int(_get("global_discount_days", "0") or 0)
        except Exception:
            d = 0
        starts_raw = _get("global_discount_starts_at", "")
        starts_dt = utils.parse_date_flexible(starts_raw) if starts_raw else datetime.now().astimezone()
        if d > 0:
            db.set_setting("global_discount_expires_at", (starts_dt + timedelta(days=d)).isoformat())
        else:
            db.set_setting("global_discount_expires_at", "")

    await update.message.reply_text(f"✅ مقدار «{key}» ذخیره شد.")
    dest = context.user_data.pop('settings_return_to', None) or _infer_return_target(key)
    context.user_data.pop('editing_setting_key', None)

    if dest == "first_charge_promo": return await first_charge_promo_submenu(update, context)
    if dest == "payment_info": return await payment_info_submenu(update, context)
    if dest == "payment_guides": return await payment_and_guides_submenu(update, context)
    if dest == "subdomains": return await subdomains_submenu(update, context)
    if dest == "maintenance_join": return await maintenance_and_join_submenu(update, context)
    if dest == "reports_reminders": return await reports_and_reminders_submenu(update, context)
    if dest == "usage_aggregation": return await usage_aggregation_submenu(update, context)
    if dest == "global_discount": return await global_discount_submenu(update, context)
    return await settings_menu(update, context)

async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _toggle("maintenance_enabled")
    return await maintenance_and_join_submenu(update, context)

async def toggle_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _toggle("force_join_enabled")
    return await maintenance_and_join_submenu(update, context)

async def toggle_expiry_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _toggle("expiry_reminder_enabled", True)
    return await reports_and_reminders_submenu(update, context)

async def toggle_report_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    key = (q.data if q else "").replace("toggle_report_", "").strip()
    _toggle(key)
    return await reports_and_reminders_submenu(update, context)

async def edit_default_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = _get("default_sub_link_type", "sub")
    text = f"🔗 نوع پیش‌فرض لینک اشتراک (فعلی: {current}) را انتخاب کنید:"
    kb = _kb([
        [btn("V2Ray (sub)", "set_default_link_sub"), btn("Auto", "set_default_link_auto")],
        [btn("Base64 (sub64)", "set_default_link_sub64"), btn("SingBox", "set_default_link_singbox")],
        [btn("Xray", "set_default_link_xray"), btn("Clash", "set_default_link_clash")],
        [btn("Clash Meta", "set_default_link_clashmeta")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_service_configs")],
    ])
    await _send_or_edit(update, context, text, kb, parse_mode=None)
    return ADMIN_SETTINGS_MENU

async def set_default_link_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    link_type = (q.data if q else "").replace("set_default_link_", "").strip()
    if link_type:
        db.set_setting("default_sub_link_type", link_type)
        if q:
            await q.answer(f"✅ نوع پیش‌فرض روی «{link_type}» تنظیم شد.", show_alert=True)
        else:
            await update.effective_message.reply_text(f"✅ نوع پیش‌فرض روی «{link_type}» تنظیم شد.")
    return await service_configs_submenu(update, context)

async def toggle_usage_aggregation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _toggle("usage_aggregation_enabled", USAGE_AGGREGATION_ENABLED_CONFIG)
    return await usage_aggregation_submenu(update, context)

async def back_to_admin_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=q.from_user.id, text="🔙 بازگشت به منوی مدیریت", reply_markup=get_admin_menu_keyboard())
    else:
        await update.effective_message.reply_text("🔙 بازگشت به منوی مدیریت", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU