# filename: constants.py
# -*- coding: utf-8 -*-

# Commands
CMD_CANCEL = "/cancel"
CMD_SKIP = "/skip"
CMD_DONE = "/done"

# Buttons
BTN_ADMIN_PANEL = "👑 پنل ادمین"
BTN_EXIT_ADMIN_PANEL = "🚪 خروج از پنل ادمین"
BTN_BACK_TO_ADMIN_MENU = "⬅️ بازگشت به پنل ادمین"

# General Conversation States
(
    GET_CUSTOM_NAME,
    REDEEM_GIFT,
    SUPPORT_TICKET_OPEN,
    PROMO_CODE_ENTRY,
) = range(4)

# Charge Conversation States
(
    CHARGE_MENU,
    CHARGE_AMOUNT,
    CHARGE_RECEIPT,
    AWAIT_CUSTOM_AMOUNT,
) = range(100, 104)

# Account Actions Conversation States
(
    TRANSFER_RECIPIENT_ID,
    TRANSFER_AMOUNT,
    TRANSFER_CONFIRM,
    GIFT_FROM_BALANCE_AMOUNT,
    GIFT_FROM_BALANCE_CONFIRM,
) = range(200, 205)

# Admin Conversation States (Top Level)
(
    ADMIN_MENU,
    PLAN_MENU,
    REPORTS_MENU,
    BACKUP_MENU,
    RESTORE_UPLOAD,
    USER_MANAGEMENT_MENU,
    MANAGE_USER_AMOUNT,
    GIFT_CODES_MENU,
    ADMIN_SETTINGS_MENU,
    AWAIT_SETTING_VALUE,
) = range(300, 310)

# Plan Management States
(
    PLAN_NAME,
    PLAN_PRICE,
    PLAN_DAYS,
    PLAN_GB,
    PLAN_CATEGORY,
    EDIT_PLAN_NAME,
    EDIT_PLAN_PRICE,
    EDIT_PLAN_DAYS,
    EDIT_PLAN_GB,
    EDIT_PLAN_CATEGORY,
) = range(400, 410)

# Promo Code Creation States
(
    PROMO_GET_CODE,
    PROMO_GET_PERCENT,
    PROMO_GET_MAX_USES,
    PROMO_GET_EXPIRES,
    PROMO_GET_FIRST_PURCHASE,
) = range(500, 505)

# Referral Bonus State
AWAIT_REFERRAL_BONUS = 600

# Broadcast States
(
    BROADCAST_MENU,
    BROADCAST_MESSAGE,
    BROADCAST_CONFIRM,
    BROADCAST_TO_USER_ID,
    BROADCAST_TO_USER_MESSAGE,
) = range(700, 705)

# توجه: Stateهای مدیریت نود حذف شدند تا وابستگی به نودها به‌طور کامل از ربات حذف شود.