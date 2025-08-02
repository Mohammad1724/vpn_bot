#!/bin/bash

# اسکریپت نصب خودکار ربات فروش VPN
# این اسکریپت ربات را در مسیر /root/vpn_bot نصب می‌کند.

# --- متغیرها و رنگ‌ها ---
INSTALL_DIR="/root/vpn_bot"
REPO_URL="https://github.com/Mohammad1724/vpn_bot.git"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- بررسی اجرای اسکریپت با دسترسی root ---
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}خطا: این اسکریپت باید با دسترسی root اجرا شود.${NC}"
  echo "لطفاً آن را با دستور 'sudo ./install.sh' اجرا کنید."
  exit 1
fi

echo -e "${GREEN}--- شروع فرآیند نصب ربات فروش VPN ---${NC}"

# --- نصب پیش‌نیازهای سیستمی ---
echo -e "\n${YELLOW}مرحله ۱: نصب پیش‌نیازهای سیستمی (git, python3-pip, python3-venv)...${NC}"
apt update > /dev/null 2>&1
apt install -y git python3-pip python3-venv > /dev/null 2>&1
echo -e "${GREEN}پیش‌نیازها با موفقیت نصب شدند.${NC}"

# --- کلون کردن پروژه از گیت‌هاب ---
echo -e "\n${YELLOW}مرحله ۲: دانلود فایل‌های ربات از گیت‌هاب...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}پوشه نصب ($INSTALL_DIR) از قبل وجود دارد. آیا می‌خواهید آن را حذف کرده و از نو نصب کنید؟ (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        rm -rf "$INSTALL_DIR"
        echo -e "${GREEN}پوشه قبلی حذف شد.${NC}"
    else
        echo -e "${RED}نصب متوقف شد.${NC}"
        exit 1
    fi
fi
git clone "$REPO_URL" "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    echo -e "${RED}خطا در دانلود فایل‌ها از گیت‌هاب. لطفاً اتصال اینترنت و آدرس ریپازیتوری را بررسی کنید.${NC}"
    exit 1
fi
echo -e "${GREEN}فایل‌های ربات با موفقیت در مسیر $INSTALL_DIR دانلود شدند.${NC}"

cd "$INSTALL_DIR" || exit

# --- ساخت و فعال‌سازی محیط مجازی پایتون ---
echo -e "\n${YELLOW}مرحله ۳: ساخت محیط مجازی پایتون (venv)...${NC}"
python3 -m venv venv
source venv/bin/activate
echo -e "${GREEN}محیط مجازی ساخته و فعال شد.${NC}"

# --- نصب پکیج‌های پایتون ---
echo -e "\n${YELLOW}مرحله ۴: نصب پکیج‌های مورد نیاز پایتون...${NC}"
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}خطا در نصب پکیج‌های پایتون. لطفاً فایل requirements.txt را بررسی کنید.${NC}"
    deactivate
    exit 1
fi
echo -e "${GREEN}تمام پکیج‌ها با موفقیت نصب شدند.${NC}"

# --- آماده‌سازی فایل‌های تنظیمات ---
echo -e "\n${YELLOW}مرحله ۵: آماده‌سازی فایل‌های تنظیمات...${NC}"
cp .env.example .env
touch configs.txt
echo -e "${GREEN}فایل .env برای تنظیمات و configs.txt برای کانفیگ‌ها ایجاد شد.${NC}"

echo -e "\n\n${GREEN}--- نصب با موفقیت به پایان رسید! ---${NC}"
echo -e "\n${YELLOW}اقدامات بعدی:${NC}"
echo -e "1. وارد پوشه ربات شوید: ${GREEN}cd $INSTALL_DIR${NC}"
echo -e "2. فایل .env را با اطلاعات خود ویرایش کنید: ${GREEN}nano .env${NC}"
echo -e "3. کانفیگ‌های خود را در فایل configs.txt قرار دهید (هر کدام در یک خط): ${GREEN}nano configs.txt${NC}"
echo -e "4. ربات را با دستور زیر اجرا کنید (ابتدا محیط مجازی را فعال کنید):"
echo -e "   ${GREEN}source venv/bin/activate${NC}"
echo -e "   ${GREEN}gunicorn --workers 4 --bind 0.0.0.0:8080 main:app --log-level info${NC}"
echo -e "\nفراموش نکنید که وب‌سرور (مانند Nginx) را برای دامنه خود تنظیم کنید."

deactivate
