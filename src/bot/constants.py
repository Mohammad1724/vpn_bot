# -*- coding: utf-8 -*-

# Buttons and commands
BTN_ADMIN_PANEL = "👑 ورود به پنل ادمین"
BTN_EXIT_ADMIN_PANEL = "↩️ خروج از پنل"
BTN_BACK_TO_ADMIN_MENU = "بازگشت به منوی ادمین"
BTN_MANAGE_NODES = "🖧 مدیریت نودها"  # جدید: دکمه مدیریت نودها
CMD_CANCEL = "/cancel"
CMD_SKIP = "/skip"

# Main conversation states (existing)
(
    ADMIN_MENU, PLAN_MENU, REPORTS_MENU, USER_MANAGEMENT_MENU, PLAN_NAME,
    PLAN_PRICE, PLAN_DAYS, PLAN_GB, PLAN_CATEGORY,
    EDIT_PLAN_NAME, EDIT_PLAN_PRICE, EDIT_PLAN_DAYS, EDIT_PLAN_GB, EDIT_PLAN_CATEGORY,
    MANAGE_USER_ID, MANAGE_USER_ACTION, MANAGE_USER_AMOUNT, GET_CUSTOM_NAME,
    REDEEM_GIFT, CHARGE_AMOUNT, CHARGE_RECEIPT, SETTINGS_MENU, BACKUP_MENU,
    BROADCAST_MENU, BROADCAST_MESSAGE, BROADCAST_CONFIRM, BROADCAST_TO_USER_ID,
    BROADCAST_TO_USER_MESSAGE, RESTORE_UPLOAD, AWAIT_SETTING_VALUE,
    # Account actions
    TRANSFER_RECIPIENT_ID, TRANSFER_AMOUNT, TRANSFER_CONFIRM,
    GIFT_FROM_BALANCE_AMOUNT, GIFT_FROM_BALANCE_CONFIRM,
    # Support ticket
    SUPPORT_TICKET_OPEN,
    # Admin manage user's services
    MANAGE_SERVICE_ACTION
) = range(37)

# Additional menus/states (existing)
ADMIN_SETTINGS_MENU = 100
GIFT_CODES_MENU = 101
PROMO_CODE_ENTRY = 102
AWAIT_REFERRAL_BONUS = 104

# Admin Promo Code creation (existing)
(
    PROMO_GET_CODE, PROMO_GET_PERCENT, PROMO_GET_MAX_USES,
    PROMO_GET_EXPIRES, PROMO_GET_FIRST_PURCHASE
) = range(300, 305)

# ======================
# Nodes management states (NEW)
# ======================
# We use a high, separate range to avoid collisions with existing states.
(
    NODES_MENU,           # منوی اصلی مدیریت نودها
    NODE_ADD_NAME,        # دریافت نام نود
    NODE_ADD_API_BASE,    # دریافت API Base (https://host/ADMIN_PATH/ADMIN_UUID/api/v1)
    NODE_ADD_SUB_PREFIX,  # دریافت sub_prefix (https://host/SUB_SECRET) یا '-'
    NODE_ADD_API_KEY,     # دریافت API Key یا '-'
    NODE_DELETE_ID,       # دریافت ID برای حذف نود
    NODE_TOGGLE_ID        # دریافت ID برای تغییر وضعیت فعال/غیرفعال
) = range(600, 607)