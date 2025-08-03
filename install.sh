#!/bin/bash

# ==============================================================================
# اسکریپت نصب تعاملی و خودکار ربات فروش VPN
# نسخه: 2.0 (سازگار با پایگاه داده SQLite و مدیریت پیشرفته)
# ==============================================================================

# --- متغیرها و رنگ‌ها ---
INSTALL_DIR="/root/vpn_bot"
SERVICE_NAME="vpn_bot.service"
REPO_URL="https://github.com/Mohammad1724/vpn_bot.git" # آدرس ریپازیتوری شما
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- تابع برای نمایش پیام‌های اطلاعاتی ---
log_info() {
    echo -e "${GREEN}$1${NC}"
}
log_warn() {
    echo -e "${YELLOW}$1${NC}"
}
log_error() {
    echo -e "${RED}$1${NC}"
}

# --- بررسی اجرای اسکریپت با دسترسی root ---
if [ "$EUID" -ne 0 ]; then
  log_error "خطا: این اسکریپت باید با دسترسی root اجرا شود."
  exit 1
fi

# --- تابع برای پرسیدن سوالات ---
ask_question() {
    local question=$1
    local variable_name=$2
    echo -e -n "${YELLOW}$question ${NC}"
    read -r "$variable_name"
}

log_info "=========================================="
log_info "--- شروع فرآیند نصب تعاملی ربات فروش VPN ---"
log_info "=========================================="

# --- مرحله ۱: نصب پیش‌نیازهای سیستمی ---
log_warn "\nمرحله ۱: نصب پیش‌نیازهای سیستمی (git, python3-pip, python3-venv)..."
apt-get update > /dev/null 2>&1
apt-get install -y git python3-pip python3-venv > /dev/null 2>&1
log_info "پیش‌نیازها با موفقیت نصب شدند."

# --- مرحله ۲: دانلود فایل‌های ربات ---
log_warn "\nمرحله ۲: دانلود فایل‌های ربات از گیت‌هاب..."
if [ -d "$INSTALL_DIR" ]; then
    log_warn "پوشه نصب ($INSTALL_DIR) از قبل وجود دارد. در حال حذف نسخه قبلی..."
    # ابتدا سرویس قبلی را متوقف و غیرفعال می‌کنیم
    systemctl stop "$SERVICE_NAME" > /dev/null 2>&1
    systemctl disable "$SERVICE_NAME" > /dev/null 2>&1
    rm -f "/etc/systemd/system/$SERVICE_NAME"
    rm -rf "$INSTALL_DIR"
    log_info "نسخه قبلی با موفقیت حذف شد."
fi
git clone "$REPO_URL" "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    log_error "خطا در دانلود فایل‌ها از گیت‌هاب. لطفاً اتصال اینترنت و آدرس ریپازیتوری را بررسی کنید."
    exit 1
fi
cd "$INSTALL_DIR" || exit
log_info "فایل‌های ربات با موفقیت در مسیر $INSTALL_DIR دانلود شدند."

# --- مرحله ۳: ساخت محیط مجازی و نصب پکیج‌ها ---
log_warn "\nمرحله ۳: ساخت محیط مجازی پایتون و نصب پکیج‌های مورد نیاز..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    log_error "خطا در نصب پکیج‌های پایتون. لطفاً فایل requirements.txt را بررسی کنید."
    deactivate
    exit 1
fi
deactivate
log_info "محیط مجازی ساخته و تمام پکیج‌ها با موفقیت نصب شدند."

# --- مرحله ۴: دریافت اطلاعات از کاربر و ساخت فایل .env ---
log_warn "\nمرحله ۴: لطفاً اطلاعات زیر را برای ساخت فایل .env وارد کنید:"
ask_question "توکن ربات تلگرام خود را وارد کنید (از @BotFather):" TOKEN
ask_question "آیدی عددی ادمین را وارد کنید (از @userinfobot):" ADMIN_ID
ask_question "شماره کارت خود را برای شارژ کیف پول وارد کنید:" CARD_NUMBER
ask_question "نام کامل صاحب حساب را وارد کنید:" CARD_HOLDER

# ساخت فایل .env با انکودینگ UTF-8
cat > .env << EOF
# Configuration file for VPN Bot
TOKEN="$TOKEN"
ADMIN_ID="$ADMIN_ID"
CARD_NUMBER="$CARD_NUMBER"
CARD_HOLDER="$CARD_HOLDER"
EOF
log_info "فایل .env با موفقیت ساخته شد."

# --- مرحله ۵: ساخت و راه‌اندازی سرویس systemd ---
log_warn "\nمرحله ۵: ساخت و راه‌اندازی سرویس systemd برای اجرای دائمی ربات..."
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME"
PYTHON_EXEC="$INSTALL_DIR/venv/bin/python3"
MAIN_PY_PATH="$INSTALL_DIR/main.py"

cat > "$SERVICE_FILE_PATH" << EOF
[Unit]
Description=VPN Bot Service (Advanced Version with DB)
After=network.target

[Service]
User=root
Group=root

Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_EXEC $MAIN_PY_PATH

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"
log_info "سرویس ربات با نام '$SERVICE_NAME' با موفقیت ساخته و اجرا شد."

# --- مرحله ۶: نمایش وضعیت نهایی ---
log_warn "\nمرحله ۶: بررسی وضعیت نهایی سرویس..."
# چند ثانیه صبر می‌کنیم تا سرویس زمان کافی برای اجرا داشته باشد
sleep 5
systemctl status "$SERVICE_NAME"

log_info "\n================================================="
log_info "--- نصب و راه‌اندازی با موفقیت به پایان رسید! ---"
log_info "================================================="
log_info "ربات شما اکنون در پس‌زمینه در حال اجراست."
log_info "برای مشاهده لاگ‌های زنده ربات، از دستور زیر استفاده کنید:"
log_warn "journalctl -u $SERVICE_NAME -f"