# -*- coding: utf-8 -*-

# ===============================================================
# TELEGRAM BOT CONFIGURATION
# ===============================================================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 123456789
SUPPORT_USERNAME = "your_support_username"

# ===============================================================
# HIDDIFY PANEL CONFIGURATION (Single-Server defaults)
# ===============================================================
PANEL_DOMAIN = "your_panel_domain.com"
ADMIN_PATH = "your_admin_secret_path"
SUB_PATH = "your_subscription_secret_path"
API_KEY = "your_hiddify_api_key_here"
SUB_DOMAINS = []

# ===============================================================
# MULTI-SERVER (NODES) CONFIGURATION
# Enable if you manage multiple Hiddify panels/nodes.
# If disabled, the bot uses the single-server configs above.
# ===============================================================
MULTI_SERVER_ENABLED = False

# List of servers. If enabled, the bot uses these for API calls and link building.
# Keep 'name' unique per server.
SERVERS = [
    {
        "name": "Main",
        "panel_domain": PANEL_DOMAIN,
        "admin_path": ADMIN_PATH,
        "sub_path": SUB_PATH,
        "api_key": API_KEY,
        "sub_domains": SUB_DOMAINS,  # e.g., ["sub1.example.com", "sub2.example.com"]
    },
    # {
    #     "name": "Node-2",
    #     "panel_domain": "panel2.example.com",
    #     "admin_path": "admin2",
    #     "sub_path": "sub2",
    #     "api_key": "api_key_2",
    #     "sub_domains": ["sub3.example.com"],
    # },
]

# Default server selection policy for creating new users/services
DEFAULT_SERVER_NAME = "Main"   # server name from SERVERS
SERVER_SELECTION_POLICY = "first"  # first | by_name

# Aggregation of usage across servers (per user)
USAGE_AGGREGATION_ENABLED = False
USAGE_UPDATE_INTERVAL_MIN = 10  # minutes

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
# Enable or disable the job that warns users when they reach their device limit.
DEVICE_LIMIT_ALERT_ENABLED = True