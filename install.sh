#!/bin/bash

# =================================================================
# Hiddify Bot Manager
# A comprehensive script for installing, updating, and managing the bot.
# =================================================================

# --- Configuration ---
PROJECT_NAME="vpn_bot"
GITHUB_REPO="https://github.com/Mohammad1724/vpn_bot.git" # Your repository
INSTALL_DIR="/opt/vpn_bot"
SERVICE_NAME="${PROJECT_NAME}.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

# --- Colors for better output ---
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_BLUE='\033[0;34m'

# --- Helper Functions ---
print_color() {
    echo -e "${!1}${2}${C_RESET}"
}

check_root() {
    if [ "$(id -u)" -ne "0" ]; then
        print_color "C_YELLOW" "این اسکریپت به دسترسی root نیاز دارد. در حال اجرای مجدد با sudo..."
        # Re-execute the script with sudo, passing all original arguments
        exec sudo bash "$0" "$@"
        exit 1
    fi
}

# --- Pre-execution check ---
check_root

# --- Check if bot is installed ---
is_installed() {
    if [ -d "$INSTALL_DIR" ] && [ -f "$SERVICE_FILE" ]; then
        return 0 # True
    else
        return 1 # False
    fi
}

# --- Core Management Functions ---

function install_bot() {
    print_color "C_BLUE" "--- شروع نصب ربات Hiddify ---"

    if is_installed; then
        print_color "C_YELLOW" "ربات از قبل نصب شده است."
        read -p "آیا می‌خواهید نسخه موجود را حذف و مجدداً نصب کنید؟ (تمام داده‌های قبلی حذف خواهد شد) [y/N]: " REINSTALL_CONFIRM
        if [[ "$REINSTALL_CONFIRM" =~ ^[Yy]$ ]]; then
            uninstall_bot_silent
        else
            print_color "C_YELLOW" "عملیات نصب توسط کاربر لغو شد."
            return
        fi
    fi

    # 1. Install required system packages
    print_color "C_YELLOW" "[1/6] در حال نصب نیازمندی‌های سیستم (git, python3, pip, venv)..."
    apt-get update > /dev/null 2>&1
    apt-get install -y git python3 python3-pip python3-venv > /dev/null 2>&1
    print_color "C_GREEN" "نیازمندی‌های سیستم نصب شد."

    # 2. Clone the repository
    print_color "C_YELLOW" "[2/6] در حال دریافت سورس ربات از گیت‌هاب..."
    git clone "$GITHUB_REPO" "$INSTALL_DIR" > /dev/null 2>&1
    print_color "C_GREEN" "سورس ربات در مسیر $INSTALL_DIR کلون شد."

    # Change to the project directory
    cd "$INSTALL_DIR"

    # 3. Set up Python virtual environment and install packages
    print_color "C_YELLOW" "[3/6] در حال ساخت محیط مجازی پایتون..."
    python3 -m venv venv
    print_color "C_YELLOW" "در حال نصب پکیج‌های پایتون از requirements.txt..."
    source venv/bin/activate
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt > /dev/null 2>&1
    deactivate
    print_color "C_GREEN" "محیط مجازی پایتون آماده شد."

    # 4. Create and populate the configuration file
    print_color "C_YELLOW" "[4/6] در حال ایجاد فایل کانفیگ (src/config.py)..."
    CONFIG_FILE="src/config.py"
    cp src/config_template.py "$CONFIG_FILE"

    print_color "C_BLUE" "لطفاً اطلاعات زیر را برای تنظیم ربات وارد کنید:"
    read -p "توکن ربات تلگرام خود را وارد کنید: " BOT_TOKEN
    read -p "آیدی عددی ادمین تلگرام را وارد کنید: " ADMIN_ID
    read -p "نام کاربری پشتیبانی تلگرام (بدون @) را وارد کنید: " SUPPORT_USERNAME

    print_color "C_BLUE" "اطلاعات پنل Hiddify:"
    read -p "دامنه پنل را وارد کنید (مثال: mypanel.com): " PANEL_DOMAIN
    read -p "مسیر ادمین پنل Hiddify را وارد کنید: " ADMIN_PATH
    read -p "مسیر لینک اشتراک Hiddify را وارد کنید (می‌تواند با مسیر ادمین یکی باشد): " SUB_PATH
    read -p "کلید API پنل Hiddify (در صورت استفاده، وگرنه خالی بگذارید): " API_KEY

    # Apply configurations using sed
    sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"${BOT_TOKEN}\"|" "$CONFIG_FILE"
    sed -i "s|^ADMIN_ID = .*|ADMIN_ID = ${ADMIN_ID}|" "$CONFIG_FILE"
    sed -i "s|^SUPPORT_USERNAME = .*|SUPPORT_USERNAME = \"${SUPPORT_USERNAME}\"|" "$CONFIG_FILE"
    sed -i "s|^PANEL_DOMAIN = .*|PANEL_DOMAIN = \"${PANEL_DOMAIN}\"|" "$CONFIG_FILE"
    sed -i "s|^ADMIN_PATH = .*|ADMIN_PATH = \"${ADMIN_PATH}\"|" "$CONFIG_FILE"
    sed -i "s|^SUB_PATH = .*|SUB_PATH = \"${SUB_PATH}\"|" "$CONFIG_FILE"
    # Only set API_KEY if it's provided
    if [ -n "$API_KEY" ]; then
        sed -i "s|^API_KEY = .*|API_KEY = \"${API_KEY}\"|" "$CONFIG_FILE"
    fi
    print_color "C_GREEN" "فایل کانفیگ با موفقیت ایجاد شد."

    # 5. Create the systemd service
    print_color "C_YELLOW" "[5/6] در حال ایجاد سرویس systemd..."
    cat > "$SERVICE_FILE" << EOL
[Unit]
Description=Hiddify Telegram Bot (${PROJECT_NAME})
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}/src
ExecStart=${INSTALL_DIR}/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOL
    print_color "C_GREEN" "فایل سرویس در مسیر $SERVICE_FILE ایجاد شد."

    # 6. Enable and start the service
    print_color "C_YELLOW" "[6/6] در حال فعال‌سازی و اجرای سرویس ربات..."
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"

    print_color "C_GREEN" "\n--- نصب با موفقیت انجام شد! ---"
    print_color "C_BLUE" "ربات هم اکنون به عنوان یک سرویس در حال اجرا است."
    echo "برای بررسی وضعیت از دستور زیر استفاده کنید: ${C_YELLOW}systemctl status ${SERVICE_NAME}${C_RESET}"
}

function update_bot() {
    if ! is_installed; then
        print_color "C_RED" "خطا: ربات نصب نشده است. لطفاً ابتدا گزینه ۱ را برای نصب انتخاب کنید."
        return
    fi
    print_color "C_BLUE" "--- شروع به‌روزرسانی ربات ---"
    
    cd "$INSTALL_DIR"
    print_color "C_YELLOW" "[1/3] در حال دریافت آخرین تغییرات از گیت‌هاب..."
    git pull
    
    print_color "C_YELLOW" "[2/3] در حال به‌روزرسانی پکیج‌های پایتون..."
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    
    print_color "C_YELLOW" "[3/3] در حال راه‌اندازی مجدد سرویس ربات..."
    systemctl restart "$SERVICE_NAME"
    
    print_color "C_GREEN" "--- به‌روزرسانی با موفقیت انجام شد! ---"
}

function show_status() {
    if ! is_installed; then
        print_color "C_RED" "خطا: ربات نصب نشده است."
        return
    fi
    print_color "C_BLUE" "--- وضعیت سرویس ربات ---"
    systemctl status "$SERVICE_NAME"
}

function show_live_logs() {
    if ! is_installed; then
        print_color "C_RED" "خطا: ربات نصب نشده است."
        return
    fi
    print_color "C_BLUE" "--- نمایش لاگ‌های لحظه‌ای (برای خروج CTRL+C را بزنید) ---"
    journalctl -u "$SERVICE_NAME" -f
}

function show_all_logs() {
    if ! is_installed; then
        print_color "C_RED" "خطا: ربات نصب نشده است."
        return
    fi
    print_color "C_BLUE" "--- نمایش تمام لاگ‌های ربات ---"
    journalctl -u "$SERVICE_NAME"
}

function restart_bot() {
    if ! is_installed; then
        print_color "C_RED" "خطا: ربات نصب نشده است."
        return
    fi
    print_color "C_BLUE" "--- در حال راه‌اندازی مجدد سرویس ربات ---"
    systemctl restart "$SERVICE_NAME"
    print_color "C_GREEN" "سرویس ربات با موفقیت راه‌اندازی مجدد شد."
    sleep 2
    show_status
}

function uninstall_bot() {
    if ! is_installed; then
        print_color "C_RED" "خطا: ربات از قبل نصب نشده است."
        return
    fi
    
    print_color "C_RED" "!!! هشدار حذف کامل !!!"
    read -p "آیا مطمئن هستید که می‌خواهید ربات را به طور کامل حذف کنید؟ (این عملیات غیرقابل بازگشت است) [y/N]: " UNINSTALL_CONFIRM
    if [[ "$UNINSTALL_CONFIRM" =~ ^[Yy]$ ]]; then
        uninstall_bot_silent
        print_color "C_GREEN" "--- ربات با موفقیت حذف شد. ---"
    else
        print_color "C_YELLOW" "عملیات حذف توسط کاربر لغو شد."
    fi
}

function uninstall_bot_silent() {
    print_color "C_YELLOW" "در حال توقف و غیرفعال کردن سرویس..."
    systemctl stop "$SERVICE_NAME" &>/dev/null || true
    systemctl disable "$SERVICE_NAME" &>/dev/null || true
    
    print_color "C_YELLOW" "در حال حذف فایل سرویس..."
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    
    print_color "C_YELLOW" "در حال حذف پوشه نصب ربات..."
    rm -rf "$INSTALL_DIR"
}

function show_menu() {
    clear
    print_color "C_BLUE" "=========================================="
    print_color "C_BLUE" "          Hiddify Bot Manager"
    print_color "C_BLUE" "=========================================="
    echo ""
    print_color "C_GREEN" "1. نصب یا نصب مجدد ربات (Install/Reinstall)"
    print_color "C_GREEN" "2. به‌روزرسانی ربات (Update)"
    print_color "C_GREEN" "3. نمایش وضعیت ربات (Status)"
    print_color "C_GREEN" "4. نمایش لاگ‌های لحظه‌ای (Live Logs)"
    print_color "C_GREEN" "5. نمایش کل لاگ‌های ربات (All Logs)"
    print_color "C_GREEN" "6. راه‌اندازی مجدد ربات (Restart)"
    print_color "C_RED"   "7. حذف کامل ربات (Uninstall)"
    echo ""
    print_color "C_YELLOW" "0. خروج (Exit)"
    echo ""
}

# --- Main Logic ---
while true; do
    show_menu
    read -p "لطفا یک گزینه را انتخاب کنید [0-7]: " choice

    case $choice in
        1)
            install_bot
            ;;
        2)
            update_bot
            ;;
        3)
            show_status
            ;;
        4)
            show_live_logs
            ;;
        5)
            show_all_logs
            ;;
        6)
            restart_bot
            ;;
        7)
            uninstall_bot
            ;;
        0)
            print_color "C_BLUE" "خروج از برنامه."
            exit 0
            ;;
        *)
            print_color "C_RED" "گزینه نامعتبر است. لطفاً عددی بین 0 تا 7 وارد کنید."
            ;;
    esac
    
    if [[ "$choice" != "0" ]]; then
        read -p $'\nبرای بازگشت به منوی اصلی، کلید Enter را فشار دهید...'
    fi
done