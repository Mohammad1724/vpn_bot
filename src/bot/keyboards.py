# -*- coding: utf-8 -*-

from telegram import ReplyKeyboardMarkup
from config import ADMIN_ID, TRIAL_ENABLED
from bot.constants import BTN_ADMIN_PANEL

def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["👤 اطلاعات حساب کاربری", "🎁 کد هدیه"],
        ["🎁 معرفی دوستان"]
    ]
    if TRIAL_ENABLED:
        keyboard.insert(2, ["🧪 دریافت سرویس تست رایگان"])

    keyboard.append(["📞 پشتیبانی", "📚 راهنما"]) # ← متن دکمه اصلاح شد

    if user_id == ADMIN_ID:
        keyboard.append([BTN_ADMIN_PANEL])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

from telegram import ReplyKeyboardMarkup

def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["👤 اطلاعات حساب کاربری", "📚 راهنما"],
        ["🧪 دریافت سرویس تست رایگان", "🎁 معرفی دوستان"],
        ["💳 شارژ حساب"],  # دکمه جدید
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)