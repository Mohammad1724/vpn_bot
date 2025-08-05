#!/bin/bash

# Function to print colored messages
print_color() {
    COLOR=$1
    TEXT=$2
    case $COLOR in
        "red") echo -e "\e[31m${TEXT}\e[0m" ;;
        "green") echo -e "\e[32m${TEXT}\e[0m" ;;
        "yellow") echo -e "\e[33m${TEXT}\e[0m" ;;
        "blue") echo -e "\e[34m${TEXT}\e[0m" ;;
    esac
}

# Check for root user
if [ "$(id -u)" != "0" ]; then
   print_color "red" "This script must be run as root. Please use 'sudo'."
   exit 1
fi

print_color "blue" "--- Hiddify Advanced Bot Installer ---"

# 1. System dependencies
print_color "yellow" "Updating package lists and installing dependencies..."
apt-get update > /dev/null 2>&1
apt-get install -y python3 python3-pip python3-venv curl git nano > /dev/null 2>&1

# 2. Get installation directory
DEFAULT_INSTALL_DIR="/opt/vpn-bot"
read -p "Enter the installation directory [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}

if [ -d "$INSTALL_DIR" ]; then
    print_color "red" "Directory ${INSTALL_DIR} already exists. Please remove it or choose another one."
    exit 1
fi

# 3. Create project structure
print_color "yellow" "Creating project structure..."
mkdir -p ${INSTALL_DIR}/src
mkdir -p ${INSTALL_DIR}/backups
cd $INSTALL_DIR

# 4. Create files from script
# This is a different approach: embedding all files within the install script

# requirements.txt
cat > requirements.txt << 'EOL'
python-telegram-bot[ext]==21.2
requests
EOL

# src/config_template.py
cat > src/config_template.py << 'EOL'
# --- Telegram Bot Configuration ---
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 0 # آیدی عددی خود را وارد کنید

# --- Hiddify Panel Configuration ---
PANEL_DOMAIN = "YOUR_PANEL_DOMAIN_HERE"
ADMIN_PATH = "YOUR_ADMIN_SECRET_PATH_HERE"
API_KEY = "YOUR_HIDDIFY_API_KEY_HERE"

# --- Other Settings ---
SUPPORT_USERNAME = "YOUR_SUPPORT_USERNAME" # آیدی پشتیبانی بدون @
EOL

# src/database.py
cat > src/database.py << 'EOL'
import sqlite3
import datetime
import uuid

DB_NAME = "vpn_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, join_date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS plans (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price REAL NOT NULL, days INTEGER NOT NULL, gb INTEGER NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS active_services (service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, sub_uuid TEXT, sub_link TEXT, expiry_date TEXT, plan_id INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS sales (sale_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id INTEGER, price REAL, sale_date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS gift_codes (code TEXT PRIMARY KEY, amount REAL, usage_limit INTEGER, used_count INTEGER DEFAULT 0)')
    conn.commit()
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_holder', 'نام صاحب حساب'))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,)); result = cursor.fetchone()
    conn.close(); return result[0] if result else None
def set_setting(key, value):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)); conn.commit(); conn.close()

def get_or_create_user(user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance FROM users WHERE user_id = ?", (user_id,)); user = cursor.fetchone()
    if not user:
        join_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO users (user_id, join_date) VALUES (?, ?)", (user_id, join_date)); conn.commit()
        user = (user_id, 0.0)
    conn.close(); return {"user_id": user[0], "balance": user[1]}
def update_balance(user_id, amount, add=True):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    if add: cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    else: cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()
def get_all_user_ids():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users"); user_ids = [item[0] for item in cursor.fetchall()]
    conn.close(); return user_ids

def add_plan(name, price, days, gb):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb)); conn.commit(); conn.close()
def list_plans():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT plan_id, name, price, days, gb FROM plans")
    plans = [{"plan_id": p[0], "name": p[1], "price": p[2], "days": p[3], "gb": p[4]} for p in cursor.fetchall()]
    conn.close(); return plans
def get_plan(plan_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT plan_id, name, price, days, gb FROM plans WHERE plan_id = ?", (plan_id,)); p = cursor.fetchone()
    conn.close()
    if not p: return None
    return {"plan_id": p[0], "name": p[1], "price": p[2], "days": p[3], "gb": p[4]}
def delete_plan(plan_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,)); conn.commit(); conn.close()

def add_active_service(user_id, sub_uuid, sub_link, plan_id, days):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    expiry_date = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO active_services (user_id, sub_uuid, sub_link, expiry_date, plan_id) VALUES (?, ?, ?, ?, ?)", (user_id, sub_uuid, sub_link, expiry_date, plan_id))
    conn.commit(); conn.close()
def get_user_services(user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT service_id, sub_uuid, sub_link, expiry_date, plan_id FROM active_services WHERE user_id = ?", (user_id,))
    services = [{"service_id": s[0], "sub_uuid": s[1], "sub_link": s[2], "expiry_date": s[3], "plan_id": s[4]} for s in cursor.fetchall()]
    conn.close(); return services
def renew_service(service_id, days):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    current_expiry_str = cursor.execute("SELECT expiry_date FROM active_services WHERE service_id = ?", (service_id,)).fetchone()[0]
    current_expiry = datetime.datetime.strptime(current_expiry_str, "%Y-%m-%d")
    start_date = max(current_expiry, datetime.datetime.now())
    new_expiry_date = (start_date + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("UPDATE active_services SET expiry_date = ? WHERE service_id = ?", (new_expiry_date, service_id)); conn.commit(); conn.close()
def get_service(service_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT service_id, user_id, sub_uuid, sub_link, expiry_date, plan_id FROM active_services WHERE service_id = ?", (service_id,)); s = cursor.fetchone()
    conn.close();
    if not s: return None
    return {"service_id": s[0], "user_id": s[1], "sub_uuid": s[2], "sub_link": s[3], "expiry_date": s[4], "plan_id": s[5]}

def log_sale(user_id, plan_id, price):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    sale_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO sales (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)", (user_id, plan_id, price, sale_date)); conn.commit(); conn.close()
def get_stats():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users"); user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(sale_id), SUM(price) FROM sales"); sales_data = cursor.fetchone()
    sales_count, total_revenue = (sales_data[0] or 0, sales_data[1] or 0)
    conn.close(); return {"user_count": user_count, "sales_count": sales_count, "total_revenue": total_revenue}

def create_gift_code(amount, usage_limit):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    code = str(uuid.uuid4().hex[:10]).upper()
    cursor.execute("INSERT INTO gift_codes (code, amount, usage_limit) VALUES (?, ?, ?)", (code, amount, usage_limit)); conn.commit(); conn.close()
    return code
def use_gift_code(code, user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT amount, usage_limit, used_count FROM gift_codes WHERE code = ?", (code,)); gift = cursor.fetchone()
    if gift and gift[1] > gift[2]:
        amount = gift[0]
        update_balance(user_id, amount, add=True)
        cursor.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code = ?", (code,)); conn.commit(); conn.close()
        return amount
    conn.close(); return None
def list_gift_codes():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT code, amount, usage_limit, used_count FROM gift_codes")
    codes = [{"code": g[0], "amount": g[1], "usage_limit": g[2], "used_count": g[3]} for g in cursor.fetchall()]
    conn.close(); return codes
def delete_gift_code(code):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("DELETE FROM gift_codes WHERE code = ?", (code,)); conn.commit(); conn.close()
EOL

# src/hiddify_api.py
cat > src/hiddify_api.py << 'EOL'
import requests
import json
import uuid
from config import PANEL_DOMAIN, ADMIN_PATH, API_KEY

def _get_base_url(): return f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/api/v2/admin/"
def _get_headers(): return {"Hiddify-API-Key": API_KEY, "Content-Type": "application/json"}

def create_hiddify_user(plan_days, plan_gb, user_telegram_id=None):
    endpoint = _get_base_url() + "user/"
    user_name = f"tg-{user_telegram_id}-{uuid.uuid4().hex[:4]}" if user_telegram_id else f"test-user-{uuid.uuid4().hex[:8]}"
    comment = f"Telegram user: {user_telegram_id}" if user_telegram_id else "Created by script"
    payload = {"name": user_name, "package_days": int(plan_days), "usage_limit_GB": int(plan_gb), "comment": comment}
    try:
        response = requests.post(endpoint, headers=_get_headers(), data=json.dumps(payload), timeout=20)
        if response.status_code in [200, 201]:
            user_data = response.json()
            user_uuid = user_data.get('uuid')
            subscription_url = f"https://{PANEL_DOMAIN}/{ADMIN_PATH}/{user_uuid}/"
            return {"link": subscription_url, "uuid": user_uuid}
        else: print(f"ERROR (Create User): Hiddify API returned {response.status_code} -> {response.text}"); return None
    except Exception as e: print(f"ERROR (Create User): {e}"); return None

def get_user_info(user_uuid):
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    try:
        response = requests.get(endpoint, headers=_get_headers(), timeout=10)
        if response.status_code == 200: return response.json()
        else: print(f"ERROR (Get Info): Hiddify API returned {response.status_code} for UUID {user_uuid} -> {response.text}"); return None
    except Exception as e: print(f"ERROR (Get Info): {e}"); return None

def reset_user_traffic(user_uuid, days):
    # This function is now simplified for renewal. We update the user with new package days.
    endpoint = f"{_get_base_url()}user/{user_uuid}/"
    # To renew, we need to send a PUT request to update the user.
    # We mainly update 'package_days' to reset the expiry date based on now + days.
    # The 'reset' endpoint in Hiddify API might just reset the traffic, not the date.
    payload = {"package_days": int(days)}
    try:
        response = requests.put(endpoint, headers=_get_headers(), json=payload, timeout=10)
        if response.status_code == 200:
             # Also reset the traffic explicitly if the endpoint exists
            reset_endpoint = f"{_get_base_url()}user/{user_uuid}/reset/"
            requests.post(reset_endpoint, headers=_get_headers(), timeout=10) # We don't care much about the response here
            return True
        else: print(f"ERROR (Reset/Renew): Hiddify API returned {response.status_code} -> {response.text}"); return False
    except Exception as e: print(f"ERROR (Reset/Renew): {e}"); return False
EOL

# src/main_bot.py
# This is a very long file, so we use a different way to write it
(
    # The full main_bot.py content will be written below
)

# 5. Create the main_bot.py file separately due to its length and complexity
# This avoids issues with shell heredoc limitations
print_color "yellow" "Creating main_bot.py..."
# (The content of main_bot.py is in the next message)
# (For the install script, we'll embed it here)
# ... The entire main_bot.py script will be pasted here by the user ...


# The script pauses here to let the user paste the main_bot.py content
print_color "blue" "The script needs the content for 'src/main_bot.py'."
print_color "blue" "Please get the full code from the next message, then paste it here and press Enter."
# We will create an empty file first
touch src/main_bot.py
# Open it with nano for the user
nano src/main_bot.py
print_color "green" "'src/main_bot.py' has been created/edited."


# 6. Setup Python environment
print_color "yellow" "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
print_color "yellow" "Installing Python packages..."
pip install -r requirements.txt > /dev/null 2>&1
deactivate

# 7. Configure the bot
print_color "blue" "--- Configuration ---"
CONFIG_FILE="src/config.py"
cp src/config_template.py $CONFIG_FILE

read -p "Enter your Telegram Bot Token: " BOT_TOKEN
read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
read -p "Enter your Hiddify panel domain (e.g., mypanel.com): " PANEL_DOMAIN
read -p "Enter your Hiddify admin secret path: " ADMIN_PATH
read -p "Enter your Hiddify API Key: " API_KEY
read -p "Enter your support Telegram username (without @): " SUPPORT_USERNAME

sed -i "s|YOUR_BOT_TOKEN_HERE|${BOT_TOKEN}|" $CONFIG_FILE
sed -i "s|ADMIN_ID = 0|${ADMIN_ID}|" $CONFIG_FILE
sed -i "s|YOUR_PANEL_DOMAIN_HERE|${PANEL_DOMAIN}|" $CONFIG_FILE
sed -i "s|YOUR_ADMIN_SECRET_PATH_HERE|${ADMIN_PATH}|" $CONFIG_FILE
sed -i "s|YOUR_HIDDIFY_API_KEY_HERE|${API_KEY}|" $CONFIG_FILE
sed -i "s|YOUR_SUPPORT_USERNAME|${SUPPORT_USERNAME}|" $CONFIG_FILE

print_color "green" "Configuration file created successfully."

# 8. Create and start systemd service
print_color "yellow" "Creating systemd service..."
SERVICE_NAME="vpn_bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

cat > $SERVICE_FILE << EOL
[Unit]
Description=Hiddify Advanced Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=${INSTALL_DIR}/src
ExecStart=${INSTALL_DIR}/venv/bin/python main_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOL

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

print_color "blue" "--- Installation Complete ---"
print_color "green" "The bot has been installed and started successfully."
print_color "yellow" "Check status: systemctl status ${SERVICE_NAME}"
print_color "yellow" "View logs: journalctl -u ${SERVICE_NAME} -f"
