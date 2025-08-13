# -*- coding: utf-8 -*-

import logging
import warnings
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    ApplicationBuilder, ConversationHandler, MessageHandler, CallbackQueryHandler,
    CommandHandler, filters, ContextTypes
)
from telegram import Update
from telegram.request import HTTPXRequest

from bot import jobs, constants
from bot.handlers import start as start_h
from bot.handlers import gift as gift_h
from bot.handlers import charge as charge_h
from bot.handlers import buy as buy_h
from bot.handlers import user_services as us_h
from bot.handlers import account_actions as acc_act
from bot.handlers import support as support_h
from bot.handlers.common_handlers import check_channel_membership
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
    request = HTTPXRequest(connect_timeout=10.0, read_timeout=30.0, write_timeout=30.0, pool_timeout=60.0)
    
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(jobs.post_init)
        .post_shutdown(jobs.post_shutdown)
        .build()
    )
    application.add_error_handler(error_handler)

    admin_filter = filters.User(user_id=ADMIN_ID)
    user_filter = ~admin_filter

    # --- User-facing Conversations (Top-level) ---
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(buy_h.buy_start), pattern='^user_buy_')],
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
        entry_points=[MessageHandler(filters.Regex('^🎁 کد هدیه$') & user_filter, check_channel_membership(gift_h.gift_code_entry))],
        states={constants.REDEEM_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift_h.redeem_gift_code)]},
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True, per_chat=True
    )

    charge_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(charge_h.charge_start), pattern='^user_start_charge$')],
        states={
            constants.CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_h.charge_amount_received)],
            constants.CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_h.charge_receipt_received)]
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True, per_chat=True
    )

    transfer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(acc_act.transfer_start), pattern="^acc_transfer_start$")],
        states={
            constants.TRANSFER_RECIPIENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, acc_act.transfer_recipient_received)],
            constants.TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, acc_act.transfer_amount_received)],
            constants.TRANSFER_CONFIRM: [CallbackQueryHandler(acc_act.transfer_confirm, pattern="^transfer_confirm_")],
        },
        fallbacks=[CommandHandler('cancel', acc_act.transfer_cancel)]
    )

    gift_from_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(acc_act.create_gift_from_balance_start), pattern="^acc_gift_from_balance_start$")],
        states={
            constants.GIFT_FROM_BALANCE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, acc_act.create_gift_amount_received)],
            constants.GIFT_FROM_BALANCE_CONFIRM: [CallbackQueryHandler(acc_act.create_gift_confirm, pattern="^gift_confirm_")],
        },
        fallbacks=[CommandHandler('cancel', acc_act.create_gift_cancel)]
    )

    support_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📞 پشتیبانی$') & user_filter, check_channel_membership(support_h.support_ticket_start))],
        states={
            constants.SUPPORT_TICKET_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_h.support_message_received)],
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True, per_chat=True
    )

    # --- Admin Nested Conversations ---
    add_plan_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ افزودن پلن جدید$') & admin_filter, admin_plans.add_plan_start)],
        states={
            constants.PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_name_received)],
            constants.PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_price_received)],
            constants.PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_days_received)],
            constants.PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_gb_received)],
        },
        fallbacks=[CommandHandler('cancel', admin_plans.cancel_add_plan)],
        map_to_parent={ConversationHandler.END: constants.PLAN_MENU}
    )

    edit_plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_plans.edit_plan_start, pattern="^admin_edit_plan_")],
        states={
            constants.EDIT_PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_name_received), CommandHandler('skip', admin_plans.skip_edit_plan_name)],
            constants.EDIT_PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_price_received), CommandHandler('skip', admin_plans.skip_edit_plan_price)],
            constants.EDIT_PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_days_received), CommandHandler('skip', admin_plans.skip_edit_plan_days)],
            constants.EDIT_PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_gb_received), CommandHandler('skip', admin_plans.skip_edit_plan_gb)],
        },
        fallbacks=[CommandHandler('cancel', admin_plans.cancel_edit_plan)],
        map_to_parent={constants.PLAN_MENU: constants.PLAN_MENU, ConversationHandler.END: constants.PLAN_MENU}
    )

    create_gift_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ ساخت کد هدیه جدید$') & admin_filter, admin_gift.create_gift_code_start)],
        states={admin_gift.CREATE_GIFT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift.create_gift_amount_received)]},
        fallbacks=[CommandHandler('cancel', admin_c.admin_conv_cancel)],
        map_to_parent={ConversationHandler.END: constants.ADMIN_MENU}
    )

    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_settings.edit_setting_start, pattern="^admin_edit_setting_")],
        states={constants.AWAIT_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_settings.setting_value_received)]},
        fallbacks=[CommandHandler('cancel', admin_c.admin_conv_cancel)],
        map_to_parent={constants.ADMIN_MENU: constants.ADMIN_MENU, ConversationHandler.END: constants.ADMIN_MENU}
    )

    broadcast_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📩 ارسال پیام$') & admin_filter, admin_users.broadcast_menu)],
        states={
            constants.BROADCAST_MENU: [
                MessageHandler(filters.Regex('^ارسال به همه کاربران$') & admin_filter, admin_users.broadcast_to_all_start),
                MessageHandler(filters.Regex('^ارسال به کاربر خاص$') & admin_filter, admin_users.broadcast_to_user_start),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.back_to_admin_menu),
            ],
            constants.BROADCAST_MESSAGE: [MessageHandler((~filters.COMMAND) & admin_filter, admin_users.broadcast_to_all_confirm)],
            constants.BROADCAST_CONFIRM: [CallbackQueryHandler(admin_users.broadcast_confirm_callback, pattern="^broadcast_confirm_(yes|no)$")],
            constants.BROADCAST_TO_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_users.broadcast_to_user_id_received)],
            constants.BROADCAST_TO_USER_MESSAGE: [MessageHandler((~filters.COMMAND) & admin_filter, admin_users.broadcast_to_user_message_received)],
        },
        fallbacks=[CommandHandler('cancel', admin_c.admin_conv_cancel)],
        map_to_parent={ConversationHandler.END: constants.ADMIN_MENU}
    )
    
    backup_settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_backup.edit_backup_target_start, pattern="^edit_backup_target$")],
        states={
            constants.AWAIT_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_backup.backup_target_received)],
        },
        fallbacks=[CommandHandler('cancel', admin_backup.cancel_backup_settings)],
        map_to_parent={constants.BACKUP_MENU: constants.BACKUP_MENU, ConversationHandler.END: constants.BACKUP_MENU}
    )

    # --- Main Admin Conversation (Parent) ---
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{constants.BTN_ADMIN_PANEL}$') & admin_filter, admin_c.admin_entry)],
        states={
            constants.ADMIN_MENU: [
                MessageHandler(filters.Regex('^➕ مدیریت پلن‌ها$'), admin_plans.plan_management_menu),
                MessageHandler(filters.Regex('^📈 گزارش‌ها و آمار$'), admin_reports.reports_menu),
                MessageHandler(filters.Regex('^⚙️ تنظیمات$'), admin_settings.settings_menu),
                MessageHandler(filters.Regex('^💾 پشتیبان‌گیری$'), admin_backup.backup_restore_menu),
                MessageHandler(filters.Regex('^👥 مدیریت کاربران$'), admin_users.user_management_menu),
                MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$'), admin_c.shutdown_bot),
                MessageHandler(filters.Regex('^🎁 مدیریت کد هدیه$'), admin_gift.gift_code_management_menu),
                MessageHandler(filters.Regex('^📋 لیست کدهای هدیه$'), admin_gift.list_gift_codes),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$'), admin_c.back_to_admin_menu),
                create_gift_conv,
                settings_conv,
                broadcast_conv,
                CallbackQueryHandler(admin_settings.back_to_admin_menu_cb, pattern="^admin_back_to_menu$"),
            ],
            constants.REPORTS_MENU: [
                MessageHandler(filters.Regex('^📊 آمار کلی$'), admin_reports.show_stats_report),
                MessageHandler(filters.Regex('^📈 گزارش فروش امروز$'), admin_reports.show_daily_report),
                MessageHandler(filters.Regex('^📅 گزارش فروش ۷ روز اخیر$'), admin_reports.show_weekly_report),
                MessageHandler(filters.Regex('^🏆 محبوب‌ترین پلن‌ها$'), admin_reports.show_popular_plans_report),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$'), admin_c.back_to_admin_menu),
            ],
            constants.PLAN_MENU: [
                add_plan_conv,
                edit_plan_conv,
                MessageHandler(filters.Regex('^📋 لیست پلن‌ها$'), admin_plans.list_plans_admin),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$'), admin_c.back_to_admin_menu),
                CallbackQueryHandler(admin_plans.admin_delete_plan_callback, pattern="^admin_delete_plan_"),
                CallbackQueryHandler(admin_plans.admin_toggle_plan_visibility_callback, pattern="^admin_toggle_plan_"),
            ],
            constants.BACKUP_MENU: [
                MessageHandler(filters.Regex('^📥 دریافت فایل پشتیبان$') & admin_filter, admin_backup.send_backup_file),
                MessageHandler(filters.Regex('^📤 بارگذاری فایل پشتیبان$') & admin_filter, admin_backup.restore_start),
                MessageHandler(filters.Regex('^⚙️ تنظیمات پشتیبان‌گیری خودکار$') & admin_filter, admin_backup.edit_auto_backup_start),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.back_to_admin_menu),
                CallbackQueryHandler(admin_backup.admin_confirm_restore_callback, pattern="^admin_confirm_restore$"),
                CallbackQueryHandler(admin_backup.admin_cancel_restore_callback, pattern="^admin_cancel_restore$"),
                CallbackQueryHandler(admin_backup.edit_backup_interval_start, pattern="^edit_backup_interval$"),
                backup_settings_conv,
            ],
            constants.RESTORE_UPLOAD: [
                MessageHandler(filters.Document.ALL & admin_filter, admin_backup.restore_receive_file),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.back_to_admin_menu),
            ],
            constants.MANAGE_USER_ID: [
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$'), admin_c.back_to_admin_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_users.manage_user_id_received)
            ],
            constants.MANAGE_USER_ACTION: [
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$'), admin_c.back_to_admin_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_users.manage_user_action_handler)
            ],
            constants.MANAGE_USER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_users.manage_user_amount_received)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{constants.BTN_EXIT_ADMIN_PANEL}$'), admin_c.exit_admin_panel),
            CommandHandler('cancel', admin_c.admin_generic_cancel),
        ],
        per_user=True, per_chat=True, allow_reentry=True
    )

    # --- Register handlers ---
    application.add_handler(charge_conv)
    application.add_handler(gift_conv)
    application.add_handler(buy_conv)
    application.add_handler(admin_conv)
    application.add_handler(transfer_conv)
    application.add_handler(gift_from_balance_conv)
    application.add_handler(support_conv)

    # Handler for admin replies to support tickets
    application.add_handler(MessageHandler(filters.REPLY & admin_filter, support_h.admin_reply_handler))

    # Global callbacks (with higher priority)
    application.add_handler(CallbackQueryHandler(admin_users.admin_confirm_charge_callback, pattern="^admin_confirm_charge_"), group=1)
    application.add_handler(CallbackQueryHandler(admin_users.admin_reject_charge_callback, pattern="^admin_reject_charge_"), group=1)
    
    # Settings Submenus
    application.add_handler(CallbackQueryHandler(admin_settings.maintenance_submenu, pattern="^settings_maintenance$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.force_join_submenu, pattern="^settings_force_join$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.expiry_submenu, pattern="^settings_expiry$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.payment_submenu, pattern="^settings_payment$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.subdomains_submenu, pattern="^settings_subdomains$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.other_settings_submenu, pattern="^settings_other$"), group=1)
    
    # Other settings callbacks
    application.add_handler(CallbackQueryHandler(admin_settings.edit_default_link_start, pattern="^edit_default_link_type$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.set_default_link_type, pattern="^set_default_link_"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.settings_menu, pattern="^back_to_settings$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_gift.delete_gift_code_callback, pattern="^delete_gift_code_"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.toggle_report_setting, pattern="^toggle_report_"), group=1)
    application.add_handler(CallbackQueryHandler(admin_backup.set_backup_interval, pattern="^set_backup_interval_"), group=1)
    application.add_handler(CallbackQueryHandler(admin_backup.backup_restore_menu, pattern="^back_to_backup_menu$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.toggle_maintenance, pattern="^toggle_maintenance$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.toggle_expiry_reminder, pattern="^toggle_expiry_reminder$"), group=1)
    application.add_handler(CallbackQueryHandler(admin_settings.toggle_force_join, pattern="^toggle_force_join$"), group=1)
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.start), pattern="^check_membership$"))

    # User services callbacks
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.view_service_callback), pattern="^view_service_"), group=2)
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.back_to_services_callback), pattern="^back_to_services$"), group=2)
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.get_link_callback), pattern="^getlink_"), group=2)
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.refresh_service_details), pattern="^refresh_"), group=2)
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.more_links_callback), pattern="^more_links_"), group=2)
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.renew_service_handler), pattern="^renew_"), group=2)
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.confirm_renewal_callback), pattern="^confirmrenew$"), group=2)
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.cancel_renewal_callback), pattern="^cancelrenew$"), group=2)
    application.add_handler(CallbackQueryHandler(check_channel_membership(us_h.delete_service_callback), pattern="^delete_service_"), group=2)

    # Account info callbacks
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.show_purchase_history_callback), pattern="^acc_purchase_history$"))
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.show_charge_history_callback), pattern="^acc_charge_history$"))
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.show_charging_guide_callback), pattern="^acc_charging_guide$"))
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.show_account_info), pattern="^acc_back_to_main$"))

    # Main commands and menus
    application.add_handler(CommandHandler("start", check_channel_membership(start_h.start)), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), check_channel_membership(buy_h.buy_service_list)), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📋 سرویس‌های من$'), check_channel_membership(us_h.list_my_services)), group=3)
    application.add_handler(MessageHandler(filters.Regex('^👤 اطلاعات حساب کاربری$'), check_channel_membership(start_h.show_account_info)), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), check_channel_membership(support_h.support_ticket_start)), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📚 راهنمای اتصال$'), check_channel_membership(start_h.show_guide)), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🧪 دریافت سرویس تست رایگان$'), check_channel_membership(trial_get_trial_service)), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🎁 معرفی دوستان$'), check_channel_membership(start_h.show_referral_link)), group=3)

    return application