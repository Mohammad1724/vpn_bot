#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to print colored messages
print_color() {
    COLOR=$1
    TEXT=$2
    # Standard color codes
    case $COLOR in
        "red") echo -e "\033[0;31m${TEXT}\033[0m" ;;
        "green") echo -e "\033[0;32m${TEXT}\033[0m" ;;
        "yellow") echo -e "\033[0;33m${TEXT}\033[0m" ;;
        "blue") echo -e "\033[0;34m${TEXT}\033[0m" ;;
    esac
}

# --- Main Script ---

# 1. Check for root privileges
if [ "$(id -u)" -ne "0" ]; then
   print_color "red" "This script must be run as root. Please use 'sudo bash install.sh'."
   exit 1
fi

print_color "blue" "--- Hiddify Advanced Bot Installer ---"

# 2. Update system and install dependencies
print_color "yellow" "Updating package lists and installing system dependencies..."
apt-get update > /dev/null 2>&1
apt-get install -y python3 python3-pip python3-venv curl git > /dev/null 2>&1

# 3. Get repository and installation directory
GITHUB_REPO="https://github.com/Mohammad1724/vpn_bot.git" # <<< Assumed repo, change if needed
DEFAULT_INSTALL_DIR="/opt/vpn-bot"

read -p "Enter the installation directory [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}

if [ -d "$INSTALL_DIR" ]; then
    print_color "yellow" "An existing installation was found. It will be removed for a clean setup."
    # Stop the service before removing files to prevent issues
    systemctl stop vpn_bot.service || true
    rm -rf "$INSTALL_DIR"
fi

# 4. Clone repository
print_color "yellow" "Cloning the bot repository from GitHub..."
git clone "$GITHUB_REPO" "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    print_color "red" "Failed to clone the repository. Please check the URL and your internet connection."
    exit 1
fi
cd "$INSTALL_DIR"

# 5. Set up Python environment and install packages from requirements.txt
print_color "yellow" "Setting up Python virtual environment and installing required packages..."
python3 -m venv venv
# Activate venv for this script's context to ensure pip commands run inside it
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
# Ensure requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    print_color "red" "Error: 'requirements.txt' not found in the repository root."
    exit 1
fi
pip install -r requirements.txt > /dev/null 2>&1
deactivate

# 6. Create and configure config.py
print_color "blue" "--- Bot Configuration ---"
CONFIG_FILE="src/config.py"
# Check if the template file exists before copying
if [ ! -f "src/config_template.py" ]; then
    print_color "red" "Error: 'src/config_template.py' not found in the repository."
    exit 1
fi
cp src/config_template.py "$CONFIG_FILE"

# --- Collect user input ---
read -p "Enter your Telegram Bot Token: " BOT_TOKEN
read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
read -p "Enter your Hiddify panel domain (e.g., mypanel.com): " PANEL_DOMAIN
read -p "Enter your Hiddify ADMIN secret path: " ADMIN_PATH
read -p "Enter your Hiddify SUBSCRIPTION secret path (can be same as ADMIN_PATH): " SUB_PATH
read -p "Enter your Hiddify API Key (from the admin panel): " API_KEY
read -p "Enter your support Telegram username (without @): " SUPPORT_USERNAME

print_color "yellow" "\nEnter your subscription domains, separated by a comma (or press Enter to use panel domain)."
read -p "Subscription Domains: " SUB_DOMAINS_INPUT

PYTHON_LIST_FORMAT="[]"
if [ -n "$SUB_DOMAINS_INPUT" ]; then
    # Improved sed command to handle special characters in domains
    PYTHON_LIST_FORMAT="[\"$(echo "$SUB_DOMAINS_INPUT" | sed 's/,/\", \"/g')\"]"
fi

print_color "blue" "\n--- Free Trial Configuration ---"
read -p "Do you want to enable the free trial service? [Y/n]: " ENABLE_TRIAL
ENABLE_TRIAL=${ENABLE_TRIAL:-Y}

TRIAL_ENABLED_VAL="False"
TRIAL_DAYS_VAL=0
TRIAL_GB_VAL=0

if [[ "$ENABLE_TRIAL" =~ ^[Yy]$ ]]; then
    TRIAL_ENABLED_VAL="True"
    read -p "Enter trial duration in days [1]: " TRIAL_DAYS_INPUT
    TRIAL_DAYS_VAL=${TRIAL_DAYS_INPUT:-1}
    read -p "Enter trial data limit in GB [1]: " TRIAL_GB_INPUT
    TRIAL_GB_VAL=${TRIAL_GB_INPUT:-1}
fi

# --- Use sed to replace placeholders in config.py ---
# Using a different delimiter for sed to avoid issues with special characters in inputs
sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"${BOT_TOKEN}\"|" "$CONFIG_FILE"
sed -i "s|^ADMIN_ID = .*|ADMIN_ID = ${ADMIN_ID}|" "$CONFIG_FILE"
sed -i "s|^PANEL_DOMAIN = .*|PANEL_DOMAIN = \"${PANEL_DOMAIN}\"|" "$CONFIG_FILE"
sed -i "s|^ADMIN_PATH = .*|ADMIN_PATH = \"${ADMIN_PATH}\"|" "$CONFIG_FILE"
sed -i "s|^SUB_PATH = .*|SUB_PATH = \"${SUB_PATH}\"|" "$CONFIG_FILE"
sed -i "s|^API_KEY = .*|API_KEY = \"${API_KEY}\"|" "$CONFIG_FILE"
sed -i "s|^SUPPORT_USERNAME = .*|SUPPORT_USERNAME = \"${SUPPORT_USERNAME}\"|" "$CONFIG_FILE"
sed -i "s|^SUB_DOMAINS = .*|SUB_DOMAINS = ${PYTHON_LIST_FORMAT}|" "$CONFIG_FILE"
sed -i "s|^TRIAL_ENABLED = .*|TRIAL_ENABLED = ${TRIAL_ENABLED_VAL}|" "$CONFIG_FILE"
sed -i "s|^TRIAL_DAYS = .*|TRIAL_DAYS = ${TRIAL_DAYS_VAL}|" "$CONFIG_FILE"
sed -i "s|^TRIAL_GB = .*|TRIAL_GB = ${TRIAL_GB_VAL}|" "$CONFIG_FILE"

print_color "green" "Configuration file created successfully."

# 7. Create systemd service file
print_color "yellow" "Creating and configuring systemd service..."
SERVICE_NAME="vpn_bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

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

# 8. Reload daemon and start the service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

print_color "blue" "--- Installation Complete ---"
print_color "green" "The bot has been installed and started successfully as '${SERVICE_NAME}' service."
print_color "yellow" "To check its status, run: systemctl status ${SERVICE_NAME}"
print_color "yellow" "To view live logs, run: journalctl -u ${SERVICE_NAME} -f"