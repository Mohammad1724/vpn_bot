# -*- coding: utf-8 -*-

from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID, TRIAL_ENABLED
from bot.constants import BTN_ADMIN_PANEL, BTN_EXIT_ADMIN_PANEL

def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    منوی اصلی کاربر را می‌سازد و دکمه‌های اختیاری (تست رایگان، شارژ حساب) را اضافه می‌کند.
    اگر کاربر ادمین باشد، دکمه ورود به پنل ادمین هم نمایش داده می‌شود.
    """
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["👤 اطلاعات حساب کاربری", "🎁 کد هدیه"],
        ["💳 شارژ حساب"],  # دکمه جدید
        ["🎁 معرفی دوستان"]
    ]
    if TRIAL_ENABLED:
        keyboard.insert(2, ["🧪 دریافت سرویس تست رایگان"])

    keyboard.append(["📞 پشتیبانی", "📚 راهنما"])

    # تبدیل ADMIN_ID به int برای مقایسه مطمئن
    try:
        admin_id_int = int(ADMIN_ID)
    except (ValueError, TypeError):
        admin_id_int = ADMIN_ID  # در صورت خطا، همان مقدار قبلی را نگه دار

    if user_id == admin_id_int:
        keyboard.append([BTN_ADMIN_PANEL])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    منوی اصلی پنل ادمین با دکمه‌های Reply.
    """
    rows = [
        ["➕ مدیریت پلن‌ها", "📈 گزارش‌ها و آمار"],
        ["👥 مدیریت کاربران", "🎁 مدیریت کد هدیه"],
        ["⚙️ تنظیمات", "💾 پشتیبان‌گیری"],
        ["📩 ارسال پیام", "🛑 خاموش کردن ربات"],
        [BTN_EXIT_ADMIN_PANEL]
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)