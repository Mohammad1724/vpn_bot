# -*- coding: utf-8 -*-

import logging
import asyncio

# <--- FIX: Imports from the new library: python-telegram-bot
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Import configurations and constants
try:
    from config import BOT_TOKEN, ADMIN_ID
    from constants import (
        BUTTON_TEXTS,
        create_main_menu_keyboard,
        create_services_menu_keyboard,
        create_back_keyboard,
        create_cancel_keyboard,
        SELECTING_ACTION,
        SELECTING_SERVICE,
        TYPING_WALLET_AMOUNT,
    )
except ImportError:
    print("Error: config.py or constants.py not found. Please ensure they exist.")
    exit(1)


# Enable logging for better debugging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Handler Functions ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the /start command and displays the main menu."""
    user = update.effective_user
    logger.info(f"User {user.first_name} ({user.id}) started the bot.")
    
    await update.message.reply_text(
        f"سلام {user.mention_html()}! به ربات فروش هیدیفای خوش آمدید.",
        reply_markup=create_main_menu_keyboard(),
        parse_mode='HTML'
    )
    # This is the entry point of our main conversation
    return SELECTING_ACTION

async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the services menu."""
    await update.message.reply_text(
        "لطفا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=create_services_menu_keyboard()
    )
    return SELECTING_ACTION

async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays wallet information and options."""
    # This is a placeholder. You need to implement wallet logic.
    user_id = update.effective_user.id
    # Example: balance = db.get_user_balance(user_id)
    balance = 0 
    await update.message.reply_text(
        f"موجودی کیف پول شما: {balance} تومان.\n"
        "برای افزایش موجودی، لطفا مبلغ مورد نظر را به تومان وارد کنید:",
        reply_markup=create_back_keyboard()
    )
    return TYPING_WALLET_AMOUNT


async def handle_wallet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the amount entered for wallet top-up."""
    amount_text = update.message.text
    try:
        amount = int(amount_text)
        if amount <= 0:
            raise ValueError
        
        # Placeholder for payment logic
        await update.message.reply_text(
            f"درخواست افزایش موجودی به مبلغ {amount} تومان ثبت شد.\n"
            "لطفا از طریق لینک زیر پرداخت را تکمیل کنید: [لینک پرداخت اینجا قرار می‌گیرد]",
            reply_markup=create_main_menu_keyboard()
        )
        return SELECTING_ACTION

    except ValueError:
        await update.message.reply_text(
            "لطفا یک مبلغ معتبر (عدد صحیح و مثبت) وارد کنید.",
            reply_markup=create_back_keyboard()
        )
        return TYPING_WALLET_AMOUNT


async def unhandled_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles any text that doesn't match a specific handler."""
    await update.message.reply_text("متوجه نشدم. لطفا از دکمه‌های زیر استفاده کنید.")


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ends a conversation (e.g., on 'Cancel' or 'Back')."""
    await update.message.reply_text(
        "به منوی اصلی بازگشتید.",
        reply_markup=create_main_menu_keyboard(),
    )
    return SELECTING_ACTION


async def main() -> None:
    """Main function to set up and run the bot."""
    
    # <--- FIX: Bot initialization using ApplicationBuilder
    application = Application.builder().token(BOT_TOKEN).build()
    
    # --- Conversation Handler Setup ---
    # This handler manages the user's flow through the bot's menus.
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['services']}$"), show_services),
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['wallet']}$"), show_wallet),
                # Add handlers for other main menu buttons here
            ],
            TYPING_WALLET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{BUTTON_TEXTS['back']}$"), handle_wallet_amount),
            ],
            # Add more states here, e.g., for purchasing a service
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['back']}$"), done),
            MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['cancel']}$"), done),
        ],
        conversation_timeout=300 # Timeout in seconds
    )

    # Add the main conversation handler to the application
    application.add_handler(conv_handler)
    
    # Add a handler for any other text that wasn't caught by the conversation
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unhandled_text))

    logger.info("Bot is starting...")
    # Run the bot until the user presses Ctrl-C
    await application.run_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"An error occurred in main execution: {e}")
