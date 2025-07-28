فایل راهنمای اصلی پروژه که شامل دستورالعمل‌های نصب، پیکربندی، و مدیریت ربات است. این فایل به کاربران کمک می‌کند تا به راحتی ربات را راه‌اندازی و استفاده کنند.
# 🤖 ربات فروش VPN

ربات تلگرام پیشرفته برای فروش خودکار سرویس‌های VPN با پنل HiddiFy

## ✨ ویژگی‌ها

- 🛒 **فروش خودکار** سرویس‌های VPN
- 💳 پشتیبانی از **درگاه‌های پرداخت ایرانی** (زرین‌پال و کارت به کارت)
- 🔗 اتصال مستقیم به **پنل HiddiFy** برای ایجاد خودکار کانفیگ
- 👨‍💼 **پنل مدیریت کامل** با دستورات ادمین
- 📊 **گزارش‌گیری و آمار** لحظه‌ای
- 💬 **پشتیبانی از کاربران**
- 🔄 **بک‌آپ خودکار** روزانه از دیتابیس و فایل‌ها

## 🚀 نصب سریع (توصیه شده)

با استفاده از این دستور، ربات به صورت کامل روی سرور شما نصب و راه‌اندازی می‌شود. این دستور تمام پیش‌نیازها را نصب کرده، پروژه را دانلود کرده و ربات را به عنوان یک سرویس سیستمی (Systemd) تنظیم می‌کند.
# دانلود و اجرای اسکریپت نصب


```bash
sudo curl -sSL [https://raw.github.com/Mohammad1724/vpn_bot/main/install.sh]

## 📦 نصب دستی
1. پیش‌نیازها
مطمئن شوید که Python 3 و pip روی سیستم شما نصب هستند:
sudo apt update
sudo apt install python3 python3-pip python3-venv git screen nano curl -y

2. کلون کردن پروژه
پروژه را از گیت‌هاب کلون کنید:
git clone [https://github.com/yourusername/vpn-sales-bot.git](https://github.com/yourusername/vpn-sales-bot.git)
cd vpn-sales-bot

نکته: https://github.com/yourusername/vpn-sales-bot.git را با آدرس ریپازیتوری خود جایگزین کنید.
3. نصب وابستگی‌ها
یک محیط مجازی Python ایجاد و فعال کنید، سپس کتابخانه‌های مورد نیاز را نصب کنید:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

4. تنظیمات
فایل config.py را ویرایش کرده و توکن ربات، API Key پنل Hiddify، آیدی ادمین‌ها و سایر اطلاعات را وارد کنید:
nano config.py

مثال از اطلاعات ضروری:
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_IDS = [123456789] # آیدی تلگرام خودتان
HIDDIFY_API_URL = "[https://your-hiddify-panel.com](https://your-hiddify-panel.com)"
HIDDIFY_API_KEY = "your-hiddify-api-key"
ZARINPAL_MERCHANT_ID = "your-zarinpal-merchant-id" # اختیاری

5. راه‌اندازی ربات
برای اجرای ربات به صورت دائمی، توصیه می‌شود از systemd استفاده کنید. فایل vpn-bot.service را در مسیر /etc/systemd/system/ ایجاد کنید:
sudo nano /etc/systemd/system/vpn-bot.service

محتوای زیر را درون آن قرار دهید (مسیر WorkingDirectory و ExecStart را با مسیر واقعی پروژه خود جایگزین کنید، اگر از /opt/vpn-bot استفاده نمی‌کنید):
[Unit]
Description=VPN Sales Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/your/vpn-sales-bot # مسیر دایرکتوری پروژه
Environment=PATH=/path/to/your/vpn-sales-bot/venv/bin # مسیر venv
ExecStart=/path/to/your/vpn-sales-bot/venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

سپس سرویس را فعال و راه‌اندازی کنید:
sudo systemctl daemon-reload
sudo systemctl enable vpn-bot
sudo systemctl start vpn-bot

⚙️ پیکربندی
ربات تلگرام
 * به بات‌فادر (BotFather) در تلگرام بروید.
 * دستور /newbot را ارسال کنید و مراحل را دنبال کنید تا یک ربات جدید بسازید.
 * توکن دریافتی از بات‌فادر را در فایل config.py در متغیر BOT_TOKEN قرار دهید.
پنل Hiddify
 * وارد پنل ادمین Hiddify خود شوید.
 * به بخش Settings > API بروید.
 * یک API Key جدید ایجاد کنید.
 * آدرس پنل و API Key را در فایل config.py در متغیرهای HIDDIFY_API_URL و HIDDIFY_API_KEY قرار دهید.
درگاه پرداخت
 * زرین‌پال: اگر قصد استفاده از زرین‌پال را دارید، شناسه پذیرنده (Merchant ID) خود را از پنل زرین‌پال دریافت کرده و در متغیر ZARINPAL_MERCHANT_ID در config.py قرار دهید.
 * کارت به کارت: اگر پرداخت دستی (کارت به کارت) را نیز می‌پذیرید، اطلاعات کارت بانکی خود را در متغیرهای CARD_NUMBER و CARD_HOLDER_NAME در config.py تکمیل کنید.
🛠️ مدیریت ربات
پس از نصب، می‌توانید از اسکریپت manage.sh برای مدیریت آسان ربات استفاده کنید. ابتدا به دایرکتوری پروژه بروید:
cd /opt/vpn-bot # یا مسیری که پروژه را نصب کرده‌اید

سپس اسکریپت مدیریت را اجرا کنید:
./manage.sh

این اسکریپت یک منوی تعاملی برای انجام عملیات زیر فراهم می‌کند:
 * شروع/توقف/وضعیت ربات
 * مشاهده لاگ‌ها
 * ویرایش فایل config.py
 * بازنشانی ربات
 * تنظیم فایروال (UFW)
دستورات مستقیم (پیشرفته)
اگر می‌خواهید مستقیماً با systemctl کار کنید:
# شروع ربات
sudo systemctl start vpn-bot

# توقف ربات  
sudo systemctl stop vpn-bot

# بررسی وضعیت ربات
sudo systemctl status vpn-bot

# مشاهده لاگ‌های ربات به صورت زنده
sudo journalctl -u vpn-bot -f

📱 دستورات ربات تلگرام
برای کاربران عادی
 * /start - شروع تعامل با ربات و نمایش منوی اصلی.
 * دکمه‌های اینلاین برای خرید سرویس، مشاهده سرویس‌های من، پشتیبانی و راهنما.
برای ادمین‌ها
 * /admin - دسترسی به پنل مدیریت ربات.
 * /activate ORDER_ID - فعال‌سازی یک سفارش خاص (با جایگزینی ORDER_ID با شناسه سفارش).
 * /addservice نام قیمت مدت_روز حجم_گیگ توضیحات - اضافه کردن سرویس جدید به لیست سرویس‌ها (مثال: /addservice پکیج_تست 50000 30 100 برای_تست).
 * /stats - مشاهده آمار کلی ربات (تعداد کاربران، درآمد و...).
 * /broadcast پیام_شما - ارسال یک پیام همگانی به تمام کاربران فعال ربات.
 * /orders - مشاهده ۱۰ سفارش اخیر در ربات.
🔧 عیب‌یابی
مشکلات رایج
ربات پاسخ نمی‌دهد یا کار نمی‌کند:
 * وضعیت سرویس را بررسی کنید:
   sudo systemctl status vpn-bot

   مطمئن شوید که سرویس در حال اجرا (active (running)) باشد.
 * لاگ‌های ربات را بررسی کنید:
   sudo journalctl -u vpn-bot -f

   به دنبال پیام‌های خطا یا هشدار باشید.
خطا در اتصال به پنل Hiddify:
 * آدرس پنل (HIDDIFY_API_URL) را در config.py به دقت بررسی کنید.
 * API Key (HIDDIFY_API_KEY) را از پنل Hiddify خود دوباره کپی و در config.py جایگذاری کنید (ممکن است کاراکترهای اضافی داشته باشد).
 * مطمئن شوید که سرور شما می‌تواند به آدرس پنل Hiddify متصل شود (مثلاً با ping یا curl).
مشکل در پایگاه داده SQLite:
در موارد نادر، ممکن است فایل‌های جانبی دیتابیس دچار مشکل شوند. می‌توانید آن‌ها را حذف کرده و ربات را restart کنید (دیتابیس اصلی vpn_bot.db نباید حذف شود):
rm /opt/vpn-bot/vpn_bot.db-wal
rm /opt/vpn-bot/vpn_bot.db-shm
sudo systemctl restart vpn-bot

🤝 مشارکت
از هرگونه مشارکت در بهبود این پروژه استقبال می‌شود! اگر ایده‌ای برای ویژگی جدید دارید، باگ پیدا کردید یا می‌خواهید کدی را بهبود بخشید، لطفاً مراحل زیر را دنبال کنید:
 * پروژه را Fork کنید.
 * یک Branch جدید برای تغییرات خود ایجاد کنید (git checkout -b feature/your-feature-name).
 * تغییرات خود را Commit کنید (git commit -m 'Add new feature').
 * تغییرات را به ریپازیتوری خود Push کنید (git push origin feature/your-feature-name).
 * یک Pull Request به این ریپازیتوری ایجاد کنید.
📄 لایسنس
این پروژه تحت لایسنس MIT منتشر شده است. برای اطلاعات بیشتر، به فایل LICENSE (اگر وجود دارد) مراجعه کنید.
📞 پشتیبانی
اگر سؤالی دارید یا به کمک نیاز دارید، می‌توانید از طریق راه‌های زیر با ما در تماس باشید:
 * تلگرام: [@YourUsername] (با یوزرنیم پشتیبانی خود جایگزین کنید)
 * ایمیل: [your@email.com] (با ایمیل پشتیبانی خود جایگزین کنید)
 * Issues: GitHub Issues (با آدرس ریپازیتوری خود جایگزین کنید)
