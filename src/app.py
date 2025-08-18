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
from telegram.error import NetworkError

from bot import jobs, constants
from bot.handlers import (
    start as start_h, gift as gift_h, charge as charge_h, buy as buy_h,
    user_services as us_h, account_actions as acc_act, support as support_h
)
from bot.handlers.common_handlers import check_channel_membership
from bot.handlers.admin import (
    common as admin_c, plans as admin_plans, reports as admin_reports,
    settings as admin_settings, backup as admin_backup, users as admin_users,
    gift_codes as admin_gift
)
import bot.handlers.admin.trial_settings_ui as trial_ui
from bot.handlers.trial import get_trial_service as trial_get_trial_service
from config import BOT_TOKEN, ADMIN_ID

warnings.filterwarnings("ignore", category=PTBUserWarning)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, NetworkError) and any(s in str(err) for s in ["ReadError", "Server disconnected", "Timeout"]):
        logging.getLogger("telegram.network").warning("Transient network error ignored: %s", err)
        return
    logger.error("خطا در هنگام پردازش آپدیت:", exc_info=err)
    if isinstance(update, Update):
        logger.error(f"آپدیت مربوطه: {update}")


def build_application():
    request = HTTPXRequest(
        connect_timeout=15.0, read_timeout=180.0, write_timeout=30.0, pool_timeout=90.0
    )

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(jobs.post_init)
        .post_shutdown(jobs.post_shutdown)
        .build()
    )

    application.add_error_handler(error_handler)

    # اطمینان از اینکه ADMIN_ID به صورت int استفاده می‌شود
    try:
        admin_id_int = int(ADMIN_ID)
    except Exception:
        admin_id_int = ADMIN_ID

    admin_filter = filters.User(user_id=admin_id_int)
    user_filter = ~admin_filter

    # --- Conversations ---
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(buy_h.buy_start), pattern='^user_buy_')],
        states={
            constants.GET_CUSTOM_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_h.get_custom_name),
                CommandHandler('skip', buy_h.skip_custom_name),
            ]
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True,
        per_chat=True
    )

    gift_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🎁 کد هدیه$') & user_filter, check_channel_membership(gift_h.gift_code_entry))],
        states={
            constants.REDEEM_GIFT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gift_h.redeem_gift_code)
            ]
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True,
        per_chat=True
    )

    charge_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(charge_h.charge_start), pattern='^user_start_charge$')],
        states={
            constants.CHARGE_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, charge_h.charge_amount_received),
                CallbackQueryHandler(charge_h.charge_amount_confirm_cb, pattern="^charge_amount_(confirm|cancel)$"),
            ],
            constants.CHARGE_RECEIPT: [
                MessageHandler(filters.PHOTO, charge_h.charge_receipt_received)
            ]
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True,
        per_chat=True
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
        states={constants.SUPPORT_TICKET_OPEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_h.forward_to_admin)]},
        fallbacks=[CommandHandler('cancel', support_h.support_ticket_cancel)],
        per_user=True,
        per_chat=True
    )

    # --- Admin Conversations (Nested inside the main admin conv) ---
    # افزودن پلن جدید
    add_plan_conv = ConversationHandler(
        entry_points=[
            # اگر دکمه ReplyKeyboard است:
            MessageHandler(filters.Regex(r'^➕ افزودن پلن جدید$') & admin_filter, admin_plans.add_plan_start),
            # اگر دکمه InlineKeyboard است، callback_data آن را مطابق pattern زیر قرار دهید (یا pattern را تغییر دهید):
            CallbackQueryHandler(admin_plans.add_plan_start, pattern=r'^admin_add_plan$'),
        ],
        states={
            constants.PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_name_received)],
            constants.PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_price_received)],
            constants.PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_days_received)],
            constants.PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_gb_received)],
            constants.PLAN_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.plan_category_received)],
        },
        fallbacks=[CommandHandler('cancel', admin_plans.cancel_add_plan)],
        # چون این کانورسیشن در منوی مدیریت پلن‌ها باز می‌شود، بعد از پایان به همان منو برگرد
        map_to_parent={ConversationHandler.END: constants.PLAN_MENU},
        per_user=True,
        per_chat=True,
        allow_reentry=True
    )

    # تنظیمات ادمین
    admin_settings_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),
            # اگر دکمه اینلاین دارید:
            CallbackQueryHandler(admin_settings.settings_menu, pattern="^admin_settings$")
        ],
        states={
            constants.ADMIN_SETTINGS_MENU: [
                CallbackQueryHandler(admin_settings.maintenance_and_join_submenu, pattern="^settings_maint_join$"),
                CallbackQueryHandler(admin_settings.payment_and_guides_submenu, pattern="^settings_payment_guides$"),
                CallbackQueryHandler(admin_settings.payment_info_submenu, pattern="^payment_info_submenu$"),
                CallbackQueryHandler(admin_settings.service_configs_submenu, pattern="^settings_service_configs$"),
                CallbackQueryHandler(admin_settings.subdomains_submenu, pattern="^settings_subdomains$"),
                CallbackQueryHandler(admin_settings.reports_and_reminders_submenu, pattern="^settings_reports_reminders$"),
                CallbackQueryHandler(admin_settings.edit_default_link_start, pattern="^edit_default_link_type$"),
                CallbackQueryHandler(admin_settings.set_default_link_type, pattern="^set_default_link_"),
                CallbackQueryHandler(admin_settings.toggle_maintenance, pattern="^toggle_maintenance$"),
                CallbackQueryHandler(admin_settings.toggle_force_join, pattern="^toggle_force_join$"),
                CallbackQueryHandler(admin_settings.toggle_expiry_reminder, pattern="^toggle_expiry_reminder$"),
                CallbackQueryHandler(admin_settings.toggle_report_setting, pattern="^toggle_report_"),
                CallbackQueryHandler(trial_ui.trial_menu, pattern="^settings_trial$"),
                CallbackQueryHandler(admin_settings.edit_setting_start, pattern="^admin_edit_setting_"),
            ],
            constants.AWAIT_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_settings.setting_value_received)],
        },
        fallbacks=[
            CommandHandler('cancel', admin_c.admin_generic_cancel),
            CallbackQueryHandler(admin_settings.settings_menu, pattern="^back_to_settings$")
        ],
        map_to_parent={constants.ADMIN_MENU: constants.ADMIN_MENU, ConversationHandler.END: constants.ADMIN_MENU},
        per_user=True,
        per_chat=True,
        allow_reentry=True
    )

    # --- Main Admin Conversation ---
    admin_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f'^{constants.BTN_ADMIN_PANEL}$') & admin_filter, admin_c.admin_entry),
            # اگر ورود با اینلاین باشد:
            CallbackQueryHandler(admin_c.admin_entry, pattern="^admin_panel$")
        ],
        states={
            # منوی اصلی ادمین
            constants.ADMIN_MENU: [
                # ReplyKeyboard دکمه‌ها
                MessageHandler(filters.Regex('^➕ مدیریت پلن‌ها$'), admin_plans.plan_management_menu),
                MessageHandler(filters.Regex('^📈 گزارش‌ها و آمار$'), admin_reports.reports_menu),
                MessageHandler(filters.Regex('^💾 پشتیبان‌گیری$'), admin_backup.backup_restore_menu),
                MessageHandler(filters.Regex('^👥 مدیریت کاربران$'), admin_users.user_management_menu),
                MessageHandler(filters.Regex('^🎁 مدیریت کد هدیه$'), admin_gift.gift_code_management_menu),
                MessageHandler(filters.Regex('^📩 ارسال پیام$'), admin_users.broadcast_menu),
                MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$'), admin_c.shutdown_bot),

                # InlineKeyboard دکمه‌های معادل (در صورت استفاده)
                CallbackQueryHandler(admin_plans.plan_management_menu, pattern="^admin_plans$"),
                CallbackQueryHandler(admin_reports.reports_menu, pattern="^admin_reports$"),
                CallbackQueryHandler(admin_backup.backup_restore_menu, pattern="^admin_backup$"),
                CallbackQueryHandler(admin_users.user_management_menu, pattern="^admin_users$"),
                CallbackQueryHandler(admin_gift.gift_code_management_menu, pattern="^admin_gift$"),
                CallbackQueryHandler(admin_users.broadcast_menu, pattern="^admin_broadcast$"),
                CallbackQueryHandler(admin_c.shutdown_bot, pattern="^admin_shutdown$"),

                # کانورسیشن تنظیمات داخل منوی اصلی
                admin_settings_conv,
            ],
            # منوی مدیریت پلن‌ها
            constants.PLAN_MENU: [
                # کانورسیشن افزودن پلن جدید داخل این منو
                add_plan_conv,
                # در صورت داشتن دکمه‌های دیگر (ویرایش/حذف/لیست/بازگشت) اینجا اضافه کنید
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{constants.BTN_EXIT_ADMIN_PANEL}$'), admin_c.exit_admin_panel),
            CommandHandler('cancel', admin_c.admin_generic_cancel)
        ],
        per_user=True,
        per_chat=True,
        allow_reentry=True
    )

    application.add_handler(charge_conv)
    application.add_handler(gift_conv)
    application.add_handler(buy_conv)
    application.add_handler(transfer_conv)
    application.add_handler(gift_from_balance_conv)
    application.add_handler(support_conv)
    application.add_handler(admin_conv)

    # --- Global Callbacks ---
    application.add_handler(CallbackQueryHandler(buy_h.confirm_purchase_callback, pattern="^confirmbuy$"), group=2)
    application.add_handler(CallbackQueryHandler(buy_h.cancel_purchase_callback, pattern="^cancelbuy$"), group=2)
    application.add_handler(MessageHandler(filters.REPLY & admin_filter, support_h.admin_reply_handler))
    application.add_handler(CallbackQueryHandler(support_h.close_ticket, pattern="^close_ticket_"))
    application.add_handler(CallbackQueryHandler(admin_users.admin_confirm_charge_callback, pattern="^admin_confirm_charge_"), group=1)
    application.add_handler(CallbackQueryHandler(admin_users.admin_reject_charge_callback, pattern="^admin_reject_charge_"), group=1)
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.start), pattern="^check_membership$"))

    # --- Other Handlers ---
    user_services_handlers = [
        CallbackQueryHandler(check_channel_membership(us_h.view_service_callback), pattern="^view_service_"),
        CallbackQueryHandler(check_channel_membership(us_h.back_to_services_callback), pattern="^back_to_services$"),
        CallbackQueryHandler(check_channel_membership(us_h.get_link_callback), pattern="^getlink_"),
        CallbackQueryHandler(check_channel_membership(us_h.refresh_service_details), pattern="^refresh_"),
        CallbackQueryHandler(check_channel_membership(us_h.more_links_callback), pattern="^more_links_"),
        CallbackQueryHandler(check_channel_membership(us_h.renew_service_handler), pattern="^renew_"),
        CallbackQueryHandler(check_channel_membership(us_h.confirm_renewal_callback), pattern="^confirmrenew$"),
        CallbackQueryHandler(check_channel_membership(us_h.cancel_renewal_callback), pattern="^cancelrenew$"),
        CallbackQueryHandler(check_channel_membership(us_h.delete_service_callback), pattern="^delete_service_"),
    ]
    for handler in user_services_handlers:
        application.add_handler(handler, group=2)

    account_info_handlers = [
        CallbackQueryHandler(check_channel_membership(start_h.show_purchase_history_callback), pattern="^acc_purchase_history$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_charge_history_callback), pattern="^acc_charge_history$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_charging_guide_callback), pattern="^acc_charging_guide$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_account_info), pattern="^acc_back_to_main$"),
    ]
    for handler in account_info_handlers:
        application.add_handler(handler)

    guide_handlers = [
        CallbackQueryHandler(check_channel_membership(start_h.show_guide_content), pattern="^guide_(connection|charging|buying)$"),
        CallbackQueryHandler(check_channel_membership(start_h.back_to_guide_menu), pattern="^guide_back_to_menu$"),
    ]
    for handler in guide_handlers:
        application.add_handler(handler)

    plan_category_handlers = [
        CallbackQueryHandler(check_channel_membership(buy_h.show_plans_in_category), pattern="^user_cat_"),
        CallbackQueryHandler(check_channel_membership(buy_h.buy_service_list), pattern="^back_to_cats$"),
    ]
    for handler in plan_category_handlers:
        application.add_handler(handler)

    main_menu_handlers = [
        CommandHandler("start", check_channel_membership(start_h.start)),
        MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), check_channel_membership(buy_h.buy_service_list)),
        MessageHandler(filters.Regex('^📋 سرویس‌های من$'), check_channel_membership(us_h.list_my_services)),
        MessageHandler(filters.Regex('^👤 اطلاعات حساب کاربری$'), check_channel_membership(start_h.show_account_info)),
        MessageHandler(filters.Regex('^📚 راهنما$'), check_channel_membership(start_h.show_guide)),
        MessageHandler(filters.Regex('^🧪 دریافت سرویس تست رایگان$'), check_channel_membership(trial_get_trial_service)),
        MessageHandler(filters.Regex('^🎁 معرفی دوستان$'), check_channel_membership(start_h.show_referral_link)),
    ]
    for handler in main_menu_handlers:
        application.add_handler(handler, group=3)

    return application