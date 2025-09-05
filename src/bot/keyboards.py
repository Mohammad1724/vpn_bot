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
        # متن دکمه تست کوتاه شد
        row3 = ["🧪 سرویس تست", "💳 شارژ حساب"]
    else:
        row3 = ["🎁 کد هدیه", "💳 شارژ حساب"]

    # ردیف ۴: هدیه/پشتیبانی
    # دکمه معرفی دوستان از اینجا حذف شد
    row4 = ["🎁 کد هدیه", "📞 پشتیبانی"]

    rows = [row1, row2, row3]
    if not TRIAL_ENABLED:
        # اگر تست فعال نیست، ردیف کد هدیه و پشتیبانی را اضافه می‌کنیم
        rows.append(row4)
    else:
        # اگر تست فعال است، فقط دکمه پشتیبانی را اضافه می‌کنیم
        rows.append(["📞 پشتیبانی"])

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