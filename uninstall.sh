#!/bin/bash

# Function to print colored messages
print_color() {
    COLOR=$1
    TEXT=$2
    case $COLOR in
        "red") echo -e "\e[31m${TEXT}\e[0m" ;;
        "green") echo -e "\e[32m${TEXT}\e[0m" ;;
        "yellow") echo -e "\e[33m${TEXT}\e[0m" ;;
    esac
}

if [ "$(id -u)" != "0" ]; then
   print_color "red" "This script must be run as root. Please use 'sudo'."
   exit 1
fi

print_color "yellow" "--- Hiddify VPN Bot Uninstaller ---"

SERVICE_NAME="vpn_bot"
DEFAULT_INSTALL_DIR="/opt/vpn-bot"

# Stop and disable the service
print_color "yellow" "Stopping and disabling the systemd service..."
systemctl stop $SERVICE_NAME > /dev/null 2>&1
systemctl disable $SERVICE_NAME > /dev/null 2>&1

# Remove the service file
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
if [ -f "$SERVICE_FILE" ]; then
    print_color "yellow" "Removing systemd service file..."
    rm $SERVICE_FILE
    systemctl daemon-reload
fi

# Remove the installation directory
read -p "Enter the bot's installation directory [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}

if [ -d "$INSTALL_DIR" ]; {
    read -p "Are you sure you want to permanently delete all bot files from ${INSTALL_DIR}? [y/N]: " CONFIRM
    if [[ "$CONFIRM" =~ ^[yY]$ ]]; then
        print_color "yellow" "Removing installation directory..."
        rm -rf $INSTALL_DIR
        print_color "green" "Directory removed."
    else
        print_color "yellow" "Skipping directory removal."
    fi
}
fi

print_color "green" "--- Uninstallation Complete ---"
