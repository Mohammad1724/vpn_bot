# -*- coding: utf-8 -*-

from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID, TRIAL_ENABLED
from bot.constants import BTN_ADMIN_PANEL, BTN_EXIT_ADMIN_PANEL

def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    منوی اصلی کاربر (ReplyKeyboard) — با چیدمان سفارشی و متقارن
    """
    rows = [
        # ردیف اول: دکمه‌های اصلی
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        
        # ردیف دوم: دکمه شارژ حساب در وسط
        ["💳 شارژ حساب"],
    ]

    # ردیف سوم: اطلاعات و سرویس تست
    if TRIAL_ENABLED:
        rows.append(["👤 اطلاعات حساب کاربری", "🧪 سرویس تست"])
    else:
        # اگر تست فعال نیست، به جای آن کد هدیه را می‌گذاریم
        rows.append(["👤 اطلاعات حساب کاربری", "🎁 کد هدیه"])

    # ردیف چهارم: راهنما و پشتیبانی
    rows.append(["📚 راهنما", "📞 پشتیبانی"])
    
    # اگر تست فعال بود و دکمه کد هدیه در بالا نبود، اینجا اضافه می‌کنیم (اختیاری)
    # برای حفظ سادگی چیدمان، فعلاً این کار را نمی‌کنیم. اگر خواستید، به راحتی قابل اضافه شدن است.
    # if TRIAL_ENABLED:
    #     rows.append(["🎁 کد هدیه"])

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