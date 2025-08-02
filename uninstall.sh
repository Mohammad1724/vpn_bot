#!/bin/bash

# اسکریپت حذف کامل ربات VPN

INSTALL_DIR="/root/vpn_bot"
SERVICE_NAME="vpn_bot.service"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME"

echo "--- شروع فرآیند حذف کامل ربات ---"

# مرحله ۱: توقف و غیرفعال کردن سرویس
echo "مرحله ۱: توقف و غیرفعال کردن سرویس systemd..."
systemctl stop "$SERVICE_NAME" > /dev/null 2>&1
systemctl disable "$SERVICE_NAME" > /dev/null 2>&1
echo "سرویس متوقف و غیرفعال شد."

# مرحله ۲: حذف فایل سرویس
if [ -f "$SERVICE_FILE_PATH" ]; then
    echo "مرحله ۲: حذف فایل سرویس..."
    rm -f "$SERVICE_FILE_PATH"
    systemctl daemon-reload
    echo "فایل سرویس حذف شد."
fi

# مرحله ۳: حذف پوشه پروژه
if [ -d "$INSTALL_DIR" ]; then
    echo "مرحله ۳: حذف پوشه پروژه..."
    rm -rf "$INSTALL_DIR"
    echo "پوشه پروژه ($INSTALL_DIR) حذف شد."
fi

echo "--- ربات با موفقیت به طور کامل حذف شد. ---"