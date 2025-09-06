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
# دامنه و مسیرها (توجه: مسیر اشتراک باید sub باشد، نه admin)
PANEL_DOMAIN = "mrmu3.iranshop21.monster"
ADMIN_PATH = "blWv7lnshWJWrnsK5eAX0pPe6"  # فقط برای API پنل
SUB_PATH = "sub"  # مسیر اشتراک
API_KEY = "CHANGE_ME_HIDDIFY_API_KEY"

# ساب‌دامین‌های اشتراک (یک‌خطه تا خطای ایندنت نگیری)
SUB_DOMAINS = ["mrmu3.iranshop21.monster"]

# ===============================================================
# MULTI-SERVER (NODES) CONFIGURATION
# اگر نودها را از داخل پنل ربات تعریف کرده‌ای، این را False بگذار.
# اگر نودها را در همین فایل مدیریت می‌کنی، True کن و SERVERS را پر کن.
# ===============================================================
MULTI_SERVER_ENABLED = False

# لیست نودها (فقط در صورت MULTI_SERVER_ENABLED=True و خالی بودن DB استفاده می‌شود)
SERVERS = [
    {
        "name": "Main",
        "panel_domain": PANEL_DOMAIN,
        "admin_path": ADMIN_PATH,
        "sub_path": SUB_PATH,        # فقط مسیر sub؛ نه admin_path
        "api_key": API_KEY,
        "sub_domains": SUB_DOMAINS,  # مثل ["sub1.example.com", "sub2.example.com"]
    },
    # مثال نود دوم (در صورت نیاز باز کن و تکمیل کن)
    # {
    #     "name": "Node-2",
    #     "panel_domain": "CHANGE_ME_NODE2_DOMAIN",
    #     "admin_path": "CHANGE_ME_NODE2_ADMIN_PATH",
    #     "sub_path": "sub",
    #     "api_key": "CHANGE_ME_NODE2_API_KEY",
    #     "sub_domains": ["CHANGE_ME_NODE2_SUB_DOMAIN"],
    # },
]

# انتخاب نود پیش‌فرض برای ساخت سرویس جدید
DEFAULT_SERVER_NAME = "Main"
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
# برای ادغام چند نود باید Subconverter پابلیک داشته باشی.
# مثال داکر: docker run -d -p 25500:25500 tindy2013/subconverter:latest
# توجه: آدرس باید از سمت کاربر قابل دسترس باشد (نه 127.0.0.1)
# ===============================================================
SUBCONVERTER_ENABLED = True
SUBCONVERTER_URL = "https://CHANGE_ME_SUBCONVERTER_HOST:25500"  # مثل: https://subconv.yourdomain.com:25500
SUBCONVERTER_DEFAULT_TARGET = "v2ray"  # v2ray | clash | clashmeta | singbox | sub
SUBCONVERTER_EXTRA_SERVERS = []  # اگر نمی‌خوای provisioning اضافی داشته باشی خالی بگذار

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