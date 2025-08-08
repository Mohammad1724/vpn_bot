# -*- coding: utf-8 -*-

# --- Bot Buttons & Commands ---
BTN_ADMIN_PANEL = "👑 ورود به پنل ادمین"
BTN_EXIT_ADMIN_PANEL = "↩️ خروج از پنل"
BTN_BACK_TO_ADMIN_MENU = "بازگشت به منوی ادمین"
CMD_CANCEL = "/cancel"
CMD_SKIP = "/skip"

# --- Conversation States ---
(
    # Admin States
    ADMIN_MENU, PLAN_MENU, REPORTS_MENU, USER_MANAGEMENT_MENU, PLAN_NAME,
    PLAN_PRICE, PLAN_DAYS, PLAN_GB, EDIT_PLAN_NAME, EDIT_PLAN_PRICE,
    EDIT_PLAN_DAYS, EDIT_PLAN_GB, MANAGE_USER_ID, MANAGE_USER_ACTION,
    MANAGE_USER_AMOUNT, SETTINGS_MENU, BACKUP_MENU, BROADCAST_MENU,
    BROADCAST_MESSAGE, BROADCAST_CONFIRM, BROADCAST_TO_USER_ID,
    BROADCAST_TO_USER_MESSAGE, RESTORE_UPLOAD, AWAIT_SETTING_VALUE,
    EDIT_GUIDE_TEXT,

    # User States
    GET_CUSTOM_NAME, REDEEM_GIFT, CHARGE_AMOUNT, CHARGE_RECEIPT

) = range(31)

# --- Callback Data Prefixes ---
# Using prefixes makes callback data more readable and manageable
CALLBACK_ADMIN_CONFIRM_CHARGE = "admin_confirm_charge_"
CALLBACK_ADMIN_REJECT_CHARGE = "admin_reject_charge_"
CALLBACK_USER_BUY_PLAN = "user_buy_"
CALLBACK_SHOW_SERVICE = "show_service_management_"
CALLBACK_RENEW_SERVICE = "renew_"
CALLBACK_GET_LINK = "getlink_"
# ... and so on for other callbacks
