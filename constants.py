# -*- coding: utf-8 -*-

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
    # --- Admin Buttons ---
    "admin_panel": "پنل مدیریت ⚙️",
    "user_management": "مدیریت کاربران",
    "statistics": "آمار فروش",
    "broadcast": "ارسال پیام همگانی",
    "back_to_user_menu": "بازگشت به منوی کاربری",
}

def create_main_menu_keyboard(is_admin: bool = False):
    """
    Creates the main menu keyboard.
    If is_admin is True, adds an 'Admin Panel' button.
    """
    keyboard = [
        [KeyboardButton(BUTTON_TEXTS["services"]), KeyboardButton(BUTTON_TEXTS["wallet"])],
        [KeyboardButton(BUTTON_TEXTS["my_services"]), KeyboardButton(BUTTON_TEXTS["support"])],
        [KeyboardButton(BUTTON_TEXTS["referral"]), KeyboardButton(BUTTON_TEXTS["rules"])],
    ]
    if is_admin:
        # Add the admin panel button for the admin user
        keyboard.append([KeyboardButton(BUTTON_TEXTS["admin_panel"])])
        
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_services_menu_keyboard():
    """Creates the services menu keyboard."""
    keyboard = [
        [KeyboardButton(BUTTON_TEXTS["purchase_service"]), KeyboardButton(BUTTON_TEXTS["trial_service"])],
        [KeyboardButton(BUTTON_TEXTS["back"])]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_admin_menu_keyboard():
    """Creates the admin-specific menu keyboard."""
    keyboard = [
        [KeyboardButton(BUTTON_TEXTS["user_management"]), KeyboardButton(BUTTON_TEXTS["statistics"])],
        [KeyboardButton(BUTTON_TEXTS["broadcast"])],
        [KeyboardButton(BUTTON_TEXTS["back_to_user_menu"])]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def create_back_keyboard():
    """Creates a simple keyboard with only a back button."""
    return ReplyKeyboardMarkup([[KeyboardButton(BUTTON_TEXTS["back"])]], resize_keyboard=True)
    
# --- Conversation States ---
# Define states for conversation handlers
SELECTING_ACTION, TYPING_WALLET_AMOUNT, SELECTING_ADMIN_ACTION = range(3)
