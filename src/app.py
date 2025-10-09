# filename: app.py
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
    user_services as us_h, account_actions as acc_act, support as support_h,
    usage as usage_h
)
from bot.handlers.common_handlers import check_channel_membership
from bot.handlers.admin import (
    common as admin_c, plans as admin_plans, reports as admin_reports,
    settings as admin_settings, backup as admin_backup, users as admin_users,
    gift_codes as admin_gift
)
import bot.handlers.admin.trial_settings_ui as trial_ui
from bot.handlers.trial import get_trial_service as trial_get_trial_service
from bot.handlers.admin.trial_settings import set_trial_days, set_trial_gb
# NEW: Multi-panel selection for buying
from bot.handlers import buy_panels

from config import BOT_TOKEN, ADMIN_ID

warnings.filterwarnings("ignore", category=PTBUserWarning)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, NetworkError) and any(s in str(err) for s in ["ReadError", "Server disconnected", "Timeout"]):
        logging.getLogger("telegram.network").warning("Transient network error ignored: %s", err)
        return
    logger.exception("خطا در هنگام پردازش آپدیت")
    if isinstance(update, Update):
        logger.error("آپدیت مربوطه: %s", update)


def build_application():
    request = HTTPXRequest(connect_timeout=15.0, read_timeout=75.0, write_timeout=30.0, pool_timeout=90.0)

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(jobs.post_init)
        .post_shutdown(jobs.post_shutdown)
        .build()
    )
    application.add_error_handler(error_handler)

    # Filters
    try:
        admin_id_int = int(ADMIN_ID)
    except Exception:
        admin_id_int = ADMIN_ID
    admin_filter = filters.User(user_id=admin_id_int)
    user_filter = ~admin_filter

    # Router for AWAIT_SETTING_VALUE (settings vs backup target)
    async def await_setting_value_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('awaiting_backup_target'):
            return await admin_backup.backup_target_received(update, context)
        return await admin_settings.setting_value_received(update, context)

    # --- Helper to exit charge conversation cleanly ---
    async def exit_charge_to_account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['charge_is_exiting_to_acc'] = True
        await charge_h.charge_cancel(update, context)
        await start_h.show_account_info(update, context)
        return ConversationHandler.END

    # --------- BUY FLOW ----------
    buy_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(check_channel_membership(buy_h.buy_start), pattern=r'^user_buy_'),
            CallbackQueryHandler(check_channel_membership(buy_h.back_to_promo_from_confirm), pattern=r'^buy_back_to_promo$'),
        ],
        states={
            constants.GET_CUSTOM_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_h.get_custom_name),
                CallbackQueryHandler(buy_h.back_to_cats_from_name, pattern=r'^buy_back_to_cats$'),
                CallbackQueryHandler(buy_h.skip_name_callback, pattern=r'^buy_skip_name$'),
                CallbackQueryHandler(buy_h.cancel_buy_callback, pattern=r'^buy_cancel$'),
            ],
            constants.PROMO_CODE_ENTRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_h.promo_code_received),
                CallbackQueryHandler(buy_h.back_to_name_callback, pattern=r'^buy_back_to_name$'),
                CallbackQueryHandler(buy_h.skip_promo_callback, pattern=r'^buy_skip_promo$'),
                CallbackQueryHandler(buy_h.cancel_buy_callback, pattern=r'^buy_cancel$'),
                CommandHandler('skip', buy_h.promo_code_received),
            ],
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True, per_chat=True,
        allow_reentry=True
    )

    # --------- GIFT (user) ----------
    gift_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^🎁 کد هدیه$') & user_filter, check_channel_membership(gift_h.gift_code_entry))
        ],
        states={
            constants.REDEEM_GIFT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gift_h.redeem_gift_code)
            ],
        },
        fallbacks=[CommandHandler('cancel', start_h.user_generic_cancel)],
        per_user=True, per_chat=True
    )

    # --------- CHARGE (user) ----------
    charge_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'.*💳.*') & user_filter, check_channel_membership(charge_h.charge_menu_start)),
            CallbackQueryHandler(check_channel_membership(charge_h.charge_menu_start), pattern=r'^(user_start_charge|acc_start_charge|acc_charge)$'),
        ],
        states={
            constants.CHARGE_MENU: [
                CallbackQueryHandler(charge_h.show_referral_info_inline, pattern=r"^acc_referral$"),
                CallbackQueryHandler(charge_h.charge_start_payment, pattern=r"^charge_start_payment$"),
                CallbackQueryHandler(charge_h.charge_menu_start, pattern=r"^charge_menu_main$"),
            ],
            constants.CHARGE_AMOUNT: [
                CallbackQueryHandler(charge_h.charge_amount_confirm_cb, pattern=r"^charge_amount_\d+$"),
                CallbackQueryHandler(charge_h.ask_custom_amount, pattern=r"^charge_custom_amount$"),
                CallbackQueryHandler(charge_h.charge_menu_start, pattern=r"^charge_menu_main$"),
            ],
            constants.AWAIT_CUSTOM_AMOUNT: [
                MessageHandler(filters.Regex(r'^\s*[\d۰-۹ ,]+\s*$'), charge_h.charge_amount_received),
                CallbackQueryHandler(charge_h.charge_start_payment, pattern=r"^charge_start_payment_back$"),
            ],
            constants.CHARGE_RECEIPT: [
                MessageHandler(filters.PHOTO, charge_h.charge_receipt_received),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(exit_charge_to_account_menu, pattern=r"^acc_back_to_main$"),
            CommandHandler('cancel', charge_h.charge_cancel),
            CallbackQueryHandler(start_h.start, pattern=r"^home_menu$"),
        ],
        per_user=True, per_chat=True,
        allow_reentry=True
    )

    # --------- TRANSFER ----------
    transfer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(acc_act.transfer_start), pattern=r"^acc_transfer_start$")],
        states={
            constants.TRANSFER_RECIPIENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, acc_act.transfer_recipient_received)],
            constants.TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, acc_act.transfer_amount_received)],
            constants.TRANSFER_CONFIRM: [CallbackQueryHandler(acc_act.transfer_confirm, pattern=r"^transfer_confirm_")],
        },
        fallbacks=[CommandHandler('cancel', acc_act.transfer_cancel)]
    )

    # --------- GIFT FROM BALANCE ----------
    gift_from_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(acc_act.create_gift_from_balance_start), pattern=r"^acc_gift_from_balance_start$")],
        states={
            constants.GIFT_FROM_BALANCE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, acc_act.create_gift_amount_received)],
            constants.GIFT_FROM_BALANCE_CONFIRM: [CallbackQueryHandler(acc_act.create_gift_confirm, pattern=r"^gift_confirm_")],
        },
        fallbacks=[CommandHandler('cancel', acc_act.create_gift_cancel)]
    )

    # --------- SUPPORT (user inline) ----------
    support_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^📞 پشتیبانی$') & user_filter, check_channel_membership(support_h.support_ticket_start))
        ],
        states={
            constants.SUPPORT_TICKET_OPEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_h.forward_to_admin),
                CallbackQueryHandler(support_h.support_end_cb, pattern=r"^support_end$"),
                CallbackQueryHandler(support_h.support_back_to_main_cb, pattern=r"^support_back_main$"),
                CallbackQueryHandler(support_h.support_back_to_main_cb, pattern=r"^home_menu$"),
            ],
        },
        fallbacks=[CommandHandler('cancel', support_h.support_ticket_cancel)],
        per_user=True, per_chat=True
    )

    # --------- ADMIN: ADD/EDIT PLAN ----------
    add_plan_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^➕ افزودن پلن جدید$') & admin_filter, admin_plans.add_plan_start),
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
        map_to_parent={ConversationHandler.END: constants.PLAN_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    edit_plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_plans.edit_plan_start, pattern=r'^admin_edit_plan_\d+$')],
        states={
            constants.EDIT_PLAN_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_name_received),
                CommandHandler('skip', admin_plans.skip_edit_plan_name)
            ],
            constants.EDIT_PLAN_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_price_received),
                CommandHandler('skip', admin_plans.skip_edit_plan_price)
            ],
            constants.EDIT_PLAN_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_days_received),
                CommandHandler('skip', admin_plans.skip_edit_plan_days)
            ],
            constants.EDIT_PLAN_GB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_gb_received),
                CommandHandler('skip', admin_plans.skip_edit_plan_gb)
            ],
            constants.EDIT_PLAN_CATEGORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_category_received),
                CommandHandler('skip', admin_plans.skip_edit_plan_category)
            ],
        },
        fallbacks=[CommandHandler('cancel', admin_plans.cancel_edit_plan)],
        map_to_parent={ConversationHandler.END: constants.PLAN_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    # --------- ADMIN: TRIAL SETTINGS (nested conv) ----------
    trial_settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(trial_ui.trial_menu, pattern=r"^settings_trial$")],
        states={
            trial_ui.TRIAL_MENU: [
                CallbackQueryHandler(trial_ui.ask_days, pattern=r"^trial_set_days$"),
                CallbackQueryHandler(trial_ui.ask_gb, pattern=r"^trial_set_gb$"),
                CallbackQueryHandler(admin_settings.settings_menu, pattern=r"^back_to_settings$"),
            ],
            trial_ui.WAIT_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trial_ui.days_received),
                CommandHandler('cancel', trial_ui.cancel),
            ],
            trial_ui.WAIT_GB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, trial_ui.gb_received),
                CommandHandler('cancel', trial_ui.cancel),
            ],
        },
        fallbacks=[CallbackQueryHandler(admin_settings.settings_menu, pattern=r"^back_to_settings$")],
        map_to_parent={constants.ADMIN_SETTINGS_MENU: constants.ADMIN_SETTINGS_MENU, ConversationHandler.END: constants.ADMIN_SETTINGS_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    # --------- ADMIN: BROADCAST (Inline) ----------
    broadcast_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^📩 ارسال پیام$') & admin_filter, admin_users.broadcast_menu),
        ],
        states={
            constants.BROADCAST_MENU: [
                CallbackQueryHandler(admin_users.broadcast_to_all_start, pattern=r'^bcast_all$'),
                CallbackQueryHandler(admin_users.broadcast_to_user_start, pattern=r'^bcast_user$'),
                CallbackQueryHandler(admin_users.broadcast_menu_cb, pattern=r'^bcast_menu$'),
                CallbackQueryHandler(admin_c.admin_entry, pattern=r'^admin_panel$'),
            ],
            constants.BROADCAST_MESSAGE: [
                MessageHandler(~filters.COMMAND & admin_filter, admin_users.broadcast_to_all_confirm),
                CallbackQueryHandler(admin_users.broadcast_cancel_cb, pattern=r'^bcast_menu$'),
                CallbackQueryHandler(admin_c.admin_entry, pattern=r'^admin_panel$'),
            ],
            constants.BROADCAST_CONFIRM: [
                CallbackQueryHandler(admin_users.broadcast_confirm_callback, pattern=r'^broadcast_confirm_(yes|no)$'),
                CallbackQueryHandler(admin_users.broadcast_cancel_cb, pattern=r'^bcast_menu$'),
            ],
            constants.BROADCAST_TO_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_users.broadcast_to_user_id_received),
                CallbackQueryHandler(admin_users.broadcast_cancel_cb, pattern=r'^bcast_menu$'),
                CallbackQueryHandler(admin_c.admin_entry, pattern=r'^admin_panel$'),
            ],
            constants.BROADCAST_TO_USER_MESSAGE: [
                MessageHandler(~filters.COMMAND & admin_filter, admin_users.broadcast_to_user_message_received),
                CallbackQueryHandler(admin_users.broadcast_cancel_cb, pattern=r'^bcast_menu$'),
                CallbackQueryHandler(admin_c.admin_entry, pattern=r"^admin_panel$"),
            ],
        },
        fallbacks=[CommandHandler('cancel', admin_c.admin_generic_cancel)],
        map_to_parent={ConversationHandler.END: constants.ADMIN_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    # --------- ADMIN ROOT CONVERSATION ----------
    admin_states = {}

    # ADMIN MENU
    admin_states[constants.ADMIN_MENU] = [
        MessageHandler(filters.Regex(r'^➕ مدیریت پلن‌ها$') & admin_filter, admin_plans.plan_management_menu),
        MessageHandler(filters.Regex(r'^📈 گزارش‌ها و آمار$') & admin_filter, admin_reports.reports_menu),
        MessageHandler(filters.Regex(r'^💾 پشتیبان‌گیری$') & admin_filter, admin_backup.backup_restore_menu),
        MessageHandler(filters.Regex(r'^👥 مدیریت کاربران$') & admin_filter, admin_users.user_management_menu),
        MessageHandler(filters.Regex(r'^🎁 مدیریت کد هدیه$') & admin_filter, admin_gift.gift_code_management_menu),
        MessageHandler(filters.Regex(r'^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),
        MessageHandler(filters.Regex(r'^🛑 خاموش کردن ربات$') & admin_filter, admin_c.shutdown_bot),
        CallbackQueryHandler(admin_plans.plan_management_menu, pattern=r"^admin_plans$"),
        CallbackQueryHandler(admin_reports.reports_menu, pattern=r"^admin_reports$"),
        CallbackQueryHandler(admin_backup.backup_restore_menu, pattern=r"^admin_backup$"),
        CallbackQueryHandler(admin_users.user_management_menu, pattern=r"^admin_users$"),
        CallbackQueryHandler(admin_gift.gift_code_management_menu, pattern=r"^admin_gift$"),
        CallbackQueryHandler(admin_settings.settings_menu, pattern=r"^admin_settings$"),
        CallbackQueryHandler(admin_c.shutdown_bot, pattern=r"^admin_shutdown$"),
        broadcast_conv,
    ]

    # PLANS MENU
    admin_states[constants.PLAN_MENU] = [
        MessageHandler(filters.Regex(r'^➕ مدیریت پلن‌ها$') & admin_filter, admin_plans.plan_management_menu),
        MessageHandler(filters.Regex(r'^📈 گزارش‌ها و آمار$') & admin_filter, admin_reports.reports_menu),
        MessageHandler(filters.Regex(r'^💾 پشتیبان‌گیری$') & admin_filter, admin_backup.backup_restore_menu),
        MessageHandler(filters.Regex(r'^👥 مدیریت کاربران$') & admin_filter, admin_users.user_management_menu),
        MessageHandler(filters.Regex(r'^🎁 مدیریت کد هدیه$') & admin_filter, admin_gift.gift_code_management_menu),
        MessageHandler(filters.Regex(r'^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),
        CallbackQueryHandler(admin_plans.plan_management_menu, pattern=r"^admin_plans$"),
        CallbackQueryHandler(admin_reports.reports_menu, pattern=r"^admin_reports$"),
        CallbackQueryHandler(admin_backup.backup_restore_menu, pattern=r"^admin_backup$"),
        CallbackQueryHandler(admin_users.user_management_menu, pattern=r"^admin_users$"),
        CallbackQueryHandler(admin_gift.gift_code_management_menu, pattern=r"^admin_gift$"),
        CallbackQueryHandler(admin_settings.settings_menu, pattern=r"^admin_settings$"),
        CallbackQueryHandler(admin_plans.list_plans_admin, pattern=r'^admin_list_plans$'),
        CallbackQueryHandler(admin_plans.admin_toggle_plan_visibility_callback, pattern=r'^admin_toggle_plan_\d+$'),
        CallbackQueryHandler(admin_plans.admin_delete_plan_callback, pattern=r'^admin_delete_plan_\d+$'),
        add_plan_conv,
        edit_plan_conv,
        CallbackQueryHandler(admin_plans.back_to_admin_cb, pattern=r"^admin_panel$"),
    ]

    # USER MANAGEMENT
    admin_states[constants.USER_MANAGEMENT_MENU] = [
        MessageHandler(filters.Regex(r'^➕ مدیریت پلن‌ها$') & admin_filter, admin_plans.plan_management_menu),
        MessageHandler(filters.Regex(r'^📈 گزارش‌ها و آمار$') & admin_filter, admin_reports.reports_menu),
        MessageHandler(filters.Regex(r'^💾 پشتیبان‌گیری$') & admin_filter, admin_backup.backup_restore_menu),
        MessageHandler(filters.Regex(r'^👥 مدیریت کاربران$') & admin_filter, admin_users.user_management_menu),
        MessageHandler(filters.Regex(r'^🎁 مدیریت کد هدیه$') & admin_filter, admin_gift.gift_code_management_menu),
        MessageHandler(filters.Regex(r'^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),

        # Users list (paged)
        CallbackQueryHandler(admin_users.list_users_start, pattern=r"^admin_users_list$"),
        CallbackQueryHandler(admin_users.list_users_page_cb, pattern=r"^admin_users_list_page_\d+$"),
        CallbackQueryHandler(admin_users.open_user_from_list_cb, pattern=r"^admin_user_open_\d+$"),

        CallbackQueryHandler(admin_c.admin_entry, pattern=r"^admin_panel$"),
        CallbackQueryHandler(admin_users.ask_user_id_cb, pattern=r"^admin_users_ask_id$"),
        CallbackQueryHandler(admin_users.user_management_menu_cb, pattern=r"^admin_users$"),
        CallbackQueryHandler(admin_users.admin_user_addbal_cb, pattern=r'^admin_user_addbal_\d+$'),
        CallbackQueryHandler(admin_users.admin_user_subbal_cb, pattern=r'^admin_user_subbal_\d+$'),
        CallbackQueryHandler(admin_users.admin_user_services_cb, pattern=r'^admin_user_services_\d+$'),
        CallbackQueryHandler(admin_users.admin_user_purchases_cb, pattern=r'^admin_user_purchases_\d+$'),
        CallbackQueryHandler(admin_users.admin_user_trial_reset_cb, pattern=r'^admin_user_trial_reset_\d+$'),
        CallbackQueryHandler(admin_users.admin_user_toggle_ban_cb, pattern=r'^admin_user_toggle_ban_\d+$'),
        CallbackQueryHandler(admin_users.admin_user_refresh_cb, pattern=r'^admin_user_refresh_\d+$'),
        CallbackQueryHandler(admin_users.admin_delete_service, pattern=r'^admin_delete_service_\d+(_\d+)?$'),
        CallbackQueryHandler(admin_users.admin_user_amount_cancel_cb, pattern=r'^admin_user_amount_cancel_\d+$'),
        MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_users.manage_user_id_received),
    ]

    # MANAGE USER AMOUNT
    admin_states[constants.MANAGE_USER_AMOUNT] = [
        MessageHandler(filters.Regex(r'^➕ مدیریت پلن‌ها$') & admin_filter, admin_plans.plan_management_menu),
        MessageHandler(filters.Regex(r'^📈 گزارش‌ها و آمار$') & admin_filter, admin_reports.reports_menu),
        MessageHandler(filters.Regex(r'^💾 پشتیبان‌گیری$') & admin_filter, admin_backup.backup_restore_menu),
        MessageHandler(filters.Regex(r'^👥 مدیریت کاربران$') & admin_filter, admin_users.user_management_menu),
        MessageHandler(filters.Regex(r'^🎁 مدیریت کد هدیه$') & admin_filter, admin_gift.gift_code_management_menu),
        MessageHandler(filters.Regex(r'^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),
        MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_users.manage_user_amount_received),
        CallbackQueryHandler(admin_users.admin_user_amount_cancel_cb, pattern=r'^admin_user_amount_cancel_\d+$'),
        CallbackQueryHandler(admin_c.admin_entry, pattern=r"^admin_panel$"),
    ]

    # REPORTS MENU
    admin_states[constants.REPORTS_MENU] = [
        MessageHandler(filters.Regex(r'^➕ مدیریت پلن‌ها$') & admin_filter, admin_plans.plan_management_menu),
        MessageHandler(filters.Regex(r'^📈 گزارش‌ها و آمار$') & admin_filter, admin_reports.reports_menu),
        MessageHandler(filters.Regex(r'^💾 پشتیبان‌گیری$') & admin_filter, admin_backup.backup_restore_menu),
        MessageHandler(filters.Regex(r'^👥 مدیریت کاربران$') & admin_filter, admin_users.user_management_menu),
        MessageHandler(filters.Regex(r'^🎁 مدیریت کد هدیه$') & admin_filter, admin_gift.gift_code_management_menu),
        MessageHandler(filters.Regex(r'^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),
        CallbackQueryHandler(admin_reports.reports_menu, pattern=r"^rep_menu$"),
        CallbackQueryHandler(admin_reports.show_stats_report, pattern=r"^rep_stats$"),
        CallbackQueryHandler(admin_reports.show_daily_report, pattern=r"^rep_daily$"),
        CallbackQueryHandler(admin_reports.show_weekly_report, pattern=r"^rep_weekly$"),
        CallbackQueryHandler(admin_reports.show_popular_plans_report, pattern=r"^rep_popular$"),
        CallbackQueryHandler(admin_c.admin_entry, pattern=r"^admin_panel$"),
    ]

    # SETTINGS MENU
    admin_states[constants.ADMIN_SETTINGS_MENU] = [
        MessageHandler(filters.Regex(r'^➕ مدیریت پلن‌ها$') & admin_filter, admin_plans.plan_management_menu),
        MessageHandler(filters.Regex(r'^📈 گزارش‌ها و آمار$') & admin_filter, admin_reports.reports_menu),
        MessageHandler(filters.Regex(r'^💾 پشتیبان‌گیری$') & admin_filter, admin_backup.backup_restore_menu),
        MessageHandler(filters.Regex(r'^👥 مدیریت کاربران$') & admin_filter, admin_users.user_management_menu),
        MessageHandler(filters.Regex(r'^🎁 مدیریت کد هدیه$') & admin_filter, admin_gift.gift_code_management_menu),
        MessageHandler(filters.Regex(r'^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),
        CallbackQueryHandler(admin_settings.settings_menu, pattern=r"^admin_settings$"),
        CallbackQueryHandler(admin_settings.settings_menu, pattern=r"^back_to_settings$"),
        CallbackQueryHandler(admin_settings.maintenance_and_join_submenu, pattern=r"^settings_maint_join$"),
        CallbackQueryHandler(admin_settings.payment_and_guides_submenu, pattern=r"^settings_payment_guides$"),
        CallbackQueryHandler(admin_settings.payment_info_submenu, pattern=r"^payment_info_submenu$"),
        CallbackQueryHandler(admin_settings.first_charge_promo_submenu, pattern=r"^first_charge_promo_submenu$"),
        CallbackQueryHandler(admin_settings.service_configs_submenu, pattern=r"^settings_service_configs$"),
        CallbackQueryHandler(admin_settings.subdomains_submenu, pattern=r"^settings_subdomains$"),
        CallbackQueryHandler(admin_settings.reports_and_reminders_submenu, pattern=r"^settings_reports_reminders$"),
        CallbackQueryHandler(admin_settings.usage_aggregation_submenu, pattern=r"^settings_usage_aggregation$"),
        CallbackQueryHandler(admin_settings.toggle_usage_aggregation, pattern=r"^toggle_usage_aggregation$"),
        CallbackQueryHandler(admin_settings.edit_default_link_start, pattern=r"^edit_default_link_type$"),
        CallbackQueryHandler(admin_settings.set_default_link_type, pattern=r"^set_default_link_"),
        CallbackQueryHandler(admin_settings.toggle_maintenance, pattern=r"^toggle_maintenance$"),
        CallbackQueryHandler(admin_settings.toggle_force_join, pattern=r"^toggle_force_join$"),
        CallbackQueryHandler(admin_settings.toggle_expiry_reminder, pattern=r"^toggle_expiry_reminder$"),
        CallbackQueryHandler(admin_settings.toggle_report_setting, pattern=r"^toggle_report_"),
        trial_settings_conv,
        CallbackQueryHandler(admin_settings.edit_setting_start, pattern=r"^admin_edit_setting_"),
        CallbackQueryHandler(admin_settings.back_to_admin_menu_cb, pattern=r"^admin_back_to_menu$"),
        CallbackQueryHandler(admin_c.admin_entry, pattern=r"^admin_panel$"),
    ]

    # AWAIT SETTING VALUE
    admin_states[constants.AWAIT_SETTING_VALUE] = [
        MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, await_setting_value_router),
    ]

    # GIFT CODES MENU
    admin_states[constants.GIFT_CODES_MENU] = [
        MessageHandler(filters.Regex(r'^➕ مدیریت پلن‌ها$') & admin_filter, admin_plans.plan_management_menu),
        MessageHandler(filters.Regex(r'^📈 گزارش‌ها و آمار$') & admin_filter, admin_reports.reports_menu),
        MessageHandler(filters.Regex(r'^💾 پشتیبان‌گیری$') & admin_filter, admin_backup.backup_restore_menu),
        MessageHandler(filters.Regex(r'^👥 مدیریت کاربران$') & admin_filter, admin_users.user_management_menu),
        MessageHandler(filters.Regex(r'^🎁 مدیریت کد هدیه$') & admin_filter, admin_gift.gift_code_management_menu),
        MessageHandler(filters.Regex(r'^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),

        CallbackQueryHandler(admin_gift.gift_code_management_menu, pattern=r'^gift_root_menu$'),
        CallbackQueryHandler(admin_gift.gift_code_management_menu, pattern=r'^admin_gift$'),
        CallbackQueryHandler(admin_gift.admin_gift_codes_submenu, pattern=r'^gift_menu_gift$'),
        CallbackQueryHandler(admin_gift.admin_promo_codes_submenu, pattern=r'^gift_menu_promo$'),

        # NEW: referral bonus settings
        CallbackQueryHandler(admin_gift.ask_referral_bonus, pattern=r'^gift_referral_bonus$'),
        CallbackQueryHandler(admin_gift.referral_cancel_cb, pattern=r'^gift_referral_cancel$'),

        CallbackQueryHandler(admin_gift.create_gift_code_start, pattern=r'^gift_new_gift$'),
        CallbackQueryHandler(admin_gift.cancel_create_gift_cb, pattern=r'^gift_create_cancel$'),
        CallbackQueryHandler(admin_gift.list_gift_codes, pattern=r'^gift_list_gift$'),
        CallbackQueryHandler(admin_gift.delete_gift_code_callback, pattern=r'^delete_gift_code_'),

        CallbackQueryHandler(admin_gift.create_promo_start, pattern=r'^promo_new$'),
        CallbackQueryHandler(admin_gift.promo_cancel_cb, pattern=r'^promo_cancel$'),
        CallbackQueryHandler(admin_gift.promo_skip_expires_cb, pattern=r'^promo_skip_expires$'),
        CallbackQueryHandler(admin_gift.list_promo_codes, pattern=r'^promo_list$'),
        CallbackQueryHandler(admin_gift.delete_promo_code_callback, pattern=r'^delete_promo_code_'),
        CallbackQueryHandler(admin_gift.promo_first_purchase_choice, pattern=r'^promo_first_(yes|no)$'),

        CallbackQueryHandler(admin_settings.global_discount_submenu, pattern=r'^global_discount_submenu$'),
        CallbackQueryHandler(admin_settings.toggle_global_discount, pattern=r'^toggle_global_discount$'),
        CallbackQueryHandler(admin_settings.edit_setting_start, pattern=r'^admin_edit_setting_'),
        CallbackQueryHandler(admin_c.admin_entry, pattern=r"^admin_panel$"),
    ]

    # NEW: AWAIT_REFERRAL_BONUS state
    admin_states[constants.AWAIT_REFERRAL_BONUS] = [
        MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_gift.referral_bonus_received),
        CallbackQueryHandler(admin_gift.referral_cancel_cb, pattern=r'^gift_referral_cancel$'),
        CallbackQueryHandler(admin_gift.gift_code_management_menu, pattern=r'^gift_root_menu$'),
        CallbackQueryHandler(admin_c.admin_entry, pattern=r"^admin_panel$"),
    ]

    admin_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f'^{constants.BTN_ADMIN_PANEL}$') & admin_filter, admin_c.admin_entry),
            CallbackQueryHandler(admin_c.admin_entry, pattern=r"^admin_panel$")
        ],
        states=admin_states,
        fallbacks=[
            MessageHandler(filters.Regex(f'^{constants.BTN_EXIT_ADMIN_PANEL}$') & admin_filter, admin_c.exit_admin_panel),
            CommandHandler('cancel', admin_c.admin_generic_cancel)
        ],
        per_user=True, per_chat=True, allow_reentry=True
    )

    # --------- REGISTER HANDLERS ----------
    application.add_handler(buy_conv, group=0)
    application.add_handler(gift_conv, group=0)
    application.add_handler(charge_conv, group=0)
    application.add_handler(transfer_conv, group=0)
    application.add_handler(gift_from_balance_conv, group=0)
    application.add_handler(support_conv, group=0)
    application.add_handler(admin_conv, group=0)

    # Admin settings commands
    application.add_handler(CommandHandler("set_trial_days", set_trial_days, filters=admin_filter))
    application.add_handler(CommandHandler("set_trial_gb", set_trial_gb, filters=admin_filter))

    # Buy confirm/cancel
    application.add_handler(CallbackQueryHandler(buy_h.confirm_purchase_callback, pattern=r"^confirmbuy$"), group=2)
    application.add_handler(CallbackQueryHandler(buy_h.cancel_purchase_callback, pattern=r"^cancelbuy$"), group=2)

    # Support replies (admin side)
    application.add_handler(MessageHandler(filters.REPLY & admin_filter, support_h.admin_reply_handler), group=1)
    application.add_handler(CallbackQueryHandler(support_h.close_ticket, pattern=r"^close_ticket_"), group=1)

    # Home/menu checks
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.start), pattern=r"^check_membership$"))
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.start), pattern=r"^home_menu$"))

    # Usage
    application.add_handler(CallbackQueryHandler(usage_h.show_usage_menu, pattern=r"^acc_usage$"), group=2)
    application.add_handler(CallbackQueryHandler(usage_h.show_usage_menu, pattern=r"^acc_usage_refresh$"), group=2)

    # Admin charge decision
    application.add_handler(CallbackQueryHandler(admin_users.admin_confirm_charge_callback, pattern=r'^admin_confirm_charge_'), group=1)
    application.add_handler(CallbackQueryHandler(admin_users.admin_reject_charge_callback, pattern=r'^admin_reject_charge_'), group=1)

    # USER SERVICES (user side)
    user_services_handlers = [
        CallbackQueryHandler(check_channel_membership(us_h.view_service_callback), pattern=r"^view_service_"),
        CallbackQueryHandler(check_channel_membership(us_h.back_to_services_callback), pattern=r"^back_to_services$"),
        CallbackQueryHandler(check_channel_membership(us_h.get_link_callback), pattern=r"^getlink_"),
        CallbackQueryHandler(check_channel_membership(us_h.refresh_service_details), pattern=r"^refresh_"),
        CallbackQueryHandler(check_channel_membership(us_h.more_links_callback), pattern=r"^more_links_"),
        CallbackQueryHandler(check_channel_membership(us_h.renew_service_handler), pattern=r"^renew_"),
        CallbackQueryHandler(check_channel_membership(us_h.confirm_renewal_callback), pattern=r"^confirmrenew$"),
        CallbackQueryHandler(check_channel_membership(us_h.cancel_renewal_callback), pattern=r"^cancelrenew$"),
        CallbackQueryHandler(check_channel_membership(us_h.delete_service_callback), pattern=r"^delete_service_"),
    ]
    for h in user_services_handlers:
        application.add_handler(h, group=2)

    # ACCOUNT INFO
    account_info_handlers = [
        CallbackQueryHandler(check_channel_membership(start_h.show_purchase_history_callback), pattern=r"^acc_purchase_history$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_charge_history_callback), pattern=r"^acc_charge_history$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_charging_guide_callback), pattern=r"^acc_charging_guide$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_account_info), pattern=r"^acc_back_to_main$"),
    ]
    for h in account_info_handlers:
        application.add_handler(h, group=2)

    # GUIDES
    guide_handlers = [
        CallbackQueryHandler(check_channel_membership(start_h.show_guide_content), pattern=r"^guide_(connection|charging|buying)$"),
        CallbackQueryHandler(check_channel_membership(start_h.back_to_guide_menu), pattern=r"^guide_back_to_menu$"),
    ]
    for h in guide_handlers:
        application.add_handler(h)

    # PLANS (User browsing)
    plan_category_handlers = [
        CallbackQueryHandler(check_channel_membership(buy_h.show_plans_in_category), pattern=r"^user_cat_"),
        CallbackQueryHandler(check_channel_membership(buy_h.buy_service_list), pattern=r"^back_to_cats$"),
    ]
    for h in plan_category_handlers:
        application.add_handler(h)

    # BUY PANEL SELECT (Multi-panel)
    application.add_handler(CallbackQueryHandler(check_channel_membership(buy_panels.choose_panel_callback), pattern=r"^buy_select_panel_"))

    # MAIN MENU (user)
    main_menu_handlers = [
        CommandHandler("start", check_channel_membership(start_h.start)),
        # Route purchase to panel selection menu first
        MessageHandler(filters.Regex(r'^🛍️ خرید سرویس$'), check_channel_membership(buy_panels.show_panel_menu)),
        MessageHandler(filters.Regex(r'^📋 سرویس‌های من$'), check_channel_membership(us_h.list_my_services)),
        MessageHandler(filters.Regex(r'^👤 اطلاعات حساب کاربری$'), check_channel_membership(start_h.show_account_info)),
        MessageHandler(filters.Regex(r'^📚 راهنما$'), check_channel_membership(start_h.show_guide)),
        MessageHandler(filters.Regex(r'^🧪 سرویس تست$'), check_channel_membership(trial_get_trial_service)),
    ]
    for h in main_menu_handlers:
        application.add_handler(h, group=1)

    return application