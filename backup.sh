#!/bin/bash
DATE=$(date +%Y%m%d_%H%M)
BACKUP_DIR="/opt/backups"
PROJECT_DIR="/opt/vpn-bot"

echo "🗄️ ایجاد بک‌آپ..."
tar -czf "$BACKUP_DIR/vpn-bot-backup-$DATE.tar.gz" -C "$PROJECT_DIR" .

# حذف بک‌آپ‌های قدیمی (بیشتر از 7 روز)
find "$BACKUP_DIR" -name "vpn-bot-backup-*.tar.gz" -mtime +7 -delete

echo "✅ بک‌آپ ذخیره شد: vpn-bot-backup-$DATE.tar.gz"
