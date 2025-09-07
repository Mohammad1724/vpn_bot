# filename: config.py
# -*- coding: utf-8 -*-

# ===============================================================
# TELEGRAM BOT CONFIGURATION
# ===============================================================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # توکن ربات خود را اینجا قرار بده
ADMIN_ID = 8011293838              # آیدی ادمین
SUPPORT_USERNAME = "Farsnetadmin"  # یوزرنیم پشتیبانی

# ===============================================================
# HIDDIFY PANEL CONFIGURATION
# ===============================================================
# دامنه اصلی پنل شما
PANEL_DOMAIN = "admin33.iranshop21.monster"

# مسیر ادمین پنل (برای API v2)
ADMIN_PATH = "UA3jz9Ii21F7IHIxm5"

# مسیر کلاینت (مسیر اشتراک) - معمولاً 'sub' است
SUB_PATH = "sub"

# کلید API پنل (از تنظیمات پنل هیدیفای بردار)
API_KEY = "YOUR_HIDDIFY_API_KEY_HERE"

# ساب‌دامین‌های اشتراک (اختیاری)
SUB_DOMAINS = ["mrmu3.iranshop21.monster"]

# ===============================================================
# EXPANDED API CONFIGURATION (بسیار مهم برای تمدید)
# ===============================================================
# این مقدار را با سکرت UUID پنل خود جایگزین کن
# این همان بخشی است که در URL پنل شما وجود دارد
# مثال: blWv7lnshWJWrnsK5eAX0pPe6
PANEL_SECRET_UUID = "blWv7lnshWJWrnsK5eAX0pPe6"

# اگر گواهی SSL پنل شما Self-signed است، این را False بگذارید
HIDDIFY_API_VERIFY_SSL = True

# ===============================================================
# MULTI-NODE & SUBCONVERTER (فعلاً غیرفعال)
# ===============================================================
MULTI_SERVER_ENABLED = False
SUBCONVERTER_ENABLED = False
SERVERS = []
DEFAULT_SERVER_NAME = "Main"
SERVER_SELECTION_POLICY = "first"
SUBCONVERTER_URL = ""
SUBCONVERTER_DEFAULT_TARGET = "v2ray"
SUBCONVERTER_EXTRA_SERVERS = []

# ... (بقیه تنظیمات مثل قبل باقی بمانند)
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