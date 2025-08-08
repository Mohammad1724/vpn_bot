# -*- coding: utf-8 -*-

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from typing import List, Dict, Any

import database as db
from config import ADMIN_ID, TRIAL_ENABLED, SUB_DOMAINS, PANEL_DOMAIN, SUB_PATH, ADMIN_PATH
from constants import BTN_ADMIN_PANEL, BTN_EXIT_ADMIN_PANEL, BTN_BACK_TO_ADMIN_MENU, CMD_CANCEL, CMD_SKIP

# --- Reply Keyboards ---

async def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Creates the main menu keyboard for a user."""
    user_info = await db.get_or_create_user(user_id)
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["👤 اطلاعات حساب", "🎁 کد هدیه"],
        ["🎁 معرفی دوستان"]
    ]
    if TRIAL_ENABLED and user_info and not user_info.get('has_used_trial'):
        keyboard.insert(2, ["🧪 دریافت سرویس تست رایگان"])
    keyboard.append(["📞 پشتیبانی", "📚 راهنمای اتصال"])
    if user_id == ADMIN_ID:
        keyboard.append([BTN_ADMIN_PANEL])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Creates the main admin panel keyboard."""
    keyboard = [
        ["➕ مدیریت پلن‌ها", "📈 گزارش‌ها و آمار"],
        ["⚙️ تنظیمات", "🎁 مدیریت کد هدیه"],
        ["📩 ارسال پیام", "💾 پشتیبان‌گیری"],
        ["👥 مدیریت کاربران"],
        ["🛑 خاموش کردن ربات", BTN_EXIT_ADMIN_PANEL]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
def get_plan_management_keyboard() -> ReplyKeyboardMarkup:
    """Creates the plan management menu keyboard for admin."""
    return ReplyKeyboardMarkup([
        ["➕ افزودن پلن جدید", "📋 لیست پلن‌ها"],
        [BTN_BACK_TO_ADMIN_MENU]
    ], resize_keyboard=True)

def get_reports_menu_keyboard() -> ReplyKeyboardMarkup:
    """Creates the reports menu keyboard for admin."""
    return ReplyKeyboardMarkup([
        ["📊 آمار کلی", "📈 گزارش فروش امروز"],
        ["📅 گزارش فروش ۷ روز اخیر", "🏆 محبوب‌ترین پلن‌ها"],
        [BTN_BACK_TO_ADMIN_MENU]
    ], resize_keyboard=True)

def get_broadcast_menu_keyboard() -> ReplyKeyboardMarkup:
    """Creates the broadcast menu keyboard for admin."""
    return ReplyKeyboardMarkup([
        ["ارسال به همه کاربران", "ارسال به کاربر خاص"],
        [BTN_BACK_TO_ADMIN_MENU]
    ], resize_keyboard=True)
    
def get_backup_menu_keyboard() -> ReplyKeyboardMarkup:
    """Creates the backup/restore menu keyboard for admin."""
    return ReplyKeyboardMarkup([
        ["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"],
        [BTN_BACK_TO_ADMIN_MENU]
    ], resize_keyboard=True)

def get_user_management_action_keyboard(is_banned: bool) -> ReplyKeyboardMarkup:
    """Creates the action keyboard for managing a specific user."""
    ban_text = "آزاد کردن کاربر" if is_banned else "مسدود کردن کاربر"
    keyboard = [
        ["افزایش موجودی", "کاهش موجودی"],
        ["📜 سوابق خرید", ban_text],
        [BTN_BACK_TO_ADMIN_MENU]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Creates a simple cancel keyboard."""
    return ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)

def get_skip_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Creates a skip and cancel keyboard."""
    return ReplyKeyboardMarkup([[CMD_SKIP], [CMD_CANCEL]], resize_keyboard=True)

def get_broadcast_confirmation_keyboard() -> ReplyKeyboardMarkup:
    """Creates a yes/no keyboard for broadcast confirmation."""
    return ReplyKeyboardMarkup([["بله، ارسال کن"], ["خیر، لغو کن"]], resize_keyboard=True)


# --- Inline Keyboards ---

async def get_service_management_keyboard(service_id: int, sub_uuid: str, plan_id: int) -> InlineKeyboardMarkup:
    """Creates the inline keyboard for managing a specific service."""
    renewal_plan = await db.get_plan(plan_id)
    keyboard = []

    management_buttons = [InlineKeyboardButton("🔄 به‌روزرسانی", callback_data=f"show_service_management_{service_id}")]
    if renewal_plan and plan_id > 0:
        management_buttons.append(InlineKeyboardButton(f"⏳ تمدید ({renewal_plan['price']:.0f} تومان)", callback_data=f"renew_{service_id}"))
    keyboard.append(management_buttons)

    recommended_type = await db.get_setting('recommended_link_type') or 'auto'
    rec_text = " (پیشنهاد ادمین)"
    keyboard.append([InlineKeyboardButton(f"🔗 لینک هوشمند (Auto){rec_text if recommended_type == 'auto' else ''}", callback_data=f"getlink_auto_{sub_uuid}")])
    keyboard.append([
        InlineKeyboardButton(f"Clash{rec_text if recommended_type == 'clash' else ''}", callback_data=f"getlink_clash_{sub_uuid}"),
        InlineKeyboardButton(f"Sub{rec_text if recommended_type == 'sub' else ''}", callback_data=f"getlink_sub_{sub_uuid}")
    ])

    keyboard.append([
        InlineKeyboardButton("⚙️ کانفیگ‌های تکی", callback_data=f"single_configs_{service_id}"),
        InlineKeyboardButton("⬅️ بازگشت", callback_data="back_to_services")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_single_configs_keyboard(service_id: int, info: dict) -> InlineKeyboardMarkup:
    """Creates the inline keyboard for selecting single config types."""
    keyboard = []
    if info.get('vless_link'):
        keyboard.append([InlineKeyboardButton("VLESS", callback_data=f"get_single_vless_{service_id}")])
    if info.get('vmess_link'):
        keyboard.append([InlineKeyboardButton("VMess", callback_data=f"get_single_vmess_{service_id}")])
    if info.get('trojan_link'):
        keyboard.append([InlineKeyboardButton("Trojan", callback_data=f"get_single_trojan_{service_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ بازگشت به مدیریت سرویس", callback_data=f"show_service_management_{service_id}")])
    return InlineKeyboardMarkup(keyboard)
