# -*- coding: utf-8 -*-

from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID, TRIAL_ENABLED
from bot.constants import BTN_ADMIN_PANEL, BTN_EXIT_ADMIN_PANEL, BTN_MANAGE_NODES


def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    ساخت منوی اصلی کاربر با نمایش دکمه‌های مرتبط
    """
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["👤 اطلاعات حساب کاربری", "🎁 کد هدیه"],
        ["💳 شارژ حساب"],
        ["🎁 معرفی دوستان"]
    ]

    # نمایش دکمه سرویس تست در صورت فعال بودن
    if TRIAL_ENABLED:
        keyboard.insert(2, ["🧪 دریافت سرویس تست رایگان"])

    # دکمه‌های عمومی پایین منو
    keyboard.append(["📞 پشتیبانی", "📚 راهنما"])

    # تبدیل ADMIN_ID به int برای مقایسه مطمئن
    try:
        admin_id_int = int(ADMIN_ID)
    except (ValueError, TypeError):
        admin_id_int = ADMIN_ID

    # نمایش دکمه ورود به پنل ادمین برای ادمین
    if user_id == admin_id_int:
        keyboard.append([BTN_ADMIN_PANEL])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    ساخت منوی اصلی ادمین با دکمه‌های مدیریتی
    """
    rows = [
        ["➕ مدیریت پلن‌ها", "📈 گزارش‌ها و آمار"],
        ["👥 مدیریت کاربران", "🎁 مدیریت کد هدیه"],
        ["⚙️ تنظیمات", "💾 پشتیبان‌گیری"],
        ["📩 ارسال پیام", "🛑 خاموش کردن ربات"],
        ["🖧 مدیریت نودها"],  # دکمه جدید برای مدیریت نودها
        [BTN_EXIT_ADMIN_PANEL]
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)