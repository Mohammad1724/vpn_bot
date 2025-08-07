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
   print_color "red" "This script must be run as root. Please use 'sudo bash uninstall.sh'."
   exit 1
fi

print_color "blue" "--- Hiddify Advanced Bot Uninstaller ---"

# --- Configuration ---
SERVICE_NAME="vpn_bot"
DEFAULT_INSTALL_DIR="/opt/vpn-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# 2. Stop and disable the systemd service
print_color "yellow" "Stopping and disabling the systemd service..."
# Use `systemctl list-units` to check if the service exists before trying to stop it
if systemctl list-units --type=service | grep -q "${SERVICE_NAME}.service"; then
    systemctl stop "$SERVICE_NAME"
    systemctl disable "$SERVICE_NAME"
    print_color "green" "Service stopped and disabled."
else
    print_color "yellow" "Service '${SERVICE_NAME}' not found. Skipping."
fi

# 3. Remove the systemd service file
if [ -f "$SERVICE_FILE" ]; then
    print_color "yellow" "Removing systemd service file..."
    rm "$SERVICE_FILE"
    systemctl daemon-reload
    print_color "green" "Service file removed."
else
    print_color "yellow" "Service file not found. Skipping."
fi

# 4. Ask for the installation directory and confirm removal
read -p "Enter the bot's installation directory to remove [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}

if [ -d "$INSTALL_DIR" ]; then
    print_color "red" "WARNING: This will permanently delete all bot files and data from '${INSTALL_DIR}'."
    read -p "Are you absolutely sure you want to proceed? [y/N]: " CONFIRM
    
    if [[ "$CONFIRM" =~ ^[yY]$ ]]; then
        print_color "yellow" "Removing installation directory: ${INSTALL_DIR}..."
        rm -rf "$INSTALL_DIR"
        print_color "green" "Directory successfully removed."
    else
        print_color "yellow" "Directory removal cancelled by user."
    fi
else
    print_color "yellow" "Installation directory '${INSTALL_DIR}' not found. Nothing to remove."
fi

print_color "blue" "--- Uninstallation Complete ---"