# -*- coding: utf-8 -*-

import logging

# Imports from the python-telegram-bot library
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Import configurations and constants from local files
try:
    from config import BOT_TOKEN
    from constants import (
        BUTTON_TEXTS,
        create_main_menu_keyboard,
        create_services_menu_keyboard,
        create_back_keyboard,
        SELECTING_ACTION,
        TYPING_WALLET_AMOUNT,
    )
except ImportError as e:
    logging.critical(f"Failed to import config or constants: {e}. Please ensure they exist and are correct.")
    exit(1)

# --- Logging Setup ---
# Configure logging for better debugging and monitoring
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation Handler Functions ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the /start command and displays the main menu."""
    user = update.effective_user
    logger.info(f"User {user.first_name} ({user.id}) started the bot.")
    await update.message.reply_text(
        f"سلام {user.mention_html()}! به ربات فروش هیدیفای خوش آمدید.",
        reply_markup=create_main_menu_keyboard(),
        parse_mode='HTML'
    )
    return SELECTING_ACTION

async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the services menu."""
    await update.message.reply_text(
        "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=create_services_menu_keyboard()
    )
    return SELECTING_ACTION

async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays wallet information and asks for top-up amount."""
    user_id = update.effective_user.id
    balance = 0  # Placeholder, replace with actual database logic
    await update.message.reply_text(
        f"موجودی کیف پول شما: {balance} تومان.\n"
        "برای افزایش موجودی، لطفا مبلغ مورد نظر را به تومان وارد کنید:",
        reply_markup=create_back_keyboard()
    )
    return TYPING_WALLET_AMOUNT

async def handle_wallet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the amount entered for wallet top-up."""
    try:
        amount = int(update.message.text)
        if amount <= 0: raise ValueError
        await update.message.reply_text(
            f"درخواست افزایش موجودی به مبلغ {amount} تومان ثبت شد. (منطق پرداخت پیاده‌سازی نشده)",
            reply_markup=create_main_menu_keyboard()
        )
        return SELECTING_ACTION
    except (ValueError, TypeError):
        await update.message.reply_text(
            "لطفا یک مبلغ معتبر (عدد صحیح و مثبت) وارد کنید.",
            reply_markup=create_back_keyboard()
        )
        return TYPING_WALLET_AMOUNT

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generic handler for 'Back' button to return to the main menu."""
    await update.message.reply_text(
        "به منوی اصلی بازگشتید.",
        reply_markup=create_main_menu_keyboard(),
    )
    return SELECTING_ACTION

async def unhandled_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles any text that doesn't match a specific command or button."""
    await update.message.reply_text(
        "دستور شما شناسایی نشد. لطفا از دکمه‌های منو استفاده کنید.",
        reply_markup=create_main_menu_keyboard()
    )

def main() -> None:
    """Main function to set up and run the bot."""
    
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set in config.py. The bot cannot start.")
        return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()
    
    # --- Conversation Handler Setup ---
    # This handler manages the user's flow through the bot's menus.
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['services']}$"), show_services),
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['wallet']}$"), show_wallet),
                # Add handlers for other main menu buttons here...
            ],
            TYPING_WALLET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{BUTTON_TEXTS['back']}$"), handle_wallet_amount),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['back']}$"), back_to_main_menu),
        ],
        conversation_timeout=600  # 10 minutes
    )

    # Add the main conversation handler to the application
    application.add_handler(conv_handler)
    
    # Add a fallback handler for any text that isn't part of a conversation
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unhandled_text))

    logger.info("Bot configuration is complete. Starting to poll for updates...")
    
    # --- FIX: The library manages its own asyncio loop. We just call this blocking function. ---
    application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"An unrecoverable error occurred during bot execution: {e}", exc_info=True)
