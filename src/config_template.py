# -*- coding: utf-8 -*-

# ===============================================================
# TELEGRAM BOT CONFIGURATION
# ===============================================================
# Telegram Bot Token from @BotFather
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Your numeric Telegram User ID. You can get it from @userinfobot
ADMIN_ID = 123456789

# Your support username (without the @)
SUPPORT_USERNAME = "your_support_username"

# ===============================================================
# HIDDIFY PANEL CONFIGURATION
# ===============================================================
# Your Hiddify panel domain (e.g., "panel.example.com")
PANEL_DOMAIN = "your_panel_domain.com"

# The secret path for your admin panel (e.g., "abcdef123456")
ADMIN_PATH = "your_admin_secret_path"

# The secret path for subscription links (can be the same as ADMIN_PATH)
SUB_PATH = "your_subscription_secret_path"

# Your Hiddify API Key, found in the admin panel settings
API_KEY = "your_hiddify_api_key_here"

# A list of domains to be used for generating subscription links.
# The bot will randomly choose one. If empty, PANEL_DOMAIN will be used.
# Example: ["sub1.example.com", "sub2.example.com"]
SUB_DOMAINS = []

# ===============================================================
# FREE TRIAL SERVICE CONFIGURATION
# ===============================================================
# Enable or disable the free trial feature
TRIAL_ENABLED = True

# Duration of the trial service in days
TRIAL_DAYS = 1

# Data limit for the trial service in GB
TRIAL_GB = 1

# ===============================================================
# NEW: REFERRAL SYSTEM & EXPIRY REMINDER CONFIGURATION
# ===============================================================

# --- Referral System Settings ---
# The bonus amount (in Toman) given to both the referrer and the new user upon the first purchase.
REFERRAL_BONUS_AMOUNT = 5000

# --- Expiry Reminder Settings ---
# The bot will send a reminder message to users whose services will expire in exactly this many days.
EXPIRY_REMINDER_DAYS = 3