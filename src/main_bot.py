# -*- coding: utf-8 -*-

from app import build_application
import database as db
from config import REFERRAL_BONUS_AMOUNT

def main():
    db.init_db()
    # همگام‌سازی اولیه مبلغ هدیه معرفی (در صورت نبود در DB)
    if db.get_setting('referral_bonus_amount') is None:
        db.set_setting('referral_bonus_amount', str(REFERRAL_BONUS_AMOUNT))

    application = build_application()
    print("Bot is running.")
    application.run_polling()

if __name__ == "__main__":
    main()