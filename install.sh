#!/bin/bash

# =================================================================
# Hiddify Advanced Bot Manager - v1.0
# A professional multi-tool script for managing the bot lifecycle.
# =================================================================

set -o pipefail

# --- Configuration ---
PROJECT_NAME="vpn_bot"
GITHUB_REPO="https://github.com/Mohammad1724/vpn_bot.git"
DEFAULT_INSTALL_DIR="/opt/vpn-bot"
SERVICE_NAME="${PROJECT_NAME}.service"

# --- Colors ---
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_BLUE='\033[0;34m'
C_CYAN='\033[0;36m'

# --- Helper Functions ---

print_color() {
    echo -e "${!1}${2}${C_RESET}"
}

check_root() {
    if [ "$(id -u)" -ne "0" ]; then
        print_color "C_YELLOW" "This action requires root privileges. Attempting to re-run with sudo..."
        exec sudo bash "$0" "$@"
        exit 1
    fi
}

# --- Core Functions ---

do_install() {
    print_color "C_BLUE" "--- Starting Full Bot Installation ---"
    
    print_color "C_YELLOW" "[1/7] Installing system dependencies..."
    apt-get update > /dev/null 2>&1
    apt-get install -y python3 python3-pip python3-venv curl git > /dev/null 2>&1

    INSTALL_DIR=$DEFAULT_INSTALL_DIR
    if [ -d "$INSTALL_DIR" ]; then
        print_color "C_YELLOW" "An existing installation was found. Backing up config and removing old directory..."
        if [ -f "${INSTALL_DIR}/src/config.py" ]; then
            mv "${INSTALL_DIR}/src/config.py" "/tmp/config.py.bak"
            print_color "C_GREEN" "Existing config.py backed up to /tmp/config.py.bak"
        fi
        systemctl stop "$SERVICE_NAME" || true
        rm -rf "$INSTALL_DIR"
    fi

    print_color "C_YELLOW" "[2/7] Cloning repository..."
    git clone "$GITHUB_REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"

    print_color "C_YELLOW" "[3/7] Setting up Python environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt > /dev/null 2>&1
    deactivate

    print_color "C_YELLOW" "[4/7] Creating configuration file..."
    CONFIG_FILE="src/config.py"
    cp src/config_template.py "$CONFIG_FILE"

    if [ -f "/tmp/config.py.bak" ]; then
        read -p "A backup of your previous config was found. Do you want to restore it? [Y/n]: " RESTORE_CONF
        if [[ "${RESTORE_CONF:-Y}" =~ ^[Yy]$ ]]; then
            mv "/tmp/config.py.bak" "$CONFIG_FILE"
            print_color "C_GREEN" "Configuration restored."
        else
            collect_config_details "$CONFIG_FILE"
        fi
    else
        collect_config_details "$CONFIG_FILE"
    fi

    print_color "C_YELLOW" "[5/7] Creating systemd service..."
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
    create_systemd_service "$INSTALL_DIR" "$SERVICE_FILE"

    print_color "C_YELLOW" "[6/7] Reloading and starting the service..."
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"

    print_color "C_GREEN" "\n--- Installation Complete! ---"
    print_color "C_YELLOW" "The bot is now running. Use 'sudo bash manager.sh' to manage it."
}

collect_config_details() {
    local CONFIG_FILE=$1
    print_color "C_BLUE" "Please provide the following details:"
    read -p "Enter your Telegram Bot Token: " BOT_TOKEN
    read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
    read -p "Enter your Hiddify panel domain (e.g., mypanel.com): " PANEL_DOMAIN
    read -p "Enter your Hiddify ADMIN secret path: " ADMIN_PATH
    read -p "Enter your Hiddify SUBSCRIPTION secret path (can be same as ADMIN_PATH): " SUB_PATH
    read -p "Enter your Hiddify API Key: " API_KEY
    read -p "Enter your support Telegram username (without @): " SUPPORT_USERNAME
    read -p "Enter subscription domains, separated by comma: " SUB_DOMAINS_INPUT
    
    PYTHON_LIST_FORMAT_DOMAINS="[]"
    if [ -n "$SUB_DOMAINS_INPUT" ]; then
        PYTHON_LIST_FORMAT_DOMAINS="[\"$(echo "$SUB_DOMAINS_INPUT" | sed 's/,/\", \"/g')\"]"
    fi

    read -p "Enable free trial? [Y/n]: " ENABLE_TRIAL
    TRIAL_ENABLED_VAL="False"; TRIAL_DAYS_VAL=1; TRIAL_GB_VAL=1
    if [[ "${ENABLE_TRIAL:-Y}" =~ ^[Yy]$ ]]; then
        TRIAL_ENABLED_VAL="True"
        read -p "Trial duration in days [1]: " TRIAL_DAYS_INPUT; TRIAL_DAYS_VAL=${TRIAL_DAYS_INPUT:-1}
        read -p "Trial data limit in GB [1]: " TRIAL_GB_INPUT; TRIAL_GB_VAL=${TRIAL_GB_INPUT:-1}
    fi

    read -p "Referral bonus in Toman [5000]: " REFERRAL_BONUS_INPUT; REFERRAL_BONUS_AMOUNT=${REFERRAL_BONUS_INPUT:-5000}
    read -p "Send expiry reminder X days before [3]: " EXPIRY_REMINDER_INPUT; EXPIRY_REMINDER_DAYS=${EXPIRY_REMINDER_INPUT:-3}
    read -p "Send low usage warning at what percentage? (e.g., 80) [80]: " USAGE_THRESHOLD_INPUT; USAGE_ALERT_THRESHOLD_PERCENT=${USAGE_THRESHOLD_INPUT:-80}
    USAGE_ALERT_THRESHOLD=$(awk "BEGIN {print ${USAGE_ALERT_THRESHOLD_PERCENT}/100}")

    read -p "Enter channel usernames for force join (@ch1,@ch2): " FORCE_JOIN_INPUT
    PYTHON_LIST_FORMAT_CHANNELS="[]"
    if [ -n "$FORCE_JOIN_INPUT" ]; then
        PYTHON_LIST_FORMAT_CHANNELS="[\"$(echo "$FORCE_JOIN_INPUT" | sed 's/,/\", \"/g')\"]"
    fi
    
    sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"${BOT_TOKEN}\"|; \
            s|^ADMIN_ID = .*|ADMIN_ID = ${ADMIN_ID}|; \
            s|^SUPPORT_USERNAME = .*|SUPPORT_USERNAME = \"${SUPPORT_USERNAME}\"|; \
            s|^PANEL_DOMAIN = .*|PANEL_DOMAIN = \"${PANEL_DOMAIN}\"|; \
            s|^ADMIN_PATH = .*|ADMIN_PATH = \"${ADMIN_PATH}\"|; \
            s|^SUB_PATH = .*|SUB_PATH = \"${SUB_PATH}\"|; \
            s|^API_KEY = .*|API_KEY = \"${API_KEY}\"|; \
            s|^SUB_DOMAINS = .*|SUB_DOMAINS = ${PYTHON_LIST_FORMAT_DOMAINS}|; \
            s|^TRIAL_ENABLED = .*|TRIAL_ENABLED = ${TRIAL_ENABLED_VAL}|; \
            s|^TRIAL_DAYS = .*|TRIAL_DAYS = ${TRIAL_DAYS_VAL}|; \
            s|^TRIAL_GB = .*|TRIAL_GB = ${TRIAL_GB_VAL}|; \
            s|^REFERRAL_BONUS_AMOUNT = .*|REFERRAL_BONUS_AMOUNT = ${REFERRAL_BONUS_AMOUNT}|; \
            s|^EXPIRY_REMINDER_DAYS = .*|EXPIRY_REMINDER_DAYS = ${EXPIRY_REMINDER_DAYS}|; \
            s|^USAGE_ALERT_THRESHOLD = .*|USAGE_ALERT_THRESHOLD = ${USAGE_ALERT_THRESHOLD}|; \
            s|^FORCE_JOIN_CHANNELS = .*|FORCE_JOIN_CHANNELS = ${PYTHON_LIST_FORMAT_CHANNELS}|" "$CONFIG_FILE"
}

create_systemd_service() {
    local INSTALL_DIR=$1
    local SERVICE_FILE=$2
    cat > "$SERVICE_FILE" << EOL
[Unit]
Description=Hiddify Telegram Bot Service
After=network.target
[Service]
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}/src
ExecStart=${INSTALL_DIR}/venv/bin/python main_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
EOL
}

do_update() {
    print_color "C_BLUE" "--- Updating Bot ---"
    cd "$DEFAULT_INSTALL_DIR"
    print_color "C_YELLOW" "[1/3] Pulling latest changes from GitHub..."
    git pull origin main
    
    print_color "C_YELLOW" "[2/3] Updating Python packages..."
    source venv/bin/activate
    pip install -r requirements.txt > /dev/null 2>&1
    deactivate
    
    print_color "C_YELLOW" "[3/3] Restarting the bot service..."
    systemctl restart "$SERVICE_NAME"
    
    print_color "C_GREEN" "\n--- Update Complete! ---"
}

do_uninstall() {
    read -p "Are you sure you want to completely uninstall the bot? [y/N]: " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        print_color "C_YELLOW" "Uninstallation cancelled."
        exit 0
    fi
    
    print_color "C_YELLOW" "Stopping and disabling service..."
    systemctl stop "$SERVICE_NAME" || true
    systemctl disable "$SERVICE_NAME" || true

    print_color "C_YELLOW" "Removing files..."
    rm -f "/etc/systemd/system/${SERVICE_NAME}"
    rm -rf "$DEFAULT_INSTALL_DIR"
    systemctl daemon-reload
    
    print_color "C_GREEN" "\n--- Uninstallation Complete! ---"
}

do_status() {
    systemctl status "$SERVICE_NAME"
    # Bonus: Check if bot is responsive via Telegram API
    TOKEN=$(grep -oP 'BOT_TOKEN = "\K[^"]+' ${DEFAULT_INSTALL_DIR}/src/config.py)
    if [ -n "$TOKEN" ]; then
        API_URL="https://api.telegram.org/bot${TOKEN}/getMe"
        if response=$(curl -s $API_URL); then
            if echo "$response" | grep -q '"ok":true'; then
                BOT_USERNAME=$(echo "$response" | grep -oP '"username":"\K[^"]+')
                print_color "C_GREEN" "\nTelegram API check: Bot @${BOT_USERNAME} is responsive."
            else
                print_color "C_RED" "\nTelegram API check: Bot token seems invalid or blocked."
            fi
        else
            print_color "C_RED" "\nTelegram API check: Could not connect to Telegram API."
        fi
    fi
}

# --- Main Menu ---
show_menu() {
    clear
    print_color "C_CYAN" "========================================="
    print_color "C_CYAN" "    Hiddify Advanced Bot Manager v2.0"
    print_color "C_CYAN" "========================================="
    echo ""
    print_color "C_GREEN" "  1. Install / Reinstall Bot"
    print_color "C_GREEN" "  2. Update Bot"
    print_color "C_YELLOW" "  3. Restart Service"
    print_color "C_YELLOW" "  4. Check Service Status"
    print_color "C_YELLOW" "  5. View Live Logs (journalctl)"
    print_color "C_YELLOW" "  6. View bot.log File"
    print_color "C_RED"   "  7. Uninstall Bot"
    echo ""
    print_color "C_CYAN" "  0. Exit"
    print_color "C_CYAN" "-----------------------------------------"
    read -p "Please enter your choice [0-7]: " choice
}

# --- Script Logic ---
if [[ "$1" ]]; then
    choice=$1
else
    show_menu
fi

case $choice in
    1) check_root; do_install ;;
    2) check_root; do_update ;;
    3) check_root; systemctl restart "$SERVICE_NAME"; print_color "C_GREEN" "Service restarted." ;;
    4) check_root; do_status ;;
    5) check_root; journalctl -u "$SERVICE_NAME" -f ;;
    6) do_view_log_file ;; # No root needed to view log
    7) check_root; do_uninstall ;;
    0) print_color "C_BLUE" "Exiting."; exit 0 ;;
    *) print_color "C_RED" "Invalid choice." ;;
esac