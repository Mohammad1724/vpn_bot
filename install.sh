#!/bin/bash

# =================================================================
# Hiddify Bot Installer
# A standalone script for the initial installation of the bot.
# This script is designed to work in tandem with manager.sh
# =================================================================

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
PROJECT_NAME="vpn_bot"
GITHUB_REPO="https://github.com/Mohammad1724/vpn_bot.git" # Your repository
INSTALL_DIR="/opt/vpn_bot"
SERVICE_NAME="${PROJECT_NAME}.service"

# --- Colors for better output ---
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_BLUE='\033[0;34m'

# --- Helper Functions ---
print_color() {
    echo -e "${!1}${2}${C_RESET}"
}

check_root() {
    if [ "$(id -u)" -ne "0" ]; then
        print_color "C_YELLOW" "This script requires root privileges. Re-running with sudo..."
        # Re-execute the script with sudo, passing all original arguments
        exec sudo bash "$0" "$@"
        exit 1
    fi
}

# --- Main Installation Logic ---

# 1. Ensure the script is run as root
check_root

print_color "C_BLUE" "--- Starting Hiddify Bot Installation ---"

# 2. Install required system packages
print_color "C_YELLOW" "[1/6] Installing system dependencies (git, python3, pip, venv)..."
apt-get update > /dev/null 2>&1
apt-get install -y git python3 python3-pip python3-venv > /dev/null 2>&1
print_color "C_GREEN" "System dependencies installed."

# 3. Clone the repository
if [ -d "$INSTALL_DIR" ]; then
    print_color "C_YELLOW" "Existing installation directory found at $INSTALL_DIR."
    read -p "Do you want to remove it and perform a clean installation? (This will delete existing data inside) [y/N]: " REINSTALL_CONFIRM
    if [[ "$REINSTALL_CONFIRM" =~ ^[Yy]$ ]]; then
        print_color "C_RED" "Removing existing directory..."
        systemctl stop "$SERVICE_NAME" &>/dev/null || true # Stop service if it exists
        rm -rf "$INSTALL_DIR"
    else
        print_color "C_YELLOW" "Installation aborted by user."
        exit 0
    fi
fi
print_color "C_YELLOW" "[2/6] Cloning the bot repository from GitHub..."
git clone "$GITHUB_REPO" "$INSTALL_DIR" > /dev/null 2>&1
print_color "C_GREEN" "Repository cloned to $INSTALL_DIR."

# Change to the project directory
cd "$INSTALL_DIR"

# 4. Set up Python virtual environment and install packages
print_color "C_YELLOW" "[3/6] Setting up Python virtual environment..."
python3 -m venv venv
print_color "C_YELLOW" "Installing Python dependencies from requirements.txt..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
deactivate
print_color "C_GREEN" "Python environment is ready."

# 5. Create and populate the configuration file
print_color "C_YELLOW" "[4/6] Creating configuration file (src/config.py)..."
CONFIG_FILE="src/config.py"
# Assuming you have a template file in your repo
cp src/config_template.py "$CONFIG_FILE" 

print_color "C_BLUE" "Please provide the following details to configure your bot:"
read -p "Enter your Telegram Bot Token: " BOT_TOKEN
read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
read -p "Enter your support Telegram username (without @): " SUPPORT_USERNAME

print_color "C_BLUE" "Hiddify Panel Details:"
read -p "Enter panel domain (e.g., mypanel.com): " PANEL_DOMAIN
read -p "Enter Hiddify ADMIN secret path: " ADMIN_PATH
read -p "Enter Hiddify SUBSCRIPTION secret path (can be same as ADMIN_PATH): " SUB_PATH
read -p "Enter Hiddify API Key (if you use one, otherwise leave blank): " API_KEY

# Apply configurations using sed
sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"${BOT_TOKEN}\"|" "$CONFIG_FILE"
sed -i "s|^ADMIN_ID = .*|ADMIN_ID = ${ADMIN_ID}|" "$CONFIG_FILE"
sed -i "s|^SUPPORT_USERNAME = .*|SUPPORT_USERNAME = \"${SUPPORT_USERNAME}\"|" "$CONFIG_FILE"
sed -i "s|^PANEL_DOMAIN = .*|PANEL_DOMAIN = \"${PANEL_DOMAIN}\"|" "$CONFIG_FILE"
sed -i "s|^ADMIN_PATH = .*|ADMIN_PATH = \"${ADMIN_PATH}\"|" "$CONFIG_FILE"
sed -i "s|^SUB_PATH = .*|SUB_PATH = \"${SUB_PATH}\"|" "$CONFIG_FILE"
# Only set API_KEY if it's provided
if [ -n "$API_KEY" ]; then
    sed -i "s|^API_KEY = .*|API_KEY = \"${API_KEY}\"|" "$CONFIG_FILE"
fi

print_color "C_GREEN" "Configuration file created successfully."

# 6. Create, enable, and start the systemd service
print_color "C_YELLOW" "[5/6] Creating systemd service file..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
cat > "$SERVICE_FILE" << EOL
[Unit]
Description=Hiddify Telegram Bot (${PROJECT_NAME})
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}/src
ExecStart=${INSTALL_DIR}/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOL
print_color "C_GREEN" "Service file created at $SERVICE_FILE."

print_color "C_YELLOW" "[6/6] Enabling and starting the bot service..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

print_color "C_GREEN" "\n--- Installation Complete! ---"
print_color "C_BLUE" "The bot is now running as a background service."
echo "You can check its status with: ${C_YELLOW}sudo systemctl status ${SERVICE_NAME}${C_RESET}"
echo "You can view live logs with: ${C_YELLOW}sudo journalctl -u ${SERVICE_NAME} -f${C_RESET}"
echo "To manage the bot later, you can download and use the manager.sh script."