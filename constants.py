# -*- coding: utf-8 -*-

# <--- FIX: Imports changed for python-telegram-bot library
from telegram import KeyboardButton, ReplyKeyboardMarkup

# --- Button texts (Persian) ---
BUTTON_TEXTS = {
    "services": "سرویس‌ها 🛍️",
    "purchase_service": "خرید سرویس",
    "my_services": "سرویس‌های من 👤",
    "trial_service": "تست رایگان 🎁",
    "wallet": "کیف پول 💳",
    "increase_wallet": "افزایش موجودی",
    "support": "پشتیبانی 📞",
    "referral": "معرفی دوستان 👥",
    "rules": "قوانین 📜",
    "back": " بازگشت ➡️",
    "cancel": "لغو ❌",
    "zarinpal": "پرداخت با زرین‌پال",
}

def create_main_menu_keyboard():
    """Creates the main menu keyboard."""
    keyboard = [
        [KeyboardButton(BUTTON_TEXTS["services"]), KeyboardButton(BUTTON_TEXTS["wallet"])],
        [KeyboardButton(BUTTON_TEXTS["my_services"]), KeyboardButton(BUTTON_TEXTS["support"])],
        [KeyboardButton(BUTTON_TEXTS["referral"]), KeyboardButton(BUTTON_TEXTS["rules"])],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_services_menu_keyboard():
    """Creates the services menu keyboard."""
    keyboard = [
        [KeyboardButton(BUTTON_TEXTS["purchase_service"]), KeyboardButton(BUTTON_TEXTS["trial_service"])],
        [KeyboardButton(BUTTON_TEXTS["back"])]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_back_keyboard():
    """Creates a simple keyboard with only a back button."""
    return ReplyKeyboardMarkup([[KeyboardButton(BUTTON_TEXTS["back"])]], resize_keyboard=True)
    
def create_cancel_keyboard():
    """Creates a simple keyboard with only a cancel button."""
    return ReplyKeyboardMarkup([[KeyboardButton(BUTTON_TEXTS["cancel"])]], resize_keyboard=True)

# --- Conversation States ---
# Define states for conversation handlers
SELECTING_ACTION, SELECTING_SERVICE, TYPING_WALLET_AMOUNT = range(3)