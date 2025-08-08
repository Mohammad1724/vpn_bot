#!/bin/bash

# =================================================================
# Hiddify Bot Manager
# A comprehensive script for installing, updating, and managing the bot.
# =================================================================

# --- Configuration ---
PROJECT_NAME="vpn_bot"
GITHUB_REPO="https://github.com/Mohammad1724/vpn_bot.git" # Your repository
INSTALL_DIR="/opt/vpn_bot"
SERVICE_NAME="${PROJECT_NAME}.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

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
        exec sudo bash "$0" "$@"
        exit 1
    fi
}

# --- Pre-execution check ---
check_root

# --- Check if bot is installed ---
is_installed() {
    if [ -d "$INSTALL_DIR" ] && [ -f "$SERVICE_FILE" ]; then
        return 0 # True
    else
        return 1 # False
    fi
}

# --- Core Management Functions ---

function install_bot() {
    print_color "C_BLUE" "--- Starting Hiddify Bot Installation ---"

    if is_installed; then
        print_color "C_YELLOW" "Bot is already installed."
        read -p "Do you want to remove the existing version and reinstall? (This will delete all previous data) [y/N]: " REINSTALL_CONFIRM
        if [[ "$REINSTALL_CONFIRM" =~ ^[Yy]$ ]]; then
            uninstall_bot_silent
        else
            print_color "C_YELLOW" "Installation aborted by user."
            return
        fi
    fi

    # 1. Install system dependencies
    print_color "C_YELLOW" "[1/6] Installing system dependencies (git, python3, pip, venv)..."
    apt-get update > /dev/null 2>&1
    apt-get install -y git python3 python3-pip python3-venv > /dev/null 2>&1
    print_color "C_GREEN" "System dependencies installed."

    # 2. Clone the repository
    print_color "C_YELLOW" "[2/6] Cloning the bot repository from GitHub..."
    git clone "$GITHUB_REPO" "$INSTALL_DIR" > /dev/null 2>&1
    print_color "C_GREEN" "Repository cloned to $INSTALL_DIR."

    # Change to the project directory
    cd "$INSTALL_DIR"

    # 3. Set up Python virtual environment
    print_color "C_YELLOW" "[3/6] Setting up Python virtual environment..."
    python3 -m venv venv
    print_color "C_YELLOW" "Installing Python dependencies from requirements.txt..."
    source venv/bin/activate
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt > /dev/null 2>&1
    deactivate
    print_color "C_GREEN" "Python environment is ready."

    # 4. Create configuration file
    print_color "C_YELLOW" "[4/6] Creating configuration file (src/config.py)..."
    CONFIG_FILE="src/config.py"
    cp src/config_template.py "$CONFIG_FILE"

    print_color "C_BLUE" "Please provide the following details to configure the bot:"
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
    if [ -n "$API_KEY" ]; then
        sed -i "s|^API_KEY = .*|API_KEY = \"${API_KEY}\"|" "$CONFIG_FILE"
    fi
    print_color "C_GREEN" "Configuration file created successfully."

    # 5. Create systemd service
    print_color "C_YELLOW" "[5/6] Creating systemd service file..."
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

    # 6. Enable and start the service
    print_color "C_YELLOW" "[6/6] Enabling and starting the bot service..."
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"

    print_color "C_GREEN" "\n--- Installation Complete! ---"
    print_color "C_BLUE" "The bot is now running as a background service."
    echo "You can check its status with: ${C_YELLOW}systemctl status ${SERVICE_NAME}${C_RESET}"
}

function update_bot() {
    if ! is_installed; then
        print_color "C_RED" "Error: Bot is not installed. Please choose option 1 to install it first."
        return
    fi
    print_color "C_BLUE" "--- Starting Bot Update ---"
    
    cd "$INSTALL_DIR"
    print_color "C_YELLOW" "[1/3] Pulling latest changes from GitHub..."
    git pull
    
    print_color "C_YELLOW" "[2/3] Updating Python dependencies..."
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    
    print_color "C_YELLOW" "[3/3] Restarting the bot service..."
    systemctl restart "$SERVICE_NAME"
    
    print_color "C_GREEN" "--- Update Complete! ---"
}

function show_status() {
    if ! is_installed; then
        print_color "C_RED" "Error: Bot is not installed."
        return
    fi
    print_color "C_BLUE" "--- Bot Service Status ---"
    systemctl status "$SERVICE_NAME"
}

function show_live_logs() {
    if ! is_installed; then
        print_color "C_RED" "Error: Bot is not installed."
        return
    fi
    print_color "C_BLUE" "--- Showing Live Logs (Press CTRL+C to exit) ---"
    journalctl -u "$SERVICE_NAME" -f
}

function show_all_logs() {
    if ! is_installed; then
        print_color "C_RED" "Error: Bot is not installed."
        return
    fi
    print_color "C_BLUE" "--- Showing All Bot Logs ---"
    journalctl -u "$SERVICE_NAME"
}

function restart_bot() {
    if ! is_installed; then
        print_color "C_RED" "Error: Bot is not installed."
        return
    fi
    print_color "C_BLUE" "--- Restarting Bot Service ---"
    systemctl restart "$SERVICE_NAME"
    print_color "C_GREEN" "Bot service restarted successfully."
    sleep 2
    show_status
}

function uninstall_bot() {
    if ! is_installed; then
        print_color "C_RED" "Error: Bot is not installed."
        return
    fi
    
    print_color "C_RED" "!!! UNINSTALL WARNING !!!"
    read -p "Are you sure you want to completely uninstall the bot? (This action is irreversible) [y/N]: " UNINSTALL_CONFIRM
    if [[ "$UNINSTALL_CONFIRM" =~ ^[Yy]$ ]]; then
        uninstall_bot_silent
        print_color "C_GREEN" "--- Bot uninstalled successfully. ---"
    else
        print_color "C_YELLOW" "Uninstall operation cancelled by user."
    fi
}

function uninstall_bot_silent() {
    print_color "C_YELLOW" "Stopping and disabling service..."
    systemctl stop "$SERVICE_NAME" &>/dev/null || true
    systemctl disable "$SERVICE_NAME" &>/dev/null || true
    
    print_color "C_YELLOW" "Removing service file..."
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    
    print_color "C_YELLOW" "Removing installation directory..."
    rm -rf "$INSTALL_DIR"
}

function show_menu() {
    clear
    print_color "C_BLUE" "=========================================="
    print_color "C_BLUE" "          Hiddify Bot Manager"
    print_color "C_BLUE" "=========================================="
    echo ""
    print_color "C_GREEN" "1. Install / Reinstall Bot"
    print_color "C_GREEN" "2. Update Bot"
    print_color "C_GREEN" "3. Show Status"
    print_color "C_GREEN" "4. Show Live Logs"
    print_color "C_GREEN" "5. Show All Logs"
    print_color "C_GREEN" "6. Restart Bot"
    print_color "C_RED"   "7. Uninstall Bot"
    echo ""
    print_color "C_YELLOW" "0. Exit"
    echo ""
}

# --- Main Logic ---
while true; do
    show_menu
    read -p "Please choose an option [0-7]: " choice

    case $choice in
        1)
            install_bot
            ;;
        2)
            update_bot
            ;;
        3)
            show_status
            ;;
        4)
            show_live_logs
            ;;
        5)
            show_all_logs
            ;;
        6)
            restart_bot
            ;;
        7)
            uninstall_bot
            ;;
        0)
            print_color "C_BLUE" "Exiting."
            exit 0
            ;;
        *)
            print_color "C_RED" "Invalid option. Please enter a number between 0 and 7."
            ;;
    esac
    
    if [[ "$choice" != "0" ]]; then
        read -p $'\nPress Enter to return to the main menu...'
    fi
done