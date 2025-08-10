# -*- coding: utf-8 -*-

import logging
import warnings
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    ApplicationBuilder, ConversationHandler, MessageHandler, CallbackQueryHandler,
    CommandHandler, filters, ContextTypes
)
from telegram import Update

from bot import jobs, constants
from bot.handlers import start as start_h
from bot.handlers import gift as gift_h
from bot.handlers import charge as charge_h
from bot.handlers import buy as buy_h
from bot.handlers import user_services as us_h
from bot.handlers import account_actions  # جدید
from bot.handlers.admin import common as admin_c
from bot.handlers.admin import plans as admin_plans
from bot.handlers.admin import reports as admin_reports
from bot.handlers.admin import settings as admin_settings
from bot.handlers.admin import backup as admin_backup
from bot.handlers.admin import users as admin_users
from bot.handlers.admin import gift_codes as admin_gift
from bot.handlers.trial import get_trial_service as trial_get_trial_service
from config import BOT_TOKEN, ADMIN_ID

warnings.filterwarnings("ignore", category=PTBUserWarning)
logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("خطا در هنگام پردازش آپدیت:", exc_info=context.error)
    if isinstance(update, Update):
        logger.error(f"آپدیت مربوطه: {update}")

def build_application():
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(jobs.post_init).post_shutdown(jobs.post_shutdown).build()
    application.add_error_handler(error_handler)

    admin_filter = filters.User(user_id=ADMIN_ID)
    user_filter = ~admin_filter

    # --- User-facing Conversations ---
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_h.buy_start, pattern='^user_buy_')],
        states={
            constants.GET_CUSTOM_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_h.get_custom_name),
                CommandHandler('skip', buy_h.skip_custom_name)
            ],
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True, per_chat=True
    )

    gift_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🎁 کد هدیه$') & user_filter, gift_h.gift_code_entry)],
        states={constants.REDEEM_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_h.redeem_gift_code)]},
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True, per_chat=True
    )

    charge_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(charge_h.charge_start, pattern='^user_start_charge$')],
        states={
            constants.CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_h.charge_amount_received)],
            constants.CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_h.charge_receipt_received)]
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True, per_chat=True
    )

    # New conversations for account actions
    transfer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(account_actions.transfer_start, pattern="^acc_transfer_start$")],
        states={
            constants.TRANSFER_RECIPIENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_actions.transfer_recipient_received)],
            constants.TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_actions.transfer_amount_received)],
            constants.TRANSFER_CONFIRM: [CallbackQueryHandler(account_actions.transfer_confirm, pattern="^transfer_confirm_")],
        },
        fallbacks=[CommandHandler('cancel', account_actions.transfer_cancel)]
    )

    gift_from_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(account_actions.create_gift_from_balance_start, pattern="^acc_gift_from_balance_start$")],
        states={
            constants.GIFT_FROM_BALANCE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, account_actions.create_gift_amount_received)],
            constants.GIFT_FROM_BALANCE_CONFIRM: [CallbackQueryHandler(account_actions.create_gift_confirm, pattern="^gift_confirm_")],
        },
        fallbacks=[CommandHandler('cancel', account_actions.create_gift_cancel)]
    )

    # --- Admin Nested Conversations (مثل نسخه قبلی شما) ---
    # add_plan_conv, edit_plan_conv, create_gift_conv, settings_conv, broadcast_conv, admin_conv
    # فرض می‌کنیم قبلاً در فایل حاضر کامل پیاده است (به‌روز شده‌های قبل)

    # --- Register handlers ---
    application.add_handler(charge_conv)
    application.add_handler(gift_conv)
    application.add_handler(buy_conv)
    # admin_conv را از نسخه قبلی‌تان اضافه کنید (اینجا صرفاً روی User و اکشن‌های جدید تمرکز داریم)
    application.add_handler(transfer_conv)
    application.add_handler(gift_from_balance_conv)

    # Account info callbacks
    application.add_handler(CallbackQueryHandler(start_h.show_purchase_history_callback, pattern="^acc_purchase_history$"))
    application.add_handler(CallbackQueryHandler(start_h.show_charge_history_callback, pattern="^acc_charge_history$"))
    application.add_handler(CallbackQueryHandler(start_h.show_charging_guide_callback, pattern="^acc_charging_guide$"))
    application.add_handler(CallbackQueryHandler(start_h.show_account_info, pattern="^acc_back_to_main$"))

    # Main commands and menus
    application.add_handler(CommandHandler("start", start_h.start), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), buy_h.buy_service_list), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📋 سرویس‌های من$'), us_h.list_my_services), group=3)
    application.add_handler(MessageHandler(filters.Regex('^👤 اطلاعات حساب کاربری$'), start_h.show_account_info), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), start_h.show_support), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📚 راهنمای اتصال$'), start_h.show_guide), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🧪 دریافت سرویس تست رایگان$'), trial_get_trial_service), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🎁 معرفی دوستان$'), start_h.show_referral_link), group=3)

    return application