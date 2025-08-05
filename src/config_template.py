# src/config.py

# --- Telegram Bot Configuration ---
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 0 

# --- Hiddify Panel Configuration ---
PANEL_DOMAIN = "testbot.iranshop21.ir" # دامنه اصلی پنل شما
ADMIN_PATH = "4kVbuy9ijjUXnulKLP" # مسیر مخفی پنل شما
API_KEY = "YOUR_HIDDIFY_API_KEY_HERE"

# --- Subscription Link Configuration ---
# <<<< این بخش تغییر کرده است >>>>
# لیستی از دامنه‌های ورکر/CDN که می‌خواهید برای لینک اشتراک استفاده شوند.
# دامنه‌ها را داخل "" و با ویرگول از هم جدا کنید.
# ربات به صورت تصادفی یکی از این دامنه‌ها را انتخاب می‌کند.
# اگر این لیست خالی باشد، از دامنه اصلی پنل (PANEL_DOMAIN) استفاده می‌شود.
SUB_DOMAINS = [
    "usertestbot.iranshop21.ir",
    "sub2.yourdomain.com",
    "sub3.yourdomain.com"
]

# --- Other Settings ---
SUPPORT_USERNAME = "YOUR_SUPPORT_USERNAME"