#!/bin/bash
# VPN Bot Installer

echo "🚀 نصب ربات فروش VPN..."

# نصب Python و pip
sudo apt update
sudo apt install -y python3 python3-pip

# نصب کتابخانه‌ها
pip3 install pyTelegramBotAPI

# ایجاد فایل .env
cat > .env << EOL
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
ADMIN_ID=YOUR_ADMIN_ID_HERE
CARD_NUMBER=6037-xxxx-xxxx-xxxx
CARD_HOLDER=نام صاحب کارت
EOL

echo "✅ نصب کامل شد!"
echo "⚠️ لطفا فایل .env را ویرایش کنید"
echo "▶️ برای اجرا: python3 vpn_bot.py"
