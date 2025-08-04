#!/bin/bash

# ======================================================
#   Hiddify VPN Bot Uninstaller
#   This script will completely remove the bot,
#   its service, and all related files.
# ======================================================

echo "--- Starting Hiddify VPN Bot Uninstallation ---"
echo "This will permanently delete the bot and its data."
read -p "Are you sure you want to continue? (y/n): " CONFIRM

if [ "$CONFIRM" != "y" ]; then
    echo "Uninstallation cancelled."
    exit 0
fi

# --- 1. Stop and disable the systemd service ---
SERVICE_NAME="vpn_bot.service"
echo "[1/3] Stopping and disabling the systemd service..."

if systemctl is-active --quiet $SERVICE_NAME; then
    sudo systemctl stop $SERVICE_NAME
    echo "Service stopped."
else
    echo "Service was not running."
fi

if systemctl is-enabled --quiet $SERVICE_NAME; then
    sudo systemctl disable $SERVICE_NAME
    echo "Service disabled."
else
    echo "Service was not enabled."
fi

# --- 2. Remove the systemd service file ---
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
echo "[2/3] Removing the systemd service file..."

if [ -f "$SERVICE_FILE" ]; then
    sudo rm -f "$SERVICE_FILE"
    sudo systemctl daemon-reload
    echo "Service file removed and systemd reloaded."
else
    echo "Service file not found. Skipping."
fi

# --- 3. Remove the installation directory ---
INSTALL_DIR="/opt/vpn_bot"
echo "[3/3] Removing the installation directory ($INSTALL_DIR)..."

if [ -d "$INSTALL_DIR" ]; then
    sudo rm -rf "$INSTALL_DIR"
    echo "Installation directory removed."
else
    echo "Installation directory not found. Skipping."
fi

echo ""
echo "======================================================"
echo "      ✅ Uninstallation Complete ✅"
echo "The Hiddify VPN bot has been completely removed."
echo "======================================================"