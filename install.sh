#!/bin/bash

echo "🚀 نصب اصلاح‌شده ربات فروش VPN (با رفع ارور pip)..."

# آپدیت لیست پکیج‌ها
apt update

# نصب پایتون، pip و venv (اگر نباشه)
apt install python3 python3-pip python3-venv git -y

# کلون کردن ریپو به دایرکتوری جدید (برای جلوگیری از overwrite)
git clone https://github.com/Mohammad1724/vpn_bot.git /root/vpn_bot_fixed

# رفتن به دایرکتوری
cd /root/vpn_bot_fixed

# ساخت virtual environment
python3 -m venv myenv

# فعال کردن venv
source myenv/bin/activate

# نصب وابستگی‌ها داخل venv (حالا بدون ارور کار می‌کنه)
pip install -r requirements.txt

# غیرفعال کردن venv (برای تمیز بودن)
deactivate

# کپی فایل نمونه env
cp .env.example .env

echo "✅  نصب کامل شد! (وابستگی‌ها در venv نصب شدن)"
echo "⚠️ لطفا فایل .env را ویرایش کنید: nano .env"
echo "▶️ برای اجرا:"
echo "   cd /root/vpn_bot_fixed"
echo "   source myenv/bin/activate"
echo "   python3 vpn_bot.py"
echo "   (برای خروج از venv: deactivate)"
echo "نکته: اگر می‌خوای بات همیشه اجرا بشه، از screen یا systemd استفاده کن."
