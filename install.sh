#!/bin/bash

# --- Script for Installing the Hiddify VPN Bot ---

echo "================================================="
echo "     Hiddify VPN Bot Installer by Gemini"
echo "================================================="

# 1. Update system and install dependencies
echo ">>> Updating system and installing dependencies (python3, pip, git)..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip git

# 2. Get User Input for Config
echo ">>> Please provide your bot and panel details:"
read -p "Enter your Telegram Bot Token: " TELEGRAM_BOT_TOKEN
read -p "Enter your numeric Telegram Admin ID: " ADMIN_ID
read -p "Enter your Hiddify Panel Domain (e.g., panel.example.com): " HIDDIFY_DOMAIN
read -p "Enter your Hiddify Proxy Path: " HIDDIFY_PATH
read -p "Enter your Hiddify Admin UUID: " HIDDIFY_ADMIN_UUID

# 3. Clone the repository
INSTALL_DIR="/opt/vpn_bot"
echo ">>> Cloning repository into $INSTALL_DIR..."
sudo git clone https://github.com/Mohammad1724/vpn_bot.git $INSTALL_DIR

# 4. Create the config.py file from user input
echo ">>> Creating config.py..."
sudo bash -c "cat > $INSTALL_DIR/config.py" <<EOL
# config.py
TELEGRAM_BOT_TOKEN = "$TELEGRAM_BOT_TOKEN"
ADMIN_ID = $ADMIN_ID
HIDDIFY_DOMAIN = "$HIDDIFY_DOMAIN"
HIDDIFY_PATH = "$HIDDIFY_PATH"
HIDDIFY_ADMIN_UUID = "$HIDDIFY_ADMIN_UUID"
EOL

# 5. Install Python libraries
echo ">>> Installing required Python libraries..."
sudo pip3 install -r $INSTALL_DIR/requirements.txt

# 6. Create a systemd service file to run the bot 24/7
SERVICE_NAME="vpn_bot.service"
echo ">>> Creating systemd service file: $SERVICE_NAME..."
sudo bash -c "cat > /etc/systemd/system/$SERVICE_NAME" <<EOL
[Unit]
Description=Telegram VPN Bot for Hiddify
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# 7. Enable and start the service
echo ">>> Enabling and starting the bot service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

echo "================================================="
echo "Installation complete!"
echo "Your bot is now running as a background service."
echo "To check the status, use: sudo systemctl status $SERVICE_NAME"
echo "To see the logs, use: sudo journalctl -u $SERVICE_NAME -f"
echo "================================================="