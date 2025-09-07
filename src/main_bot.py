# filename: main_bot.py
# -*- coding: utf-8 -*-

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from app import build_application
import database as db

# Safe config import
try:
    import config as _cfg
except Exception:
    class _Cfg: pass
    _cfg = _Cfg()
REFERRAL_BONUS_AMOUNT = getattr(_cfg, "REFERRAL_BONUS_AMOUNT", 5000)
PANEL_ENABLED = getattr(_cfg, "PANEL_ENABLED", False)

# --- Logging Configuration ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler (5MB, 2 backups)
file_handler = RotatingFileHandler('bot.log', maxBytes=5 * 1024 * 1024, backupCount=2, encoding='utf-8')
file_handler.setFormatter(log_formatter)

# Console handler
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
    db.init_db()

    # مقدار هدیه معرفی را اگر در DB نباشد تنظیم کن
    if db.get_setting('referral_bonus_amount') is None:
        db.set_setting('referral_bonus_amount', str(REFERRAL_BONUS_AMOUNT))

    mode = "Panel: ON" if PANEL_ENABLED else "Panel: OFF"
    logging.getLogger(__name__).info("Starting bot (%s)", mode)

    application = build_application()

    logging.getLogger(__name__).info("Bot is running.")

    try:
        application.run_polling(
            timeout=60,
            poll_interval=0.0,
            drop_pending_updates=True
        )
    finally:
        db.close_db()


if __name__ == "__main__":
    main()