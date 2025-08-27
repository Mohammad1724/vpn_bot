# -*- coding: utf-8 -*-

# ===============================================================
# TELEGRAM BOT CONFIGURATION
# ===============================================================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 123456789
SUPPORT_USERNAME = "your_support_username"

# ===============================================================
# HIDDIFY PANEL CONFIGURATION (Single-Server defaults)
# Used if MULTI_SERVER_ENABLED is False and no nodes are defined in DB.
# ===============================================================
PANEL_DOMAIN = "your_panel_domain.com"
ADMIN_PATH = "your_admin_secret_path"
SUB_PATH = "your_subscription_secret_path"
API_KEY = "your_hiddify_api_key_here"
SUB_DOMAINS = []  # e.g., ["sub1.example.com", "sub2.example.com"]

# ===============================================================
# MULTI-SERVER (NODES) CONFIGURATION
# If disabled, the bot falls back to single-server settings above.
# If enabled (and DB nodes are empty), the bot uses SERVERS below.
# Note: If you add nodes from Admin Panel, those DB nodes take precedence.
# ===============================================================
MULTI_SERVER_ENABLED = False

# List of servers. Keep 'name' unique per server.
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
# first: pick the first active node
# by_name: use DEFAULT_SERVER_NAME
# least_loaded: pick the node with most free capacity (recommended)
DEFAULT_SERVER_NAME = "Main"   # server name from SERVERS
SERVER_SELECTION_POLICY = "least_loaded"  # first | by_name | least_loaded

# ===============================================================
# USAGE AGGREGATION ACROSS SERVERS (per user)
# The JobQueue periodically fetches usage and stores snapshots in DB.
# Interval can be edited later from Admin > Settings.
# ===============================================================
USAGE_AGGREGATION_ENABLED = False
USAGE_UPDATE_INTERVAL_MIN = 10  # minutes

# ===============================================================
# NODE HEALTH-CHECK (for DB/config servers)
# Periodically checks API connectivity and updates current_users per node.
# Auto-disable will set node is_active=0 after consecutive failures.
# Intervals and toggles can be edited later from Admin > Settings.
# ===============================================================
NODES_HEALTH_ENABLED = True
NODES_HEALTH_INTERVAL_MIN = 10
NODES_AUTO_DISABLE_AFTER_FAILS = 3

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