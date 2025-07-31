#!/bin/bash

echo "🚀 نصب اصلاح‌شده ربات فروش VPN..."

# چک اگر stdin باز باشه (برای read)
if [ ! -t 0 ]; then
  echo "⚠️ هشدار: stdin بسته است (مثل pipe | bash). سوالات پرسیده نمی‌شن. .env رو دستی ویرایش کن: nano /root/vpn_bot/.env"
fi

# آپدیت و نصب پکیج‌ها
apt update
apt install python3 python3-pip python3-venv git -y

# پاک کردن دایرکتوری قبلی
[ -d "/root/vpn_bot" ] && rm -rf /root/vpn_bot

# کلون ریپو
git clone https://github.com/Mohammad1724/vpn_bot.git /root/vpn_bot

# رفتن به دایرکتوری
cd /root/vpn_bot

# ساخت venv و نصب وابستگی‌ها
python3 -m venv myenv
source myenv/bin/activate
pip install --upgrade -r requirements.txt
pip install qrcode[pil]
deactivate

# ساخت .env
[ -f ".env.example" ] && cp .env.example .env || echo "# فایل .env خالی" > .env

# پرسیدن تنظیمات (اگر stdin باز باشه)
echo "حالا تنظیمات .env رو وارد کنید (Enter برای skip):"
read -p "BOT_TOKEN: " BOT_TOKEN
[ -n "$BOT_TOKEN" ] && echo "BOT_TOKEN=$BOT_TOKEN" >> .env

read -p "ADMIN_ID: " ADMIN_ID
[ -n "$ADMIN_ID" ] && echo "ADMIN_ID=$ADMIN_ID" >> .env

read -p "CARD_NUMBER: " CARD_NUMBER
[ -n "$CARD_NUMBER" ] && echo "CARD_NUMBER=$CARD_NUMBER" >> .env

read -p "PLANS (مثل 1GB:10000,10GB:50000): " PLANS
[ -n "$PLANS" ] && echo "PLANS=$PLANS" >> .env

echo "✅ تنظیمات ذخیره شد."

# رفع باگ callback
sed -i 's/@bot.callback/@bot.callback_query_handler(func=lambda call: True)/g' vpn_bot.py

# نصب screen
apt install screen -y

echo "✅ نصب کامل شد! اجرا: cd /root/vpn_bot ; source myenv/bin/activate ; python3 vpn_bot.py"

read -p "اجرا کنم؟ (y/n): " RUN_NOW
[ "$RUN_NOW" = "y" -o "$RUN_NOW" = "Y" ] && screen -S vpn_bot -dm bash -c 'cd /root/vpn_bot ; source myenv/bin/activate ; python3 vpn_bot.py' && echo "✅ اجرا شد!"
