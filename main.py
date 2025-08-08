# -*- coding: utf-8 -*-
import logging
import asyncio
import os
from datetime import time, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    PicklePersistence,
    Defaults
)
from telegram.constants import ParseMode

# Import configurations and constants
from config import BOT_TOKEN, ADMIN_ID
from constants import *

# Import modules
import database as db
import jobs

# Import handlers from their modules
from handlers.user_handlers import (
    start, show_account_info, show_support, show_guide, show_referral_link,
    get_trial_service, buy_service_list,
    buy_service_conv, gift_code_conv, charge_account_conv
)
from handlers.admin_handlers import (
    admin_conv, edit_plan_conv, settings_conv, edit_guide_conv
)
from handlers.callback_handlers import *

# --- Setup Logging ---
os.makedirs('backups', exist_ok=True)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
# Reduce verbosity of the HTTPX library used by the bot
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """Initialize the database after the application has been set up."""
    await db.init_db()
    logger.info("Database has been initialized.")


def main() -> None:
    """Start the bot."""
    # --- Persistence ---
    # This will save user and chat data across bot restarts
    persistence = PicklePersistence(filepath="bot_persistence")

    # --- Application Setup ---
    # Set default parse mode for all messages
    defaults = Defaults(parse_mode=ParseMode.HTML)
    
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .post_init(post_init)
        .defaults(defaults)
        .build()
    )

    # --- Register Handlers ---
    # The order and grouping of handlers is important.
    
    # Group 1: Conversation Handlers (User and Admin)
    # These have higher priority to catch user input in the middle of a conversation.
    application.add_handler(admin_conv, group=1)
    application.add_handler(edit_plan_conv, group=1)
    application.add_handler(settings_conv, group=1)
    application.add_handler(edit_guide_conv, group=1)
    application.add_handler(buy_service_conv, group=1)
    application.add_handler(gift_code_conv, group=1)
    application.add_handler(charge_account_conv, group=1)

    # Group 2: CallbackQuery Handlers (for inline buttons that are NOT part of a conversation)
    # Admin callbacks
    application.add_handler(CallbackQueryHandler(admin_confirm_charge_callback, pattern=f"^{CALLBACK_ADMIN_CONFIRM_CHARGE}"), group=2)
    application.add_handler(CallbackQueryHandler(admin_reject_charge_callback, pattern=f"^{CALLBACK_ADMIN_REJECT_CHARGE}"), group=2)
    application.add_handler(CallbackQueryHandler(admin_delete_plan_callback, pattern="^admin_delete_plan_"), group=2)
    application.add_handler(CallbackQueryHandler(admin_toggle_plan_visibility_callback, pattern="^admin_toggle_plan_"), group=2)
    application.add_handler(CallbackQueryHandler(admin_confirm_restore_callback, pattern="^admin_confirm_restore$"), group=2)
    application.add_handler(CallbackQueryHandler(admin_cancel_restore_callback, pattern="^admin_cancel_restore$"), group=2)
    application.add_handler(CallbackQueryHandler(admin_link_settings_menu, pattern="^admin_link_settings$"), group=2)
    application.add_handler(CallbackQueryHandler(set_recommended_link_callback, pattern="^set_rec_link_"), group=2)
    application.add_handler(CallbackQueryHandler(back_to_settings_callback, pattern="^back_to_settings$"), group=2)

    # User callbacks
    application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"), group=2)
    application.add_handler(CallbackQueryHandler(show_service_management_callback, pattern=f"^{CALLBACK_SHOW_SERVICE}"), group=2)
    application.add_handler(CallbackQueryHandler(list_my_services_callback, pattern="^back_to_services$"), group=2)
    application.add_handler(CallbackQueryHandler(get_link_callback, pattern=f"^{CALLBACK_GET_LINK}"), group=2)
    application.add_handler(CallbackQueryHandler(show_single_configs_menu, pattern="^single_configs_"), group=2)
    application.add_handler(CallbackQueryHandler(get_single_config, pattern="^get_single_"), group=2)
    application.add_handler(CallbackQueryHandler(renew_service_handler, pattern=f"^{CALLBACK_RENEW_SERVICE}"), group=2)
    application.add_handler(CallbackQueryHandler(confirm_renewal_callback, pattern="^confirmrenew$"), group=2)
    application.add_handler(CallbackQueryHandler(cancel_renewal_callback, pattern="^cancelrenew$"), group=2)

    # Group 3: Regular Commands and Message Handlers
    # These have lower priority and will only be triggered if no conversation is active.
    application.add_handler(CommandHandler("start", start), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), buy_service_list), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📋 سرویس‌های من$'), list_my_services_callback), group=3) # Changed to callback for consistency
    application.add_handler(MessageHandler(filters.Regex('^👤 اطلاعات حساب$'), show_account_info), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), show_support), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📚 راهنمای اتصال$'), show_guide), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🧪 دریافت سرویس تست رایگان$'), get_trial_service), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🎁 معرفی دوستان$'), show_referral_link), group=3)


    # --- Schedule Jobs ---
    job_queue = application.job_queue
    job_queue.run_repeating(jobs.check_low_usage, interval=timedelta(hours=4), first=timedelta(seconds=10))
    job_queue.run_daily(jobs.check_expiring_services, time=time(hour=9, minute=0))

    logger.info("Bot is starting up with modular structure...")
    
    # --- Run the Bot ---
    # This command starts the bot and keeps it running until you press Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Ensure the event loop is created before running main
    # This is good practice for async applications.
    try:
        main()
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}", exc_info=True)
