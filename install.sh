#!/bin/bash

# --- Script for Installing the Hiddify VPN Bot ---
# Version 3: Using Python Virtual Environment for reliability

echo "======================================================"
echo " Hiddify VPN Bot Installer by Gemini (v3 - venv)"
echo "======================================================"

# 1. Update system and install dependencies
echo ">>> Updating system and installing dependencies (python3, pip, git, venv)..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip git python3.10-venv # Use python3.10-venv for Debian/Ubuntu

# 2. Get User Input for Config
echo ">>> Please provide your bot and panel details:"
read -p "Enter your Telegram Bot Token: " TELEGRAM_BOT_TOKEN
read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
read -p "Enter your Hiddify Panel Domain (e.g., panel.example.com): " HIDDIFY_DOMAIN
read -p "Enter your Hiddify Proxy Path: " HIDDIFY_PATH
read -p "Enter your Hiddify Admin UUID: " HIDDIFY_ADMIN_UUID

# 3. Clone or update the repository
INSTALL_DIR="/opt/vpn_bot"
if [ -d "$INSTALL_DIR" ]; then
    echo ">>> Found existing installation. Pulling latest changes..."
    sudo git -C $INSTALL_DIR pull
else
    echo ">>> Cloning repository into $INSTALL_DIR..."
    sudo git clone https://github.com/Mohammad1724/vpn_bot.git $INSTALL_DIR
fi

# 4. Create the config.py file
echo ">>> Creating config.py..."
sudo bash -c "cat > $INSTALL_DIR/config.py" <<EOL
# config.py
TELEGRAM_BOT_TOKEN = "$TELEGRAM_BOT_TOKEN"
ADMIN_ID = $ADMIN_ID
HIDDIFY_DOMAIN = "$HIDDIFY_DOMAIN"
HIDDIFY_PATH = "$HIDDIFY_PATH"
HIDDIFY_ADMIN_UUID = "$HIDDIFY_ADMIN_UUID"
EOL

# 5. Create a Python virtual environment
echo ">>> Creating Python virtual environment in $INSTALL_DIR/venv..."
sudo python3 -m venv $INSTALL_DIR/venv

# 6. Install Python libraries INSIDE the virtual environment
echo ">>> Installing required Python libraries into the venv..."
sudo $INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt

# 7. Create a systemd service file to run the bot 24/7
SERVICE_NAME="vpn_bot.service"
# The ExecStart path is now pointing to the python executable INSIDE the venv
PYTHON_EXEC="$INSTALL_DIR/venv/bin/python"
echo ">>> Creating systemd service file: $SERVICE_NAME..."
sudo bash -c "cat > /etc/systemd/system/$SERVICE_NAME" <<EOL
[Unit]
Description=Telegram VPN Bot for Hiddify
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_EXEC $INSTALL_DIR/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# 8. Enable and start the service
echo ">>> Reloading, enabling, and restarting the bot service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

echo "======================================================"
echo "Installation/Update complete!"
echo "Your bot is now running using a dedicated virtual environment."
echo "To check the status, use: sudo systemctl status $SERVICE_NAME"
echo "To see the logs, use: sudo journalctl -u $SERVICE_NAME -f"
echo "======================================================"