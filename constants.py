# -*- coding: utf-8 -*-

from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

(
    MAIN_MENU_KEYBOARD,
    ADMIN_MENU_KEYBOARD,
    SERVICES_KEYBOARD,
    PURCHASE_SERVICE_KEYBOARD,
    MY_SERVICES_KEYBOARD,
    TRIAL_SERVICE_KEYBOARD,
    WALLET_KEYBOARD,
    INCREASE_WALLET_KEYBOARD,
    SUPPORT_KEYBOARD,
    REFERRAL_KEYBOARD,
    RULES_KEYBOARD,
    BACK_TO_MAIN_MENU_KEYBOARD,
    BACK_TO_ADMIN_MENU_KEYBOARD,
    BACK_TO_SERVICES_KEYBOARD,
    BACK_TO_MY_SERVICES_KEYBOARD,
    BACK_TO_WALLET_KEYBOARD,
    MAIN_MENU_BUTTON,
    ADMIN_MENU_BUTTON,
    SERVICES_BUTTON,
    PURCHASE_SERVICE_BUTTON,
    MY_SERVICES_BUTTON,
    TRIAL_SERVICE_BUTTON,
    WALLET_BUTTON,
    INCREASE_WALLET_BUTTON,
    SUPPORT_BUTTON,
    REFERRAL_BUTTON,
    RULES_BUTTON,
    ZARINPAL_BUTTON,
    BACK_BUTTON,
    CANCEL_BUTTON,
) = (
    "main_menu_keyboard",
    "admin_menu_keyboard",
    "services_keyboard",
    "purchase_service_keyboard",
    "my_services_keyboard",
    "trial_service_keyboard",
    "wallet_keyboard",
    "increase_wallet_keyboard",
    "support_keyboard",
    "referral_keyboard",
    "rules_keyboard",
    "back_to_main_menu_keyboard",
    "back_to_admin_menu_keyboard",
    "back_to_services_keyboard",
    "back_to_my_services_keyboard",
    "back_to_wallet_keyboard",
    "main_menu_button",
    "admin_menu_button",
    "services_button",
    "purchase_service_button",
    "my_services_button",
    "trial_service_button",
    "wallet_button",
    "increase_wallet_button",
    "support_button",
    "referral_button",
    "rules_button",
    "zarinpal_button",
    "back_button",
    "cancel_button",
)


def create_keyboards():
    # --- دکمه‌ها با متن فارسی ---
    main_menu_button = KeyboardButton("منوی اصلی")
    admin_menu_button = KeyboardButton("پنل ادمین")
    services_button = KeyboardButton("سرویس‌ها 🛍️")
    purchase_service_button = KeyboardButton("خرید سرویس")
    my_services_button = KeyboardButton("سرویس‌های من 👤")
    trial_service_button = KeyboardButton("تست رایگان 🎁")
    wallet_button = KeyboardButton("کیف پول 💳")
    increase_wallet_button = KeyboardButton("افزایش موجودی")
    support_button = KeyboardButton("پشتیبانی 📞")
    referral_button = KeyboardButton("معرفی دوستان 👥")
    rules_button = KeyboardButton("قوانین 📜")
    back_button = KeyboardButton(" بازگشت ➡️")
    cancel_button = KeyboardButton("لغو ❌")
    zarinpal_button = KeyboardButton("پرداخت با زرین‌پال")

    # Keyboards
    main_menu_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    main_menu_keyboard.add(
        services_button,
        wallet_button,
        my_services_button,
        support_button,
        referral_button,
        rules_button,
    )

    admin_menu_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    admin_menu_keyboard.add(back_button)

    services_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    services_keyboard.add(
        purchase_service_button, trial_service_button, back_button
    )

    purchase_service_keyboard = ReplyKeyboardMarkup(
        row_width=2, resize_keyboard=True
    )
    purchase_service_keyboard.add(back_button)

    my_services_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    my_services_keyboard.add(back_button)

    trial_service_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    trial_service_keyboard.add(back_button)

    wallet_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    wallet_keyboard.add(increase_wallet_button, back_button)

    increase_wallet_keyboard = ReplyKeyboardMarkup(
        row_width=2, resize_keyboard=True
    )
    increase_wallet_keyboard.add(zarinpal_button, back_button)

    support_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    support_keyboard.add(back_button)

    referral_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    referral_keyboard.add(back_button)

    rules_keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    rules_keyboard.add(back_button)

    back_to_main_menu_keyboard = ReplyKeyboardMarkup(
        row_width=1, resize_keyboard=True
    )
    back_to_main_menu_keyboard.add(back_button)

    back_to_admin_menu_keyboard = ReplyKeyboardMarkup(
        row_width=1, resize_keyboard=True
    )
    back_to_admin_menu_keyboard.add(back_button)

    back_to_services_keyboard = ReplyKeyboardMarkup(
        row_width=1, resize_keyboard=True
    )
    back_to_services_keyboard.add(back_button)

    back_to_my_services_keyboard = ReplyKeyboardMarkup(
        row_width=1, resize_keyboard=True
    )
    back_to_my_services_keyboard.add(back_button)

    back_to_wallet_keyboard = ReplyKeyboardMarkup(
        row_width=1, resize_keyboard=True
    )
    back_to_wallet_keyboard.add(back_button)

    return (
        # Keyboards
        main_menu_keyboard,
        admin_menu_keyboard,
        services_keyboard,
        purchase_service_keyboard,
        my_services_keyboard,
        trial_service_keyboard,
        wallet_keyboard,
        increase_wallet_keyboard,
        support_keyboard,
        referral_keyboard,
        rules_keyboard,
        back_to_main_menu_keyboard,
        back_to_admin_menu_keyboard,
        back_to_services_keyboard,
        back_to_my_services_keyboard,
        back_to_wallet_keyboard,
        # Buttons
        main_menu_button,
        admin_menu_button,
        services_button,
        purchase_service_button,
        my_services_button,
        trial_service_button,
        wallet_button,
        increase_wallet_button,
        support_button,
        referral_button,
        rules_button,
        zarinpal_button,
        back_button,
        cancel_button,
    )


(
    MAIN_MENU_KEYBOARD,
    ADMIN_MENU_KEYBOARD,
    SERVICES_KEYBOARD,
    PURCHASE_SERVICE_KEYBOARD,
    MY_SERVICES_KEYBOARD,
    TRIAL_SERVICE_KEYBOARD,
    WALLET_KEYBOARD,
    INCREASE_WALLET_KEYBOARD,
    SUPPORT_KEYBOARD,
    REFERRAL_KEYBOARD,
    RULES_KEYBOARD,
    BACK_TO_MAIN_MENU_KEYBOARD,
    BACK_TO_ADMIN_MENU_KEYBOARD,
    BACK_TO_SERVICES_KEYBOARD,
    BACK_TO_MY_SERVICES_KEYBOARD,
    BACK_TO_WALLET_KEYBOARD,
    MAIN_MENU_BUTTON,
    ADMIN_MENU_BUTTON,
    SERVICES_BUTTON,
    PURCHASE_SERVICE_BUTTON,
    MY_SERVICES_BUTTON,
    TRIAL_SERVICE_BUTTON,
    WALLET_BUTTON,
    INCREASE_WALLET_BUTTON,
    SUPPORT_BUTTON,
    REFERRAL_BUTTON,
    RULES_BUTTON,
    ZARINPAL_BUTTON,
    BACK_BUTTON,
    CANCEL_BUTTON,
) = create_keyboards()