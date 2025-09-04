# -*- coding: utf-8 -*-

from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID, TRIAL_ENABLED
from bot.constants import BTN_ADMIN_PANEL, BTN_EXIT_ADMIN_PANEL

def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    منوی اصلی کاربر (ReplyKeyboard) — چیدمان یکدست و مرتب
    ردیف‌ها ۲ ستونه هستند و ترتیب گزینه‌ها در همه دستگاه‌ها ثابت می‌ماند.
    """
    # ردیف ۱: عملیات اصلی
    row1 = ["🛍️ خرید سرویس", "📋 سرویس‌های من"]

    # ردیف ۲: حساب و راهنما
    row2 = ["👤 اطلاعات حساب کاربری", "📚 راهنما"]

    # ردیف ۳: تست/شارژ
    if TRIAL_ENABLED:
        row3 = ["🧪 دریافت سرویس تست رایگان", "💳 شارژ حساب"]
    else:
        row3 = ["🎁 کد هدیه", "💳 شارژ حساب"]

    # ردیف ۴: هدیه/پشتیبانی
    row4 = ["🎁 معرفی دوستان", "📞 پشتیبانی"]

    # ردیف ۵: کد هدیه (اگر در ردیف ۳ نبود)
    rows = [row1, row2, row3, row4]
    if TRIAL_ENABLED:
        # اگر ردیف ۳ حالت تست داشت، دکمه کد هدیه را هم اضافه می‌کنیم تا همچنان در دسترس باشد
        rows.append(["🎁 کد هدیه"])

    # دکمه پنل ادمین فقط برای ادمین
    try:
        admin_id_int = int(ADMIN_ID)
    except (ValueError, TypeError):
        admin_id_int = ADMIN_ID

    if user_id == admin_id_int:
        rows.append([BTN_ADMIN_PANEL])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    منوی اصلی پنل ادمین (ReplyKeyboard) — چیدمان یکدست ۲ ستونه
    توجه: متن دکمه‌ها را تغییر نداده‌ایم تا Regexهای موجود در app.py خراب نشوند.
    """
    rows = [
        ["➕ مدیریت پلن‌ها", "👥 مدیریت کاربران"],
        ["📈 گزارش‌ها و آمار", "⚙️ تنظیمات"],
        ["🎁 مدیریت کد هدیه", "💾 پشتیبان‌گیری"],
        ["📩 ارسال پیام", "🖥️ مدیریت نودها"],
        ["🛑 خاموش کردن ربات"],
        [BTN_EXIT_ADMIN_PANEL],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def get_settings_keyboard() -> ReplyKeyboardMarkup:
    """
    (اختیاری) یک نمونه کیبورد تنظیمات — اگر در جایی استفاده شود.
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