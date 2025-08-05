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
apt-get install -y python3 python3-pip python3-venv curl git > /dev/null 2>&1

# 2. Get GitHub repository URL and installation directory
GITHUB_REPO="https://github.com/Mohammad1724/vpn_bot.git"
DEFAULT_INSTALL_DIR="/opt/vpn-bot"

read -p "Enter the installation directory [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}

if [ -d "$INSTALL_DIR" ]; then
    print_color "yellow" "Existing directory found. Removing it for a clean installation..."
    rm -rf "$INSTALL_DIR"
fi

# 3. Clone repository
print_color "yellow" "Cloning repository from GitHub..."
git clone $GITHUB_REPO $INSTALL_DIR
if [ $? -ne 0 ]; then
    print_color "red" "Failed to clone repository. Please check the URL and your internet connection."
    exit 1
fi
cd $INSTALL_DIR

# 4. Create Python virtual environment and install packages
print_color "yellow" "Setting up Python environment and installing packages..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt > /dev/null 2>&1
deactivate

# 5. Create and configure config.py
print_color "blue" "--- Configuration ---"
CONFIG_FILE="src/config.py"
cp src/config_template.py $CONFIG_FILE

read -p "Enter your Telegram Bot Token: " BOT_TOKEN
read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
read -p "Enter your Hiddify panel domain (e.g., mypanel.com): " PANEL_DOMAIN
read -p "Enter your Hiddify ADMIN secret path: " ADMIN_PATH
read -p "Enter your Hiddify SUBSCRIPTION secret path: " SUB_PATH
read -p "Enter your Hiddify API Key: " API_KEY
read -p "Enter your support Telegram username (without @): " SUPPORT_USERNAME

print_color "yellow" "\nEnter your subscription domains, separated by a comma (or press Enter to use panel domain)."
read -p "Subscription Domains: " SUB_DOMAINS_INPUT

PYTHON_LIST_FORMAT="[]"
if [ -n "$SUB_DOMAINS_INPUT" ]; then
    PYTHON_LIST_FORMAT="[\"${SUB_DOMAINS_INPUT//,/'\", \"'}\"]"
fi

sed -i "/^BOT_TOKEN =/c\BOT_TOKEN = \"${BOT_TOKEN}\"" $CONFIG_FILE
sed -i "/^ADMIN_ID =/c\ADMIN_ID = ${ADMIN_ID}" $CONFIG_FILE
sed -i "/^PANEL_DOMAIN =/c\PANEL_DOMAIN = \"${PANEL_DOMAIN}\"" $CONFIG_FILE
sed -i "/^ADMIN_PATH =/c\ADMIN_PATH = \"${ADMIN_PATH}\"" $CONFIG_FILE
sed -i "/^SUB_PATH =/c\SUB_PATH = \"${SUB_PATH}\"" $CONFIG_FILE
sed -i "/^API_KEY =/c\API_KEY = \"${API_KEY}\"" $CONFIG_FILE
sed -i "/^SUPPORT_USERNAME =/c\SUPPORT_USERNAME = \"${SUPPORT_USERNAME}\"" $CONFIG_FILE
sed -i "/^SUB_DOMAINS =/c\SUB_DOMAINS = ${PYTHON_LIST_FORMAT}" $CONFIG_FILE

print_color "green" "Configuration file created successfully."

# 6. Create systemd service
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

# 7. Enable and start the service
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

print_color "blue" "--- Installation Complete ---"
print_color "green" "The bot has been installed and started successfully."
print_color "yellow" "Check status: systemctl status ${SERVICE_NAME}"
print_color "yellow" "View logs: journalctl -u ${SERVICE_NAME} -f"