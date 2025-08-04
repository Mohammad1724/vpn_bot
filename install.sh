#!/bin/bash
# Final Hiddify VPN Bot Installer (Version 4)
set -e
echo "--- Starting Hiddify VPN Bot Installation ---"
echo "[1/8] Cleaning up previous installations..."
sudo systemctl stop vpn_bot.service >/dev/null 2>&1 || true
sudo systemctl disable vpn_bot.service >/dev/null 2>&1 || true
sudo rm -f /etc/systemd/system/vpn_bot.service
sudo rm -rf /opt/vpn_bot
sudo systemctl daemon-reload
echo "[2/8] Installing dependencies..."
sudo apt-get update && sudo apt-get install -y python3 python3-pip git python3-venv
echo "[3/8] Please provide your bot and panel details:"
read -p "Enter your Telegram Bot Token: " TELEGRAM_BOT_TOKEN
read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
read -p "Enter your Hiddify API Key (from panel settings): " HIDDIFY_API_KEY
INSTALL_DIR="/opt/vpn_bot"
echo "[4/8] Cloning repository..."
sudo git clone https://github.com/Mohammad1724/vpn_bot.git $INSTALL_DIR
echo "[5/8] Creating config.py file..."
sudo bash -c "cat > $INSTALL_DIR/config.py" <<EOL
# config.py
TELEGRAM_BOT_TOKEN = "$TELEGRAM_BOT_TOKEN"
ADMIN_ID = $ADMIN_ID
HIDDIFY_DOMAIN = "mrm33.iranshop21.monster"
HIDDIFY_PATH = "UA3jz9Ii21F7IHIxm5"
HIDDIFY_API_KEY = "$HIDDIFY_API_KEY"
EOL
echo "[6/8] Creating Python virtual environment..."
sudo python3 -m venv $INSTALL_DIR/venv
if [ ! -f "$INSTALL_DIR/venv/bin/python" ]; then echo "ERROR: Failed to create venv." && exit 1; fi
sudo $INSTALL_DIR/venv/bin/pip install --upgrade pip
sudo $INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt
echo "[7/8] Creating systemd service..."
SERVICE_NAME="vpn_bot.service"
PYTHON_EXEC="$INSTALL_DIR/venv/bin/python"
MAIN_SCRIPT="$INSTALL_DIR/main.py"
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
sudo chown -R root:root $INSTALL_DIR && sudo chmod -R 755 $INSTALL_DIR
echo "[8/8] Starting the service..."
sudo systemctl daemon-reload && sudo systemctl enable $SERVICE_NAME && sudo systemctl start $SERVICE_NAME
echo "================================================="
echo "      ✅ Installation successful! ✅"
echo "To check status: sudo systemctl status $SERVICE_NAME"
echo "To view logs:   sudo journalctl -u $SERVICE_NAME -f"
echo "================================================="