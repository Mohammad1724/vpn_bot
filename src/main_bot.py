# -*- coding: utf-8 -*-

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from app import build_application
import database as db
from config import REFERRAL_BONUS_AMOUNT

# --- Logging Configuration ---
# فرمت لاگ
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler: لاگ‌ها را در bot.log می‌نویسد (5MB per file, 2 backups)
# مطمئن شوید که پوشه src برای یوزر vpn-bot قابل نوشتن است.
file_handler = RotatingFileHandler('bot.log', maxBytes=5 * 1024 * 1024, backupCount=2, encoding='utf-8')
file_handler.setFormatter(log_formatter)

# Console handler: لاگ‌ها را در کنسول چاپ می‌کند (که توسط journalctl گرفته می‌شود)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# لاگر اصلی را گرفته و handler ها را به آن اضافه می‌کنیم
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)  # سطح لاگ اصلی را روی INFO تنظیم می‌کنیم
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# کاهش لاگ‌های اضافی از کتابخانه‌ها
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)
# --- End of Logging Configuration ---

def main() -> None:
    """Start the bot."""
    db.init_db()

    # همگام‌سازی اولیه مبلغ هدیه معرفی (در صورت نبود در DB)
    if db.get_setting('referral_bonus_amount') is None:
        db.set_setting('referral_bonus_amount', str(REFERRAL_BONUS_AMOUNT))

    application = build_application()

    # پیام "Bot is running" حالا توسط لاگر چاپ می‌شود
    logging.getLogger(__name__).info("Bot is running.")

    application.run_polling()

if __name__ == "__main__":
    main()