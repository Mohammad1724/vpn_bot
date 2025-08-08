# -*- coding: utf-8 -*-

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

try:
    from config import BOT_TOKEN, ADMIN_ID
    from constants import (
        BUTTON_TEXTS,
        create_main_menu_keyboard,
        create_services_menu_keyboard,
        create_admin_menu_keyboard,
        create_back_keyboard,
        SELECTING_ACTION,
        TYPING_WALLET_AMOUNT,
        SELECTING_ADMIN_ACTION,
    )
except ImportError as e:
    logging.critical(f"Failed to import from config or constants: {e}")
    exit(1)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- User Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles /start. Differentiates between admin and regular user."""
    user = update.effective_user
    user_id = user.id

    # --- FIX: Added detailed logging for debugging the admin check ---
    logger.info("--- ADMIN CHECK ---")
    logger.info(f"User ID from Telegram: {user_id} (Type: {type(user_id)})")
    logger.info(f"Admin ID from config.py: {ADMIN_ID} (Type: {type(ADMIN_ID)})")

    # --- FIX: Forcing both IDs to be integers before comparison for robustness ---
    try:
        is_admin = (int(user_id) == int(ADMIN_ID))
    except (ValueError, TypeError):
        is_admin = False # If conversion fails, they are not admin.
    
    logger.info(f"Comparison result (is_admin): {is_admin}")
    logger.info("-------------------")
    
    reply_text = f"سلام {user.mention_html()}! به ربات فروش هیدیفای خوش آمدید."
    if is_admin:
        reply_text = f"سلام ادمین. به ربات خوش آمدید. پنل مدیریت برای شما در دسترس است."
        
    await update.message.reply_text(
        reply_text,
        reply_markup=create_main_menu_keyboard(is_admin=is_admin),
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
    balance = 0  # Placeholder for DB logic
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
        is_admin = (int(update.effective_user.id) == int(ADMIN_ID))
        await update.message.reply_text(
            f"درخواست افزایش موجودی به مبلغ {amount} تومان ثبت شد. (منطق پرداخت پیاده‌سازی نشده)",
            reply_markup=create_main_menu_keyboard(is_admin=is_admin)
        )
        return SELECTING_ACTION
    except (ValueError, TypeError):
        await update.message.reply_text(
            "لطفا یک مبلغ معتبر (عدد صحیح و مثبت) وارد کنید.",
            reply_markup=create_back_keyboard()
        )
        return TYPING_WALLET_AMOUNT

# --- Admin Handlers ---

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows the admin-specific menu."""
    if int(update.effective_user.id) != int(ADMIN_ID):
        return SELECTING_ACTION

    await update.message.reply_text(
        "شما در پنل مدیریت هستید. لطفا یک گزینه را انتخاب کنید:",
        reply_markup=create_admin_menu_keyboard()
    )
    return SELECTING_ADMIN_ACTION

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Placeholder for the broadcast functionality."""
    await update.message.reply_text("ویژگی ارسال پیام همگانی در حال توسعه است.")
    return SELECTING_ADMIN_ACTION

# --- Common Handlers ---

async def unhandled_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles any text that doesn't match a specific command or button."""
    is_admin = (int(update.effective_user.id) == int(ADMIN_ID))
    await update.message.reply_text(
        "دستور شما شناسایی نشد. لطفا از دکمه‌های منو استفاده کنید.",
        reply_markup=create_main_menu_keyboard(is_admin=is_admin)
    )

def main() -> None:
    """Main function to set up and run the bot."""
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set in config.py. The bot cannot start.")
        return

    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['services']}$"), show_services),
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['wallet']}$"), show_wallet),
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['admin_panel']}$"), show_admin_panel),
            ],
            TYPING_WALLET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{BUTTON_TEXTS['back']}$"), handle_wallet_amount),
            ],
            SELECTING_ADMIN_ACTION: [
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['broadcast']}$"), admin_broadcast),
                MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['back_to_user_menu']}$"), start),
            ]
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(f"^{BUTTON_TEXTS['back']}$"), start),
        ],
        conversation_timeout=600
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unhandled_text))

    logger.info("Bot configuration is complete. Starting to poll for updates...")
    application.run_polling()

if __name__ == "__main__":
    main()
