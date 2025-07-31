#!/bin/bash

echo "🚀 Sales robot vpn"

# آپدیت و نصب پکیج‌ها
apt update
apt install python3 python3-pip python3-venv git -y

# پاک کردن دایرکتوری قبلی
[ -d "/root/vpn_bot" ] && rm -rf /root/vpn_bot

# کلون ریپو
git clone https://github.com/Mohammad1724/vpn_bot.git /root/vpn_bot

# رفتن به دایرکتوری
cd /root/vpn_bot

# ساخت و فعال کردن venv
python3 -m venv myenv
source myenv/bin/activate

# نصب وابستگی‌ها
pip install --upgrade -r requirements.txt
pip install qrcode[pil]

# غیرفعال کردن venv
deactivate

# ساخت .env
if [ -f ".env.example" ]; then
  cp .env.example .env
else
  echo "# فایل .env خالی ساخته شد" > .env
  echo "⚠️ .env.example نبود. تنظیمات رو وارد کنید."
fi

# پرسیدن تنظیمات (ساده‌شده برای جلوگیری از ارور syntax)
echo "حالا تنظیمات .env رو وارد کنید (Enter برای skip):"
read -p "BOT_TOKEN: " BOT_TOKEN && [ -n "$BOT_TOKEN" ] && echo "BOT_TOKEN=$BOT_TOKEN" >> .env
read -p "ADMIN_ID: " ADMIN_ID && [ -n "$ADMIN_ID" ] && echo "ADMIN_ID=$ADMIN_ID" >> .env
read -p "CARD_NUMBER (برای پرداخت): " CARD_NUMBER && [ -n "$CARD_NUMBER" ] && echo "CARD_NUMBER=$CARD_NUMBER" >> .env
read -p "PLANS (مثل 1GB:10000,10GB:50000): " PLANS && [ -n "$PLANS" ] && echo "PLANS=$PLANS" >> .env

echo "✅ تنظیمات ذخیره شد. ویرایش: nano .env"

# رفع باگ callback
sed -i 's/@bot.callback/@bot.callback_query_handler(func=lambda call: True)/g' vpn_bot.py
echo "✅ باگ callback رفع شد."

# نصب screen
apt install screen -y

echo "✅ نصب کامل شد!"
echo "▶️ اجرا: cd /root/vpn_bot ; source myenv/bin/activate ; python3 vpn_bot.py"

# پرسیدن اجرا
read -p "اجرا کنم؟ (y/n): " RUN_NOW
[ "$RUN_NOW" = "y" -o "$RUN_NOW" = "Y" ] && screen -S vpn_bot -dm bash -c 'cd /root/vpn_bot ; source myenv/bin/activate ; python3 vpn_bot.py' && echo "✅ اجرا شد! screen -r vpn_bot"
