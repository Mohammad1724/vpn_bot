# filename: config.py
# -*- coding: utf-8 -*-

# ===============================================================
# TELEGRAM BOT CONFIGURATION
# ===============================================================
BOT_TOKEN = "CHANGE_ME_BOT_TOKEN"
ADMIN_ID = 123456789  # عدد تلگرام ادمین
SUPPORT_USERNAME = "CHANGE_ME_SUPPORT_USERNAME"

# ===============================================================
# HIDDIFY PANEL CONFIGURATION (Single-Server defaults)
# ===============================================================
# دامنه پنل/سابسکریپشن اصلی
PANEL_DOMAIN = "mrmu3.iranshop21.monster"  # دامنه واقعی‌ات
# مسیر ادمین پنل (همون که لینک قبلی‌ت داشت، فقط برای API استفاده میشه)
ADMIN_PATH = "blWv7lnshWJWrnsK5eAX0pPe6"
# مسیر اشتراک؛ حتماً مسیر «sub» یا مسیر اشتراک واقعی‌ت رو بزن، نه admin_path
SUB_PATH = "sub"
# کلید API پنل اصلی
API_KEY = "CHANGE_ME_HIDDIFY_API_KEY"
# ساب‌دامین‌های اشتراک (اختیاری). اگر نداری خالی بذار یا همین دامنه اصلی رو بده
SUB_DOMAINS = [
    "mrmu3.iranshop21.monster",
]

# ===============================================================
# MULTI-SERVER (NODES) CONFIGURATION
# اگر نودها رو از داخل پنل ادمین ربات تعریف کرده‌ای، همین False بمونه.
# اگر نودها رو اینجا مدیریت می‌کنی، True کن و لیست SERVERS رو تکمیل کن.
# ===============================================================
MULTI_SERVER_ENABLED = False

# لیست نودها (فقط اگر MULTI_SERVER_ENABLED=True و DB خالی باشد استفاده می‌شود)
SERVERS = [
    {
        "name": "mrmu3",  # باید با server_name دیتابیس یکی باشد
        "panel_domain": "mrmu3.iranshop21.monster",
        "admin_path": ADMIN_PATH,
        "sub_path": SUB_PATH,  # فقط مسیر sub؛ نه admin_path
        "api_key": API_KEY,
        "sub_domains": SUB_DOMAINS,
    },
    # نود دوم نمونه (در صورت نیاز باز کن و مقادیرش را پر کن)
    # {
    #     "name": "node2",
    #     "panel_domain": "CHANGE_ME_NODE2_DOMAIN",
    #     "admin_path": "CHANGE_ME_NODE2_ADMIN_PATH",
    #     "sub_path": "sub",
    #     "api_key": "CHANGE_ME_NODE2_API_KEY",
    #     "sub_domains": ["CHANGE_ME_NODE2_SUB_DOMAIN"],
    # },
]

# انتخاب نود پیش‌فرض برای ساخت سرویس جدید
DEFAULT_SERVER_NAME = "mrmu3"
SERVER_SELECTION_POLICY = "least_loaded"  # first | by_name | least_loaded

# ===============================================================
# USAGE AGGREGATION ACROSS SERVERS (per user)
# ===============================================================
USAGE_AGGREGATION_ENABLED = False
USAGE_UPDATE_INTERVAL_MIN = 10  # minutes

# ===============================================================
# NODE HEALTH-CHECK
# ===============================================================
NODES_HEALTH_ENABLED = True
NODES_HEALTH_INTERVAL_MIN = 10
NODES_AUTO_DISABLE_AFTER_FAILS = 3

# ===============================================================
# SUBCONVERTER (Unified subscription link for multiple panels)
# برای ادغام لینک‌های چند نود، باید یک ساب‌کانورتر پابلیک داشته باشی
# docker run -d --name subconverter -p 25500:25500 tindy2013/subconverter:latest
# و حتماً SUBCONVERTER_URL را روی دامنه/آی‌پی پابلیک ست کنی (نه 127.0.0.1)
# ===============================================================
SUBCONVERTER_ENABLED = True
SUBCONVERTER_URL = "https://CHANGE_ME_PUBLIC_HOST:25500"  # مثل: https://subconv.yourdomain.com:25500
SUBCONVERTER_DEFAULT_TARGET = "v2ray"  # v2ray | clash | clashmeta | singbox | sub
# در صورتی که می‌خواهی هنگام ایجاد سرویس، روی نودهای اضافه هم پرویژن شود
SUBCONVERTER_EXTRA_SERVERS = [
    # "mrmu3",
    # "node2",
]

# ===============================================================
# FREE TRIAL SERVICE CONFIGURATION
# ===============================================================
TRIAL_ENABLED = True
TRIAL_DAYS = 1
TRIAL_GB = 1

# ===============================================================
# REFERRAL & REMINDERS CONFIGURATION
# ===============================================================
REFERRAL_BONUS_AMOUNT = 5000
EXPIRY_REMINDER_DAYS = 3

# ===============================================================
# USAGE & DEVICE LIMITS CONFIGURATION
# ===============================================================
USAGE_ALERT_THRESHOLD = 0.8
DEVICE_LIMIT_ALERT_ENABLED = True