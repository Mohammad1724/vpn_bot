#!/bin/bash

# اسکریپت نصب تعاملی و خودکار ربات فروش VPN

# --- متغیرها و رنگ‌ها ---
INSTALL_DIR="/root/vpn_bot"
SERVICE_NAME="vpn_bot.service"
REPO_URL="https://github.com/Mohammad1724/vpn_bot.git" # آدرس ریپازیتوری شما
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# --- بررسی دسترسی root ---
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}خطا: این اسکریپت باید با دسترسی root اجرا شود.${NC}"
  exit 1
fi

# --- تابع برای پرسیدن سوالات ---
ask_question() {
    local question=$1
    local variable_name=$2
    echo -e -n "${YELLOW}$question ${NC}"
    read -r "$variable_name"
}

echo -e "${GREEN}--- شروع فرآیند نصب تعاملی ربات ---${NC}"

# --- مرحله ۱: نصب پیش‌نیازهای سیستمی ---
echo -e "\n${YELLOW}مرحله ۱: نصب پیش‌نیازهای سیستمی (git, python3-pip)...${NC}"
apt update > /dev/null 2>&1
apt install -y git python3-pip > /dev/null 2>&1
echo -e "${GREEN}پیش‌نیازها با موفقیت نصب شدند.${NC}"

# --- مرحله ۲: دانلود فایل‌های ربات ---
echo -e "\n${YELLOW}مرحله ۲: دانلود فایل‌های ربات از گیت‌هاب...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}پوشه نصب ($INSTALL_DIR) از قبل وجود دارد. در حال حذف نسخه قبلی...${NC}"
    # ابتدا سرویس قبلی را متوقف و غیرفعال می‌کنیم
    systemctl stop "$SERVICE_NAME" > /dev/null 2>&1
    systemctl disable "$SERVICE_NAME" > /dev/null 2>&1
    rm -rf "$INSTALL_DIR"
fi
git clone "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR" || exit
echo -e "${GREEN}فایل‌های ربات با موفقیت دانلود شدند.${NC}"

# --- مرحله ۳: نصب پکیج‌های پایتون ---
echo -e "\n${YELLOW}مرحله ۳: نصب پکیج‌های مورد نیاز پایتون...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}تمام پکیج‌ها با موفقیت نصب شدند.${NC}"

# --- مرحله ۴: دریافت اطلاعات از کاربر و ساخت فایل .env ---
echo -e "\n${YELLOW}مرحله ۴: لطفاً اطلاعات زیر را برای ساخت فایل .env وارد کنید:${NC}"
ask_question "توکن ربات تلگرام خود را وارد کنید (از @BotFather):" TOKEN
ask_question "آیدی عددی ادمین را وارد کنید (از @userinfobot):" ADMIN_ID
ask_question "قیمت پیش‌فرض کانفیگ را وارد کنید (مثلا 50,000):" CONFIG_PRICE
ask_question "شماره کارت خود را وارد کنید (مثلا 6037-xxxx-xxxx-xxxx):" CARD_NUMBER
ask_question "نام کامل صاحب حساب را وارد کنید:" CARD_HOLDER

# ساخت فایل .env
cat > .env << EOF
TOKEN="$TOKEN"
ADMIN_ID="$ADMIN_ID"
CONFIG_PRICE="$CONFIG_PRICE"
CARD_NUMBER="$CARD_NUMBER"
CARD_HOLDER="$CARD_HOLDER"
EOF
echo -e "${GREEN}فایل .env با موفقیت ساخته شد.${NC}"
touch configs.txt # ایجاد فایل خالی کانفیگ‌ها

# --- مرحله ۵: ساخت و راه‌اندازی سرویس systemd ---
echo -e "\n${YELLOW}مرحله ۵: ساخت و راه‌اندازی سرویس systemd برای اجرای دائمی ربات...${NC}"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME"
cat > "$SERVICE_FILE_PATH" << EOF
[Unit]
Description=VPN Bot Service (Card-to-Card Version)
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"
echo -e "${GREEN}سرویس ربات با موفقیت ساخته و اجرا شد.${NC}"

# --- مرحله ۶: نمایش وضعیت نهایی ---
echo -e "\n${YELLOW}مرحله ۶: بررسی وضعیت نهایی سرویس...${NC}"
# چند ثانیه صبر می‌کنیم تا سرویس زمان کافی برای اجرا داشته باشد
sleep 5
systemctl status "$SERVICE_NAME"

echo -e "\n\n${GREEN}--- نصب و راه‌اندازی با موفقیت به پایان رسید! ---${NC}"
echo -e "ربات شما اکنون در پس‌زمینه در حال اجراست."
echo -e "برای مدیریت ربات (مثلاً مشاهده لاگ‌ها) از دستورات زیر استفاده کنید:"
echo -e " - توقف ربات: ${YELLOW}systemctl stop $SERVICE_NAME${NC}"
echo -e " - شروع ربات: ${YELLOW}systemctl start $SERVICE_NAME${NC}"
echo -e " - ری‌استارت ربات: ${YELLOW}systemctl restart $SERVICE_NAME${NC}"
echo -e " - مشاهده لاگ‌ها: ${YELLOW}journalctl -u $SERVICE_NAME -f${NC}"