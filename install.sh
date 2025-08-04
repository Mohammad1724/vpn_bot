#!/bin/bash

# ==============================================================================
# Final Hiddify VPN Bot Installer (Version 4 - Robust & Self-Healing)
# This script cleans up old installations, creates a reliable virtual
# environment, and sets up a systemd service correctly.
# ==============================================================================

set -e # Exit immediately if a command exits with a non-zero status.

echo "--- Starting Hiddify VPN Bot Installation ---"

# --- 1. Clean up any previous broken installations ---
echo "[1/8] Cleaning up previous installations (if any)..."
sudo systemctl stop vpn_bot.service >/dev/null 2>&1 || true
sudo systemctl disable vpn_bot.service >/dev/null 2>&1 || true
sudo rm -f /etc/systemd/system/vpn_bot.service
sudo rm -rf /opt/vpn_bot
sudo systemctl daemon-reload

echo "Cleanup complete."

# --- 2. Install essential packages ---
echo "[2/8] Installing system dependencies (python3, pip, git, venv)..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip git python3-venv

echo "Dependencies installed."

# --- 3. Get User Input for Configuration ---
echo "[3/8] Please provide your bot and panel details:"
read -p "Enter your Telegram Bot Token: " TELEGRAM_BOT_TOKEN
read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
read -p "Enter your Hiddify Panel Domain (e.g., panel.example.com): " HIDDIFY_DOMAIN
read -p "Enter your Hiddify Proxy Path: " HIDDIFY_PATH
read -p "Enter your Hiddify Admin UUID: " HIDDIFY_ADMIN_UUID

# --- 4. Clone the repository ---
INSTALL_DIR="/opt/vpn_bot"
echo "[4/8] Cloning repository into $INSTALL_DIR..."
sudo git clone https://github.com/Mohammad1724/vpn_bot.git $INSTALL_DIR

# --- 5. Create config.py file ---
echo "[5/8] Creating config.py file..."
sudo bash -c "cat > $INSTALL_DIR/config.py" <<EOL
# config.py
TELEGRAM_BOT_TOKEN = "$TELEGRAM_BOT_TOKEN"
ADMIN_ID = $ADMIN_ID
HIDDIFY_DOMAIN = "$HIDDIFY_DOMAIN"
HIDDIFY_PATH = "$HIDDIFY_PATH"
HIDDIFY_ADMIN_UUID = "$HIDDIFY_ADMIN_UUID"
EOL

# --- 6. Create Virtual Environment and install packages ---
echo "[6/8] Creating Python virtual environment and installing libraries..."
sudo python3 -m venv $INSTALL_DIR/venv
# Check if venv was created successfully
if [ ! -f "$INSTALL_DIR/venv/bin/python" ]; then
    echo "ERROR: Failed to create Python virtual environment. Aborting."
    exit 1
fi
sudo $INSTALL_DIR/venv/bin/pip install --upgrade pip
sudo $INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt
echo "Libraries installed in venv."

# --- 7. Create and configure systemd service ---
SERVICE_NAME="vpn_bot.service"
PYTHON_EXEC="$INSTALL_DIR/venv/bin/python"
MAIN_SCRIPT="$INSTALL_DIR/main.py"

echo "[7/8] Creating systemd service file..."
sudo bash -c "cat > /etc/systemd/system/$SERVICE_NAME" <<EOL
[Unit]
Description=Telegram VPN Bot for Hiddify
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_EXEC $MAIN_SCRIPT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# Set correct permissions for the entire directory
sudo chown -R root:root $INSTALL_DIR
sudo chmod -R 755 $INSTALL_DIR

echo "Service file created and permissions set."

# --- 8. Start and enable the service ---
echo "[8/8] Enabling and starting the bot service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

echo ""
echo "======================================================"
echo "      ✅ Installation successful! ✅"
echo "======================================================"
echo "Your bot is now running as a background service."
echo "To check its status, run: sudo systemctl status $SERVICE_NAME"
echo "To view live logs, run:   sudo journalctl -u $SERVICE_NAME -f"
echo "======================================================"
