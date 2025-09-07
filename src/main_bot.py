# filename: main_bot.py
# -*- coding: utf-8 -*-

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from app import build_application
import database as db
from config import REFERRAL_BONUS_AMOUNT, NODELESS_MODE, PANEL_INTEGRATION_ENABLED

# --- Logging Configuration ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler (5MB, 2 backups)
file_handler = RotatingFileHandler('bot.log', maxBytes=5 * 1024 * 1024, backupCount=2, encoding='utf-8')
file_handler.setFormatter(log_formatter)

# Console handler (journalctl will capture)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# Root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Reduce noisy logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger("telegram.network").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._updater").setLevel(logging.WARNING)

# Filter to suppress transient httpx.ReadError logs
class _SuppressHttpxReadError(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return ("httpx.ReadError" not in msg) and ("Transient network error ignored: httpx.ReadError" not in msg)

logging.getLogger("telegram.ext.Updater").addFilter(_SuppressHttpxReadError())
logging.getLogger("telegram.ext._updater").addFilter(_SuppressHttpxReadError())
logging.getLogger("telegram.network").addFilter(_SuppressHttpxReadError())
# --- End of Logging Configuration ---


def main() -> None:
    """Start the bot."""
    db.init_db()

    # مقدار هدیه معرفی را اگر در DB نباشد تنظیم کن
    if db.get_setting('referral_bonus_amount') is None:
        db.set_setting('referral_bonus_amount', str(REFERRAL_BONUS_AMOUNT))

    # لاگ وضعیت اجرا: بدون نود/بدون پنل یا متصل به پنل
    mode = "NODELESS (local-only, no panel)" if (NODELESS_MODE or not PANEL_INTEGRATION_ENABLED) else "PANEL-INTEGRATED"
    logging.getLogger(__name__).info("Starting bot in mode: %s", mode)

    application = build_application()

    logging.getLogger(__name__).info("Bot is running.")

    try:
        # بهبود long-poll و کاهش نویز خطای ReadError
        application.run_polling(
            timeout=60,               # long-poll timeout
            poll_interval=0.0,        # start next poll immediately
            drop_pending_updates=True # صف قدیمی را نخوان
        )
    finally:
        # بستن تمیز اتصال دیتابیس هنگام خروج
        db.close_db()


if __name__ == "__main__":
    main()