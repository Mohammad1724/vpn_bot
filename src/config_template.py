# -*- coding: utf-8 -*-

# ===============================================================
# TELEGRAM BOT CONFIGURATION
# ===============================================================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 123456789
SUPPORT_USERNAME = "your_support_username"

# ===============================================================
# HIDDIFY PANEL CONFIGURATION
# ===============================================================
PANEL_DOMAIN = "your_panel_domain.com"
ADMIN_PATH = "your_admin_secret_path"
SUB_PATH = "your_subscription_secret_path"
API_KEY = "your_hiddify_api_key_here"

# Optional list of subscription domains. If empty, PANEL_DOMAIN will be used.
# Example: ["sub1.example.com", "sub2.example.com"]
SUB_DOMAINS = []

# ===============================================================
# FREE TRIAL SERVICE CONFIGURATION
# ===============================================================
TRIAL_ENABLED = True
TRIAL_DAYS = 1
TRIAL_GB = 1

# ===============================================================
# REFERRAL & REMINDERS CONFIGURATION
# ===============================================================
# Bonus amount (Toman) for both referrer and new user after the first purchase
REFERRAL_BONUS_AMOUNT = 5000

# Days before expiry to send reminder
EXPIRY_REMINDER_DAYS = 3

# ===============================================================
# USAGE ALERT CONFIGURATION
# ===============================================================
# Send a low-usage alert when (current_usage_GB / usage_limit_GB) >= threshold (0.0 - 1.0)
USAGE_ALERT_THRESHOLD = 0.8
