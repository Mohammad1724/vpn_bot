#!/bin/bash

echo "🚀 نصب  ربات فروش VPN"

# آپدیت لیست پکیج‌ها
apt update

# نصب پکیج‌های لازم (python, pip, venv, git)
apt install python3 python3-pip python3-venv git -y

# اگر دایرکتوری وجود داشت، پاک کن برای overwrite
if [ -d "/root/vpn_bot" ]; then
    rm -rf /root/vpn_bot
fi

# کلون کردن ریپو به دایرکتوری جدید (برای تمایز)
git clone https://github.com/Mohammad1724/vpn_bot.git /root/vpn_bot

# رفتن به دایرکتوری
cd /root/vpn_bot

# ساخت virtual environment
python3 -m venv myenv

# فعال کردن venv
source myenv/bin/activate

# نصب و آپدیت وابستگی‌ها داخل venv
pip install --upgrade -r requirements.txt

# غیرفعال کردن venv
deactivate

# چک و ساخت فایل .env
if [ -f ".env.example" ]; then
    cp .env.example .env
else
    echo "# فایل .env خالی ساخته شد (چون .env.example وجود نداشت)" > .env
    echo "⚠️ هشدار: .env.example در ریپو نبود. تنظیمات رو حالا وارد کنید."
fi

# پرسیدن 
