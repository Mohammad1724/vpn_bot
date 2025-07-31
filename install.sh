#!/bin/bash

echo "🚀 نصب ربات فروش VPN"

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

# پرسیدن تنظیمات از کاربر و ذخیره در .env
echo "حالا تنظیمات .env رو وارد کنید (اگر نمی‌خوای، Enter بزن برای skip):"

read -p "BOT_TOKEN (توکن بات تلگرام از BotFather): " BOT_TOKEN
if [ ! -z "$BOT_TOKEN" ]; then
    echo "BOT_TOKEN=$BOT_TOKEN" >> .env
fi

read -p "ADMIN_ID (ID عددی تلگرام ادمین، مثلاً 123456789): " ADMIN_ID
if [ ! -z "$ADMIN_ID" ]; then
    echo "ADMIN_ID=$ADMIN_ID" >> .env
fi

# فیلدهای اختیاری (مثل قیمت)
read -p "PRICE_1GB (قیمت نمونه، مثلاً 10000 - اختیاری): " PRICE_1GB
if [ ! -z "$PRICE_1GB" ]; then
    echo "PRICE_1GB=$PRICE_1GB" >> .env
fi

read -p "ZARINPAL_API (API درگاه پرداخت زرین‌پال - اختیاری): " ZARINPAL_API
if [ ! -z "$ZARINPAL_API" ]; then
    echo "ZARINPAL_API=$ZARINPAL_API" >> .env
fi

# پرسیدن کانفیگ‌های دستی (چند تا می‌تونی وارد کنی، جدا شده با کاما)
read -p "CONFIGS (کانفیگ‌های دستی، مثلاً vless://uuid@server:port?security=tls#config1,vless://... - جدا با کاما، اختیاری): " CONFIGS
if [ ! -z "$CONFIGS" ]; then
    echo "CONFIGS=$CONFIGS" >> .env
fi

echo "✅ تنظیمات در .env ذخیره شد. اگر نیاز به ویرایش داری: nano .env"

# رفع باگ در vpn_bot.py (تغییر @bot.callback به درستش)
sed -i 's/@bot.callback/@bot.callback_query_handler(func=lambda call: True)/g' vpn_bot.py
echo "✅ باگ @bot.callback در vpn_bot.py رفع شد (اگر ارور ادامه داشت، دستی چک کن: nano vpn_bot.py خط 298)"

# غیرفعال کردن بخش‌های پنل در کد (کامنت کردن خطوط مربوط به PANEL_URL و requests به پنل)
sed -i '/PANEL_URL/s/^/# /' vpn_bot.py  # کامنت کردن خطوط با PANEL_URL
sed -i '/requests\.post.*PANEL/s/^/# /' vpn_bot.py  # کامنت کردن درخواست‌های به پنل (مثل ساخت کانفیگ)
echo "✅ بخش‌های پنل در vpn_bot.py غیرفعال شدن (کامنت شدن). حالا ربات بدون پنل کار می‌کنه."

# اضافه کردن هندلر ساده برای مدیریت دستی کانفیگ‌ها (به انتهای فایل اضافه می‌کنه)
cat << EOF >> vpn_bot.py

# هندلر جدید برای مدیریت دستی کانفیگ‌ها (فقط برای ادمین)
@bot.message_handler(commands=['add_config'])
def add_config(message):
    if str(message.from_user.id) == os.getenv('ADMIN_ID'):
        bot.reply_to(message, "کانفیگ جدید رو بفرست (مثل vless://...):")
        bot.register_next_step_handler(message, save_config)
    else:
        bot.reply_to(message, "فقط ادمین می‌تونه کانفیگ اضافه کنه.")

def save_config(message):
    new_config = message.text
    # ذخیره در فایل ساده (مثال)
    with open('manual_configs.txt', 'a') as f:
        f.write(new_config + '\n')
    bot.reply_to(message, f"کانفیگ ذخیره شد: {new_config}")

# مثال: فرمان برای ارسال کانفیگ به کاربر (می‌تونی گسترش بدی)
@bot.message_handler(commands=['get_config'])
def get_config(message):
    # خواندن از فایل یا .env
    configs = os.getenv('CONFIGS', '').split(',')
    if configs and configs[0]:
        bot.reply_to(message, "یک کانفیگ نمونه: " + configs[0])
    else:
        bot.reply_to(message, "هیچ کانفیگی موجود نیست. ادمین اضافه کنه.")
EOF
echo "✅ هندلرهای دستی برای /add_config و /get_config به vpn_bot.py اضافه شد. حالا می‌تونی کانفیگ‌ها رو دستی مدیریت کنی."

# نصب screen برای اجرای پایدار
apt install screen -y

echo "✅ نصب کامل شد!"
echo "▶️ برای اجرا دستی:"
echo "   cd /root/vpn_bot_manual"
echo "   source myenv/bin/activate"
echo "   python3 vpn_bot.py"

# پرسیدن برای اجرای بات حالا
read -p "آیا می‌خوای بات رو حالا اجرا کنی؟ (y/n): " RUN_NOW
if [ "$RUN_NOW" = "y" ] || [ "$RUN_NOW" = "Y" ]; then
    cd /root/vpn_bot_manual
    screen -S vpn_bot -dm bash -c 'source myenv/bin/activate; python3 vpn_bot.py'
    echo "✅ بات در screen اجرا شد! برای دیدن: screen -r vpn_bot"
    echo "برای stop: screen -r vpn_bot سپس Ctrl+C و exit"
else
    echo "بات اجرا نشد. بعداً دستی اجرا کن."
fi
