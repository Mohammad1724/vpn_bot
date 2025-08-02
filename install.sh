#!/bin/bash

echo "چه کاری می‌خواهید انجام دهید؟"
echo "1) نصب ربات"
echo "2) حذف کامل ربات و فایل‌ها"
read -p "شماره گزینه را وارد کنید (1 یا 2): " action < /dev/tty

if [ "$action" == "2" ]; then
    echo "در حال حذف فایل‌های ربات..."
    rm -f configs.json payments.json plans.json .env bot_log.txt
    rm -rf backups venv
    echo "همه فایل‌ها حذف شد."
    exit 0
elif [ "$action" == "1" ]; then
    echo "در حال نصب ربات..."
else
    echo "گزینه نامعتبر!"
    exit 1
fi

# گرفتن اطلاعات برای ساخت .env
read -p "توکن ربات تلگرام را وارد کنید: " BOT_TOKEN < /dev/tty
read -p "آیدی عددی ادمین (مثلاً 123456789): " ADMIN_ID < /dev/tty
read -p "شماره کارت (مثلاً 6037-XXXX-XXXX-XXXX): " CARD_NUMBER < /dev/tty

# ساخت فایل .env
cat > .env <<EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
CARD_NUMBER=$CARD_NUMBER
EOF

echo ".env ساخته شد."

# نصب pip اگر نصب نیست
if ! command -v pip &> /dev/null
then
    echo "pip پیدا نشد. در حال نصب pip..."
    apt update && apt install -y python3-pip
fi

# ساخت محیط مجازی
if [ ! -d "venv" ]; then
    echo "در حال ساخت محیط مجازی پایتون..."
    python3 -m venv venv
fi

# فعال‌سازی محیط مجازی و نصب پکیج‌ها
source venv/bin/activate
pip install --upgrade pip

# ساخت فایل requirements.txt اگر وجود ندارد
if [ ! -f "requirements.txt" ]; then
    echo "pyTelegramBotAPI
python-dotenv
qrcode" > requirements.txt
fi

pip install -r requirements.txt

echo "نصب پیش‌نیازها تمام شد."
echo "ربات در حال اجراست..."
python3 vpn_bot/vpn_bot.py
