#!/bin/bash

# اسکریپت نصب نهایی ربات فروش VPN

INSTALL_DIR="/root/vpn_bot"
SERVICE_NAME="vpn_bot.service"
REPO_URL="https://github.com/Mohammad1724/vpn_bot.git"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}خطا: این اسکریپت باید با دسترسی root اجرا شود.${NC}"
  exit 1
fi

echo -e "${GREEN}--- شروع فرآیند نصب نهایی ربات ---${NC}"

# نصب پیش‌نیازها
echo -e "\n${YELLOW}مرحله ۱: نصب پیش‌نیازها...${NC}"
apt-get update > /dev/null 2>&1
apt-get install -y git python3-pip python3-venv > /dev/null 2>&1

# دانلود فایل‌ها
echo -e "\n${YELLOW}مرحله ۲: دانلود فایل‌های ربات...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    systemctl stop "$SERVICE_NAME" > /dev/null 2>&1
    systemctl disable "$SERVICE_NAME" > /dev/null 2>&1
    rm -rf "$INSTALL_DIR"
fi
git clone "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR" || exit

# ساخت محیط مجازی و نصب پکیج‌ها
echo -e "\n${YELLOW}مرحله ۳: نصب پکیج‌های پایتون...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
deactivate

# دریافت اطلاعات از کاربر
echo -e "\n${YELLOW}مرحله ۴: لطفاً اطلاعات زیر را وارد کنید:${NC}"
read -p "توکن ربات تلگرام: " TOKEN
read -p "آیدی عددی ادمین: " ADMIN_ID
read -p "شماره کارت: " CARD_NUMBER

# ساخت فایل .env
cat > .env << EOF
TOKEN="$TOKEN"
ADMIN_ID="$ADMIN_ID"
CARD_NUMBER="$CARD_NUMBER"
CARD_HOLDER="تنظیم نشده"
EOF
echo -e "${GREEN}فایل .env با موفقیت ساخته شد.${NC}"

# ساخت و راه‌اندازی سرویس systemd
echo -e "\n${YELLOW}مرحله ۵: ساخت و راه‌اندازی سرویس...${NC}"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME"
PYTHON_EXEC="$INSTALL_DIR/venv/bin/python3"
cat > "$SERVICE_FILE_PATH" << EOF
[Unit]
Description=VPN Bot Service (Final Version)
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_EXEC $INSTALL_DIR/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo -e "\n${YELLOW}مرحله ۶: بررسی وضعیت نهایی...${NC}"
sleep 5
systemctl status "$SERVICE_NAME"

echo -e "\n\n${GREEN}--- نصب با موفقیت به پایان رسید! ---${NC}"
echo -e "${YELLOW}*** اقدام مهم بعدی ***${NC}"
echo -e "لطفاً به ربات خود بروید، دکمه «تنظیمات پرداخت» را بزنید و «نام صاحب حساب» را به فارسی تنظیم کنید."