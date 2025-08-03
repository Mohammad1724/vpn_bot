#!/bin/bash

# ==============================================================================
# اسکریپت نصب تعاملی و خودکار ربات فروش VPN
# نسخه: 3.0 (شامل ساخت خودکار اسکریپت‌های restore و uninstall)
# ==============================================================================

# --- متغیرها و رنگ‌ها ---
INSTALL_DIR="/root/vpn_bot"
SERVICE_NAME="vpn_bot.service"
REPO_URL="https://github.com/Mohammad1724/vpn_bot.git" # آدرس ریپازیتوری شما
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- توابع برای نمایش پیام‌ها ---
log_info() { echo -e "${GREEN}$1${NC}"; }
log_warn() { echo -e "${YELLOW}$1${NC}"; }
log_error() { echo -e "${RED}$1${NC}"; }

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
log_warn "\nمرحله ۱: نصب پیش‌نیازهای سیستمی (git, python3-pip, python3-venv, unzip)..."
apt-get update > /dev/null 2>&1
apt-get install -y git python3-pip python3-venv unzip > /dev/null 2>&1
log_info "پیش‌نیازها با موفقیت نصب شدند."

# --- مرحله ۲: دانلود فایل‌های ربات ---
log_warn "\nمرحله ۲: دانلود فایل‌های ربات از گیت‌هاب..."
if [ -d "$INSTALL_DIR" ]; then
    log_warn "پوشه نصب ($INSTALL_DIR) از قبل وجود دارد. در حال حذف کامل نسخه قبلی..."
    systemctl stop "$SERVICE_NAME" > /dev/null 2>&1
    systemctl disable "$SERVICE_NAME" > /dev/null 2>&1
    rm -f "/etc/systemd/system/$SERVICE_NAME"
    rm -rf "$INSTALL_DIR"
    log_info "نسخه قبلی با موفقیت حذف شد."
fi
git clone "$REPO_URL" "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    log_error "خطا در دانلود فایل‌ها از گیت‌هاب."
    exit 1
fi
cd "$INSTALL_DIR" || exit
log_info "فایل‌های ربات با موفقیت در مسیر $INSTALL_DIR دانلود شدند."

# --- مرحله ۳: ساخت محیط مجازی و نصب پکیج‌ها ---
log_warn "\nمرحله ۳: ساخت محیط مجازی و نصب پکیج‌های پایتون..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    log_error "خطا در نصب پکیج‌های پایتون."
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
# مقدار پیش‌فرض برای نام صاحب حساب (برای جلوگیری از خطای انکودینگ)
CARD_HOLDER="تنظیم نشده"

cat > .env << EOF
TOKEN="$TOKEN"
ADMIN_ID="$ADMIN_ID"
CARD_NUMBER="$CARD_NUMBER"
CARD_HOLDER="$CARD_HOLDER"
EOF
log_info "فایل .env با موفقیت ساخته شد."

# --- مرحله ۵: ساخت اسکریپت‌های مدیریتی (restore.sh و uninstall.sh) ---
log_warn "\nمرحله ۵: ساخت اسکریپت‌های مدیریتی..."

# ساخت اسکریپت restore.sh
cat > restore.sh << 'EOF'
#!/bin/bash
SERVICE_NAME="vpn_bot.service"
INSTALL_DIR="/root/vpn_bot"
BACKUP_FILE_PATH="/root/vpn_bot/backup_to_restore.zip"

echo "شروع فرآیند بازیابی..."
echo "متوقف کردن سرویس ربات..."
systemctl stop "$SERVICE_NAME"
sleep 2

if [ -f "$BACKUP_FILE_PATH" ]; then
    echo "حذف داده‌های قدیمی..."
    rm -f "$INSTALL_DIR/bot_database.db"
    rm -rf "$INSTALL_DIR/plan_configs"
    
    echo "استخراج فایل بکاپ..."
    unzip -o "$BACKUP_FILE_PATH" -d "$INSTALL_DIR/"
    rm "$BACKUP_FILE_PATH"
    echo "فایل‌ها با موفقیت جایگزین شدند."
else
    echo "خطا: فایل بکاپ پیدا نشد."
    systemctl start "$SERVICE_NAME"
    exit 1
fi

echo "راه‌اندازی مجدد سرویس ربات..."
systemctl start "$SERVICE_NAME"
sleep 3
echo "فرآیند بازیابی به پایان رسید."
EOF

# ساخت اسکریپت uninstall.sh
cat > uninstall.sh << 'EOF'
#!/bin/bash
SERVICE_NAME="vpn_bot.service"
INSTALL_DIR="/root/vpn_bot"

echo "شروع فرآیند حذف کامل ربات..."

echo "مرحله ۱: توقف و غیرفعال کردن سرویس systemd..."
systemctl stop "$SERVICE_NAME"
systemctl disable "$SERVICE_NAME"
echo "سرویس متوقف و غیرفعال شد."

echo "مرحله ۲: حذف فایل سرویس..."
rm -f "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
echo "فایل سرویس حذف شد."

echo "مرحله ۳: حذف پوشه پروژه..."
rm -rf "$INSTALL_DIR"
echo "پوشه پروژه ($INSTALL_DIR) حذف شد."

echo "--- ربات با موفقیت به طور کامل حذف شد. ---"
EOF

chmod +x restore.sh uninstall.sh
log_info "اسکریپت‌های restore.sh و uninstall.sh با موفقیت ساخته شدند."

# --- مرحله ۶: ساخت و راه‌اندازی سرویس systemd ---
log_warn "\nمرحله ۶: ساخت و راه‌اندازی سرویس systemd..."
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
log_info "سرویس ربات با نام '$SERVICE_NAME' با موفقیت ساخته و اجرا شد."

# --- مرحله ۷: نمایش وضعیت نهایی ---
log_warn "\nمرحله ۷: بررسی وضعیت نهایی سرویس..."
sleep 5
systemctl status "$SERVICE_NAME"

log_info "\n================================================="
log_info "--- نصب و راه‌اندازی با موفقیت به پایان رسید! ---"
log_info "================================================="
log_warn "\n*** اقدام مهم بعدی ***"
log_info "لطفاً به ربات خود بروید، دکمه «تنظیمات پرداخت» را بزنید و «نام صاحب حساب» را به فارسی تنظیم کنید."
log_info "برای حذف کامل ربات در آینده، به پوشه /root/vpn_bot رفته و دستور './uninstall.sh' را اجرا کنید."