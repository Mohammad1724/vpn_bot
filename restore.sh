#!/bin/bash
# اسکریپت بازیابی اطلاعات از بکاپ

SERVICE_NAME="vpn_bot.service"
INSTALL_DIR="/root/vpn_bot"
BACKUP_FILE="backup_to_restore.zip"

echo "شروع فرآیند بازیابی..."

# مرحله ۱: توقف سرویس
echo "متوقف کردن سرویس ربات..."
systemctl stop "$SERVICE_NAME"
sleep 2

# مرحله ۲: استخراج فایل بکاپ
echo "استخراج فایل بکاپ..."
if [ -f "$BACKUP_FILE" ]; then
    unzip -o "$BACKUP_FILE" -d "$INSTALL_DIR"
    rm "$BACKUP_FILE"
    echo "فایل‌ها با موفقیت جایگزین شدند."
else
    echo "خطا: فایل بکاپ پیدا نشد."
    systemctl start "$SERVICE_NAME"
    exit 1
fi

# مرحله ۳: شروع مجدد سرویس
echo "راه‌اندازی مجدد سرویس ربات..."
systemctl start "$SERVICE_NAME"
sleep 3

# مرحله ۴: بررسی وضعیت
systemctl status "$SERVICE_NAME"
echo "فرآیند بازیابی به پایان رسید."