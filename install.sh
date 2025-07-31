#!/bin/bash

echo "🚀 نصب ربات فروش VPN"

# آپدیت لیست پکیج‌ها
apt update

# نصب پکیج‌های لازم
apt install python3 python3-pip python3-venv git -y

# پاک کردن دایرکتوری قبلی اگر وجود داشته باشه
if [ -d "/root/vpn_bot" ]; then
    rm -rf /root/vpn_bot
fi

# کلون ریپو
git clone https://github.com/Mohammad1724/vpn_bot.git /root/vpn_bot

# رفتن به دایرکتوری
cd /root/vpn_bot

# ساخت venv
python3 -m venv myenv

# فعال کردن venv
source myenv/bin/activate

# نصب وابستگی‌ها
pip install --upgrade -r requirements.txt
pip install qrcode[pil]  # برای QR کد در بات

# غیرفعال کردن venv
deactivate

# ساخت .env اگر .env.example نباشه
if [ -f ".env.example" ]; then
    cp .env.example .env
else
    echo "# فایل .env خالی ساخته شد" > .env
    echo "⚠️ .env.example نبود. تنظیمات رو وارد کنید."
fi

# پرسیدن تنظیمات (syntax چک شده)
echo "حالا تنظیمات .env رو وارد کنید (Enter برای skip):"

read -p "BOT_TOKEN (توکن بات): " BOT_TOKEN
if [ ! -z "$BOT_TOKEN" ]; then
    echo "BOT_TOKEN=$BOT_TOKEN" >> .env
fi

read -p "ADMIN_ID (ID عددی ادمین): " ADMIN_ID
if [ ! -z "$ADMIN_ID" ]; then
    echo "ADMIN_ID=$ADMIN_ID" >> .env
fi

read -p "CARD_NUMBER (شماره کارت برای پرداخت): " CARD_NUMBER
if [ ! -z "$CARD_NUMBER" ]; then
    echo "CARD_NUMBER=$CARD_NUMBER" >> .env
fi

read -p "PLANS (پلن‌ها، مثال 1GB:10000,10GB:50000): " PLANS
if [ ! -z "$PLANS" ]; then
    echo "PLANS=$PLANS" >> .env
fi

echo "✅ تنظیمات ذخیره شد. ویرایش: nano .env"

# رفع باگ callback در vpn_bot.py (اگر لازم باشه)
sed -i 's/@bot.callback/@bot.callback_query_handler(func=lambda call: True)/g' vpn_bot.py
echo "✅ باگ callback رفع شد."

# نصب screen
apt install screen -y

echo "✅ نصب کامل شد!"
echo "▶️ اجرا: cd /root/vpn_bot ; source myenv/bin/activate ; python3 vpn_bot.py"

# پرسیدن اجرا
read -p "اجرا کنم؟ (y/n): " RUN_NOW
if [ "$RUN_NOW" = "y" ] || [ "$RUN_NOW" = "Y" ]; then
    screen -S vpn_bot -dm bash -c 'cd /root/vpn_bot ; source myenv/bin/activate ; python3 vpn_bot.py'
    echo "✅ اجرا شد! screen -r vpn_bot برای دیدن."
fi
