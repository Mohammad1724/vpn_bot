# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import BadRequest

from bot.constants import AWAIT_SETTING_VALUE
from bot.keyboards import get_admin_menu_keyboard
import database as db


def _check_enabled(key: str, default: str = "1") -> bool:
    val = db.get_setting(key)
    if val is None:
        val = default
    return str(val) in ("1", "true", "True")


def _settings_keyboard() -> InlineKeyboardMarkup:
    # وضعیت کلیدهای گزارش‌ها
    daily_on = "✅" if _check_enabled("daily_report_enabled", "1") else "❌"
    weekly_on = "✅" if _check_enabled("weekly_report_enabled", "1") else "❌"

    keyboard = [
        [InlineKeyboardButton("🔗 ویرایش نوع لینک پیش‌فرض", callback_data="edit_default_link_type")],
        [InlineKeyboardButton("📝 ویرایش راهنمای اتصال", callback_data="admin_edit_setting_connection_guide")],
        [InlineKeyboardButton("⚙️ تنظیمات پشتیبان‌گیری خودکار", callback_data="edit_auto_backup")],
        [
            InlineKeyboardButton(f"{daily_on} گزارش روزانه", callback_data="toggle_report_daily"),
            InlineKeyboardButton(f"{weekly_on} گزارش هفتگی", callback_data="toggle_report_weekly"),
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # هم Message و هم Callback را هندل می‌کند
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        try:
            await q.edit_message_text("بخش تنظیمات:", reply_markup=_settings_keyboard())
        except BadRequest:
            await q.message.reply_text("بخش تنظیمات:", reply_markup=_settings_keyboard())
    else:
        await update.message.reply_text("بخش تنظیمات:", reply_markup=_settings_keyboard())


# ========== Default link type ==========
async def edit_default_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    current = (db.get_setting("default_sub_link_type") or "sub").lower()
    mapping = [
        ("sub", "V2Ray (sub)"),
        ("auto", "هوشمند (Auto)"),
        ("sub64", "Base64 (sub64)"),
        ("singbox", "SingBox"),
        ("xray", "Xray"),
        ("clash", "Clash"),
        ("clash-meta", "Clash Meta"),
    ]
    rows = []
    for key, title in mapping:
        mark = "✅ " if key == current else ""
        rows.append([InlineKeyboardButton(f"{mark}{title}", callback_data=f"set_default_link_{key}")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")])

    await q.edit_message_text("نوع لینک پیش‌فرض را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(rows))


async def set_default_link_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        val = q.data.replace("set_default_link_", "")
        db.set_setting("default_sub_link_type", val)
        await q.edit_message_text(f"✅ نوع لینک پیش‌فرض تنظیم شد: {val}", reply_markup=_settings_keyboard())
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در ذخیره تنظیم: {e}", reply_markup=_settings_keyboard())


# ========== Edit “connection_guide” ==========
async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # admin_edit_setting_*
    if not data.startswith("admin_edit_setting_"):
        await q.edit_message_text("دستور نامعتبر است.", reply_markup=_settings_keyboard())
        return ConversationHandler.END

    setting_key = data.replace("admin_edit_setting_", "")
    context.user_data["setting_key"] = setting_key

    if setting_key == "connection_guide":
        current = db.get_setting("connection_guide") or "—"
        msg = "📝 متن فعلی راهنمای اتصال:\n\n" + current + "\n\nلطفاً متن جدید را ارسال کنید:"
        # برای دریافت متن، از ReplyKeyboard ساده استفاده می‌کنیم
        await q.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True))
        return AWAIT_SETTING_VALUE

    # اگر کلیدهای دیگری را هم از این مسیر تنظیم می‌کنید:
    await q.edit_message_text("لطفاً مقدار جدید را ارسال کنید.")
    return AWAIT_SETTING_VALUE


async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get("setting_key")
    value = (update.message.text or "").strip()

    if not key:
        await update.message.reply_text("کلید تنظیمات مشخص نیست.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END

    db.set_setting(key, value)
    await update.message.reply_text("✅ مقدار با موفقیت ذخیره شد.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END


# ========== Reports toggles ==========
async def toggle_report_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    typ = q.data.replace("toggle_report_", "")  # daily | weekly
    key = "daily_report_enabled" if typ == "daily" else "weekly_report_enabled"

    curr = _check_enabled(key, "1")
    db.set_setting(key, "0" if curr else "1")
    await settings_menu(update, context)


# ========== Auto-backup interval ==========
async def edit_auto_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    current = db.get_setting("auto_backup_interval_hours") or "24"

    rows = [
        [InlineKeyboardButton("⛔ خاموش", callback_data="set_backup_interval_0")],
        [InlineKeyboardButton("⏱ هر 6 ساعت", callback_data="set_backup_interval_6")],
        [InlineKeyboardButton("🕒 هر 12 ساعت", callback_data="set_backup_interval_12")],
        [InlineKeyboardButton("📅 روزانه", callback_data="set_backup_interval_24")],
        [InlineKeyboardButton("🗓 هفتگی", callback_data="set_backup_interval_168")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
    ]
    await q.edit_message_text(f"بازه پشتیبان‌گیری خودکار (فعلی: {current}h):", reply_markup=InlineKeyboardMarkup(rows))


async def set_backup_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        hours = int(q.data.replace("set_backup_interval_", ""))
        db.set_setting("auto_backup_interval_hours", str(hours))
        await q.edit_message_text("✅ بازه پشتیبان‌گیری ذخیره شد.", reply_markup=_settings_keyboard())
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در ذخیره تنظیم: {e}", reply_markup=_settings_keyboard())