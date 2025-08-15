# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import BadRequest

from bot.constants import AWAIT_SETTING_VALUE, ADMIN_MENU
from bot.keyboards import get_admin_menu_keyboard
import database as db


def _check_enabled(key: str, default: str = "1") -> bool:
    val = db.get_setting(key)
    if val is None:
        val = default
    return str(val).lower() in ("1", "true", "on", "yes")


# ===== Main Settings Menu =====
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        send_func = q.edit_message_text
    else:
        send_func = update.message.reply_text

    keyboard = [
        [InlineKeyboardButton("🛠️ حالت نگه‌داری", callback_data="settings_maintenance")],
        [InlineKeyboardButton("📢 اجبار عضویت", callback_data="settings_force_join")],
        [InlineKeyboardButton("⏰ یادآوری انقضا", callback_data="settings_expiry")],
        [InlineKeyboardButton("💳 تنظیمات پرداخت", callback_data="settings_payment")],
        [InlineKeyboardButton("🌐 تنظیمات ساب‌دامین‌ها", callback_data="settings_subdomains")],
        [InlineKeyboardButton("⚙️ سایر تنظیمات", callback_data="settings_other")],
        [InlineKeyboardButton("↩️ بازگشت به منوی ادمین", callback_data="admin_back_to_menu")],
    ]
    await send_func("بخش تنظیمات اصلی:", reply_markup=InlineKeyboardMarkup(keyboard))


# ===== Submenus =====
async def maintenance_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    maint_on = _check_enabled("maintenance_enabled", "0")
    maint_label = f"حالت نگه‌داری: {'روشن 🟢' if maint_on else 'خاموش 🔴'}"
    keyboard = [
        [InlineKeyboardButton(maint_label, callback_data="toggle_maintenance")],
        [InlineKeyboardButton("✏️ ویرایش پیام", callback_data="admin_edit_setting_maintenance_message")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
    ]
    await q.edit_message_text("تنظیمات حالت نگه‌داری:", reply_markup=InlineKeyboardMarkup(keyboard))

async def force_join_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    force_join_on = _check_enabled("force_channel_enabled", "0")
    force_join_label = f"اجبار عضویت: {'روشن 🟢' if force_join_on else 'خاموش 🔴'}"
    keyboard = [
        [InlineKeyboardButton(force_join_label, callback_data="toggle_force_join")],
        [InlineKeyboardButton("✏️ ویرایش شناسه کانال(ها)", callback_data="admin_edit_setting_force_channel_id")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
    ]
    await q.edit_message_text("تنظیمات اجبار عضویت:", reply_markup=InlineKeyboardMarkup(keyboard))

async def expiry_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    exp_on = _check_enabled("expiry_reminder_enabled", "1")
    exp_label = f"یادآوری انقضا: {'روشن 🟢' if exp_on else 'خاموش 🔴'}"
    keyboard = [
        [InlineKeyboardButton(exp_label, callback_data="toggle_expiry_reminder")],
        [InlineKeyboardButton("📅 روزهای مانده", callback_data="admin_edit_setting_expiry_reminder_days")],
        [InlineKeyboardButton("🕒 ساعت ارسال", callback_data="admin_edit_setting_expiry_reminder_hour")],
        [InlineKeyboardButton("✏️ متن پیام", callback_data="admin_edit_setting_expiry_reminder_message")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
    ]
    await q.edit_message_text("تنظیمات یادآوری انقضا:", reply_markup=InlineKeyboardMarkup(keyboard))

async def payment_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    keyboard = [
        [InlineKeyboardButton("💳 ویرایش شماره کارت", callback_data="admin_edit_setting_card_number")],
        [InlineKeyboardButton("👤 ویرایش نام صاحب حساب", callback_data="admin_edit_setting_card_holder")],
        [InlineKeyboardButton("🎁 ویرایش هدیه دعوت", callback_data="admin_edit_setting_referral_bonus_amount")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
    ]
    await q.edit_message_text("تنظیمات پرداخت و هدیه:", reply_markup=InlineKeyboardMarkup(keyboard))

async def subdomains_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    keyboard = [
        [InlineKeyboardButton("🌐 ویرایش ساب‌دامین‌های حجمی", callback_data="admin_edit_setting_volume_based_sub_domains")],
        [InlineKeyboardButton("♾️ ویرایش ساب‌دامین‌های نامحدود", callback_data="admin_edit_setting_unlimited_sub_domains")],
        [InlineKeyboardButton("🌍 ویرایش ساب‌دامین‌های عمومی", callback_data="admin_edit_setting_sub_domains")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
    ]
    await q.edit_message_text("تنظیمات ساب‌دامین‌ها:", reply_markup=InlineKeyboardMarkup(keyboard))

async def other_settings_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    daily_on = "✅" if _check_enabled("daily_report_enabled", "1") else "❌"
    weekly_on = "✅" if _check_enabled("weekly_report_enabled", "1") else "❌"
    keyboard = [
        [InlineKeyboardButton("🔗 ویرایش نوع لینک پیش‌فرض", callback_data="edit_default_link_type")],
        [InlineKeyboardButton("📝 ویرایش راهنمای اتصال", callback_data="admin_edit_setting_connection_guide")],
        [
            InlineKeyboardButton(f"{daily_on} گزارش روزانه", callback_data="toggle_report_daily"),
            InlineKeyboardButton(f"{weekly_on} گزارش هفتگی", callback_data="toggle_report_weekly"),
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
    ]
    await q.edit_message_text("سایر تنظیمات:", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== Toggles =====
async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    curr = _check_enabled("maintenance_enabled", "0")
    db.set_setting("maintenance_enabled", "0" if curr else "1")
    await maintenance_submenu(update, context)

async def toggle_expiry_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    curr = _check_enabled("expiry_reminder_enabled", "1")
    db.set_setting("expiry_reminder_enabled", "0" if curr else "1")
    await expiry_submenu(update, context)

async def toggle_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    curr = _check_enabled("force_channel_enabled", "0")
    db.set_setting("force_channel_enabled", "0" if curr else "1")
    await force_join_submenu(update, context)

async def toggle_report_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    typ = q.data.replace("toggle_report_", "")
    key = "daily_report_enabled" if typ == "daily" else "weekly_report_enabled"
    curr = _check_enabled(key, "1")
    db.set_setting(key, "0" if curr else "1")
    await other_settings_submenu(update, context)

# ===== Default link type =====
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
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_other")])

    await q.edit_message_text("نوع لینک پیش‌فرض را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(rows))


async def set_default_link_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        val = q.data.replace("set_default_link_", "")
        db.set_setting("default_sub_link_type", val)
        await settings_menu(update, context)
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در ذخیره تنظیم: {e}")


# ===== Edit settings (generic handler) =====
async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if not data.startswith("admin_edit_setting_"):
        await q.edit_message_text("دستور نامعتبر است.")
        return ConversationHandler.END

    setting_key = data.replace("admin_edit_setting_", "")
    context.user_data["setting_key"] = setting_key

    current = db.get_setting(setting_key) or "—"
    msg = ""

    if setting_key in ("sub_domains", "volume_based_sub_domains", "unlimited_sub_domains"):
        msg = (
            f"🌐 ساب‌دامین‌های فعلی:\n{current}\n\n"
            "لطفاً لیست جدید ساب‌دامین‌ها را با کاما (,) جدا کرده و ارسال کنید (مثلاً: sub1.domain.com,sub2.domain.com).\n"
            "برای خالی کردن، یک خط تیره (-) بفرستید."
        )
    elif setting_key in ("guide_connection", "guide_charging", "guide_buying"):
        title = "اتصال" if key == "guide_connection" else "شارژ" if key == "guide_charging" else "خرید"
        msg = f"📝 متن فعلی راهنمای {title}:\n\n{current}\n\nلطفاً متن جدید را ارسال کنید:"
    elif setting_key == "card_number":
        msg = f"💳 شماره کارت فعلی:\n{current}\n\nشماره کارت جدید را ارسال کنید:"
    elif setting_key == "card_holder":
        msg = f"👤 نام صاحب حساب فعلی:\n{current}\n\nنام جدید را ارسال کنید:"
    elif setting_key == "referral_bonus_amount":
        msg = f"🎁 هدیه دعوت فعلی (تومان):\n{current}\n\nمبلغ جدید را به صورت عدد (تومان) ارسال کنید:"
    elif setting_key == "maintenance_message":
        msg = f"🛠 پیام فعلی حالت نگه‌داری:\n\n{current}\n\nمتن جدید را ارسال کنید:"
    elif setting_key == "expiry_reminder_days":
        msg = f"📅 روزهای مانده فعلی: {current}\n\nعدد روزها را ارسال کنید (مثلاً 3):"
    elif setting_key == "expiry_reminder_hour":
        msg = f"🕒 ساعت ارسال فعلی: {current}\n\nیک عدد بین 0 تا 23 ارسال کنید:"
    elif setting_key == "expiry_reminder_message":
        msg = (
            f"✏️ متن فعلی پیام یادآوری:\n\n{current}\n\n"
            "متن جدید را ارسال کنید.\n"
            "می‌توانید از {days} و {service_name} در متن استفاده کنید."
        )
    elif setting_key == "force_channel_id":
        msg = (
            f"📢 شناسه کانال(های) فعلی:\n{current}\n\n"
            "شناسه عددی کانال(ها) را ارسال کنید.\n"
            "برای چند کانال، با کاما (,) جدا کنید (مثلاً: -100123,-100456)."
        )
    else:
        msg = "لطفاً مقدار جدید را ارسال کنید:"

    await q.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True))
    return AWAIT_SETTING_VALUE


async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get("setting_key")
    value_raw = (update.message.text or "").strip()

    if not key:
        await update.message.reply_text("کلید تنظیمات مشخص نیست.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END

    if key in ("referral_bonus_amount", "expiry_reminder_days", "expiry_reminder_hour"):
        try:
            num = int(float(value_raw))
            if key == "expiry_reminder_hour" and not (0 <= num <= 23):
                raise ValueError("ساعت باید بین 0 تا 23 باشد.")
            if key == "expiry_reminder_days" and num <= 0:
                raise ValueError("روز باید بزرگ‌تر از 0 باشد.")
            db.set_setting(key, str(num))
        except ValueError as e:
            await update.message.reply_text(f"❌ مقدار نامعتبر است. {e}")
            return AWAIT_SETTING_VALUE
    elif key == "force_channel_id":
        ids = [s.strip() for s in value_raw.split(',') if s.strip()]
        valid = all(s.startswith('-100') and s[1:].isdigit() for s in ids)
        if not valid and value_raw:
            await update.message.reply_text("❌ شناسه نامعتبر است. باید با -100 شروع شود و فقط عدد باشد.")
            return AWAIT_SETTING_VALUE
        db.set_setting(key, ",".join(ids))
    elif key in ("sub_domains", "volume_based_sub_domains", "unlimited_sub_domains"):
        if value_raw == "-":
            db.set_setting(key, "")
        else:
            domains = [d.strip() for d in value_raw.split(',') if d.strip()]
            if not all("." in d for d in domains):
                await update.message.reply_text("❌ فرمت نامعتبر است. لطفاً دامنه‌ها را با کاما جدا کنید.")
                return AWAIT_SETTING_VALUE
            db.set_setting(key, ",".join(domains))
    else:
        if not value_raw:
            await update.message.reply_text("❌ مقدار خالی است. لطفاً دوباره ارسال کنید.")
            return AWAIT_SETTING_VALUE
        db.set_setting(key, value_raw)

    await update.message.reply_text("✅ مقدار با موفقیت ذخیره شد.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END


# ===== Back to admin menu =====
async def back_to_admin_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except Exception:
        pass
    await q.from_user.send_message("به منوی ادمین بازگشتید.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU