# -*- coding: utf-8 -*-

from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID, TRIAL_ENABLED
from bot.constants import BTN_ADMIN_PANEL, BTN_EXIT_ADMIN_PANEL

def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    منوی اصلی کاربر را می‌سازد و دکمه‌های اختیاری را اضافه می‌کند.
    """
    # دکمه‌های اصلی همیشه نمایش داده می‌شوند
    primary_buttons = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["👤 اطلاعات حساب کاربری", "🎁 کد هدیه"],
        ["💳 شارژ حساب"],
        ["🎁 معرفی دوستان"]
    ]

    # دکمه سرویس تست در صورت فعال بودن
    if TRIAL_ENABLED:
        primary_buttons.insert(2, ["🧪 دریافت سرویس تست رایگان"])

    # دکمه‌های پایینی همیشه نمایش داده می‌شوند
    primary_buttons.append(["📞 پشتیبانی", "📚 راهنما"])

    # تبدیل ADMIN_ID به int برای مقایسه مطمئن
    try:
        admin_id_int = int(ADMIN_ID)
    except (ValueError, TypeError):
        admin_id_int = ADMIN_ID

    # افزودن دکمه پنل ادمین برای ادمین
    if user_id == admin_id_int:
        primary_buttons.append([BTN_ADMIN_PANEL])

    return ReplyKeyboardMarkup(primary_buttons, resize_keyboard=True)

def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    منوی اصلی پنل ادمین با دکمه‌های Reply.
    """
    rows = [
        ["➕ مدیریت پلن‌ها", "📈 گزارش‌ها و آمار"],
        ["👥 مدیریت کاربران", "🎁 مدیریت کد هدیه"],
        ["🖥️ مدیریت نودها", "⚙️ تنظیمات"],
        ["💾 پشتیبان‌گیری", "📩 ارسال پیام"],
        ["🛑 خاموش کردن ربات"],
        [BTN_EXIT_ADMIN_PANEL]
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def get_settings_keyboard() -> ReplyKeyboardMarkup:
    """
    منوی تنظیمات ادمین.
    """
    rows = [
        ["⚙️ تنظیمات عمومی", "🛠️ تنظیمات پیشرفته"],
        ["🌐 تنظیمات سرور", "🧪 تنظیمات سرویس تست"],
        [BTN_EXIT_ADMIN_PANEL]
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def get_yes_no_keyboard() -> ReplyKeyboardMarkup:
    """
    صفحه کلید بله/خیر برای پرسش‌های ساده.
    """
    return ReplyKeyboardMarkup([["بله", "خیر"]], resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    صفحه کلید با دکمه لغو برای عملیات‌های در حال انجام.
    """
    return ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)