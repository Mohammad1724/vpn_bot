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
    usage as usage_h  # نمایش مصرف تجمیعی
)
from bot.handlers.common_handlers import check_channel_membership
from bot.handlers.admin import (
    common as admin_c, plans as admin_plans, reports as admin_reports,
    settings as admin_settings, backup as admin_backup, users as admin_users,
    gift_codes as admin_gift
)
# اگر مدیریت نودها را فعال دارید، این ایمپورت را نگه دارید
from bot.handlers.admin import nodes as admin_nodes

import bot.handlers.admin.trial_settings_ui as trial_ui
from bot.handlers.trial import get_trial_service as trial_get_trial_service
from bot.handlers.admin.trial_settings import set_trial_days, set_trial_gb
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

    # Admin filter
    try:
        admin_id_int = int(ADMIN_ID)
    except Exception:
        admin_id_int = ADMIN_ID
    admin_filter = filters.User(user_id=admin_id_int)
    user_filter = ~admin_filter

    # =========================
    # User Conversations
    # =========================
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(check_channel_membership(buy_h.buy_start), pattern='^user_buy_')],
        states={
            constants.GET_CUSTOM_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_h.get_custom_name),
                CommandHandler('skip', buy_h.skip_custom_name),
            ],
            constants.PROMO_CODE_ENTRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, buy_h.promo_code_received),
                CommandHandler('skip', buy_h.promo_code_received),
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
        entry_points=[
            CallbackQueryHandler(check_channel_membership(charge_h.charge_start), pattern='^user_start_charge$'),
            MessageHandler(filters.Regex(r'^💳 شارژ حساب$') & user_filter, check_channel_membership(charge_h.charge_start)),
        ],
        states={
            constants.CHARGE_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, charge_h.charge_amount_received),
                CallbackQueryHandler(charge_h.charge_amount_confirm_cb, pattern="^charge_amount_(confirm|cancel)$"),
            ],
            constants.CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_h.charge_receipt_received)],
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
        states={constants.SUPPORT_TICKET_OPEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_h.forward_to_admin)]},
        fallbacks=[CommandHandler('cancel', support_h.support_ticket_cancel)],
        per_user=True, per_chat=True
    )

    # =========================
    # Admin Nested Conversations
    # =========================
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
            constants.EDIT_PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_name_received), CommandHandler('skip', admin_plans.skip_edit_plan_name)],
            constants.EDIT_PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_price_received), CommandHandler('skip', admin_plans.skip_edit_plan_price)],
            constants.EDIT_PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_days_received), CommandHandler('skip', admin_plans.skip_edit_plan_days)],
            constants.EDIT_PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_gb_received), CommandHandler('skip', admin_plans.skip_edit_plan_gb)],
            constants.EDIT_PLAN_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plans.edit_plan_category_received), CommandHandler('skip', admin_plans.skip_edit_plan_category)],
        },
        fallbacks=[CommandHandler('cancel', admin_plans.cancel_edit_plan)],
        map_to_parent={ConversationHandler.END: constants.PLAN_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    trial_settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(trial_ui.trial_menu, pattern="^settings_trial$")],
        states={
            trial_ui.TRIAL_MENU: [
                CallbackQueryHandler(trial_ui.ask_days, pattern="^trial_set_days$"),
                CallbackQueryHandler(trial_ui.ask_gb, pattern="^trial_set_gb$"),
                CallbackQueryHandler(admin_settings.settings_menu, pattern="^back_to_settings$"),
            ],
            trial_ui.WAIT_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, trial_ui.days_received), CommandHandler('cancel', trial_ui.cancel)],
            trial_ui.WAIT_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, trial_ui.gb_received), CommandHandler('cancel', trial_ui.cancel)],
        },
        fallbacks=[CallbackQueryHandler(admin_settings.settings_menu, pattern="^back_to_settings$")],
        map_to_parent={constants.ADMIN_SETTINGS_MENU: constants.ADMIN_SETTINGS_MENU, ConversationHandler.END: constants.ADMIN_SETTINGS_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    gift_code_create_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^➕ ساخت کد هدیه جدید$') & admin_filter, admin_gift.create_gift_code_start),
            CallbackQueryHandler(admin_gift.create_gift_code_start, pattern=r'^admin_gift_create$'),
        ],
        states={admin_gift.CREATE_GIFT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift.create_gift_amount_received)]},
        fallbacks=[CommandHandler('cancel', admin_gift.cancel_create_gift)],
        map_to_parent={ConversationHandler.END: constants.GIFT_CODES_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    promo_create_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^➕ ساخت کد تخفیف جدید$') & admin_filter, admin_gift.create_promo_start)],
        states={
            constants.PROMO_GET_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift.promo_code_received)],
            constants.PROMO_GET_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift.promo_percent_received)],
            constants.PROMO_GET_MAX_USES: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift.promo_max_uses_received)],
            constants.PROMO_GET_EXPIRES: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift.promo_days_valid_received), CommandHandler('skip', admin_gift.promo_skip_expires)],
            constants.PROMO_GET_FIRST_PURCHASE: [MessageHandler(filters.Regex(r'^(بله|خیر)$'), admin_gift.promo_first_purchase_received)],
        },
        fallbacks=[CommandHandler('cancel', admin_gift.cancel_promo_create)],
        map_to_parent={ConversationHandler.END: constants.GIFT_CODES_MENU},
    )

    referral_bonus_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^💰 تنظیم هدیه دعوت$') & admin_filter, admin_gift.ask_referral_bonus)],
        states={
            constants.AWAIT_REFERRAL_BONUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift.referral_bonus_received)]
        },
        fallbacks=[CommandHandler('cancel', admin_gift.cancel_referral_bonus)],
        map_to_parent={ConversationHandler.END: constants.GIFT_CODES_MENU},
    )

    broadcast_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r'^📩 ارسال پیام$') & admin_filter, admin_users.broadcast_menu)],
        states={
            constants.BROADCAST_MENU: [
                MessageHandler(filters.Regex(r'^ارسال به همه کاربران$') & admin_filter, admin_users.broadcast_to_all_start),
                MessageHandler(filters.Regex(r'^ارسال به کاربر خاص$') & admin_filter, admin_users.broadcast_to_user_start),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
            ],
            constants.BROADCAST_MESSAGE: [
                MessageHandler(~filters.COMMAND & admin_filter, admin_users.broadcast_to_all_confirm),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
            ],
            constants.BROADCAST_CONFIRM: [CallbackQueryHandler(admin_users.broadcast_confirm_callback, pattern=r'^broadcast_confirm_(yes|no)$')],
            constants.BROADCAST_TO_USER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_users.broadcast_to_user_id_received),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
            ],
            constants.BROADCAST_TO_USER_MESSAGE: [
                MessageHandler(~filters.COMMAND & admin_filter, admin_users.broadcast_to_user_message_received),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
            ],
        },
        fallbacks=[CommandHandler('cancel', admin_c.admin_generic_cancel)],
        map_to_parent={ConversationHandler.END: constants.ADMIN_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    admin_settings_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^⚙️ تنظیمات$') & admin_filter, admin_settings.settings_menu),
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
                CallbackQueryHandler(admin_settings.multi_server_usage_submenu, pattern="^settings_multi_server_usage$"),
                CallbackQueryHandler(admin_settings.toggle_usage_aggregation, pattern="^toggle_usage_aggregation$"),

                CallbackQueryHandler(admin_settings.edit_default_link_start, pattern="^edit_default_link_type$"),
                CallbackQueryHandler(admin_settings.set_default_link_type, pattern="^set_default_link_"),
                CallbackQueryHandler(admin_settings.toggle_maintenance, pattern="^toggle_maintenance$"),
                CallbackQueryHandler(admin_settings.toggle_force_join, pattern="^toggle_force_join$"),
                CallbackQueryHandler(admin_settings.toggle_expiry_reminder, pattern="^toggle_expiry_reminder$"),
                CallbackQueryHandler(admin_settings.toggle_report_setting, pattern="^toggle_report_"),
                trial_settings_conv,
                CallbackQueryHandler(admin_settings.edit_setting_start, pattern="^admin_edit_setting_"),
                CallbackQueryHandler(admin_settings.back_to_admin_menu_cb, pattern="^admin_back_to_menu$"),
            ],
            constants.AWAIT_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_settings.setting_value_received)],
        },
        fallbacks=[
            CommandHandler('cancel', admin_c.admin_generic_cancel),
            CallbackQueryHandler(admin_settings.settings_menu, pattern="^back_to_settings$")
        ],
        map_to_parent={constants.ADMIN_MENU: constants.ADMIN_MENU, ConversationHandler.END: constants.ADMIN_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    # =========================
    # Nodes Conversation (Admin) - در صورت نیاز
    # =========================
    nodes_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^🖥️ مدیریت نودها$') & admin_filter, admin_nodes.nodes_menu),
            CallbackQueryHandler(admin_nodes.nodes_menu, pattern=r'^admin_nodes$'),
        ],
        states={
            admin_nodes.NODES_MENU: [
                CallbackQueryHandler(admin_nodes.add_node_start, pattern=r'^admin_add_node$'),
                CallbackQueryHandler(admin_nodes.list_nodes, pattern=r'^admin_list_nodes$'),
                CallbackQueryHandler(admin_c.admin_entry, pattern=r'^admin_back_to_menu$'),
            ],
            admin_nodes.ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.add_get_name)],
            admin_nodes.ADD_PANEL_DOMAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.add_get_panel_domain)],
            admin_nodes.ADD_ADMIN_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.add_get_admin_path)],
            admin_nodes.ADD_SUB_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.add_get_sub_path)],
            admin_nodes.ADD_API_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.add_get_api_key)],
            admin_nodes.ADD_SUB_DOMAINS: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.add_get_sub_domains)],
            admin_nodes.ADD_CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.add_get_capacity)],
            admin_nodes.ADD_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.add_get_location)],
            admin_nodes.ADD_CONFIRM: [
                CallbackQueryHandler(admin_nodes.add_confirm, pattern=r'^node_add_confirm$'),
                CallbackQueryHandler(admin_nodes.add_cancel, pattern=r'^node_add_cancel$'),
            ],
            admin_nodes.NODE_DETAILS: [
                CallbackQueryHandler(admin_nodes.node_details, pattern=r'^admin_node_\d+$'),
                CallbackQueryHandler(admin_nodes.toggle_node_active, pattern=r'^admin_toggle_node_\d+$'),
                CallbackQueryHandler(admin_nodes.edit_node_start, pattern=r'^admin_edit_node_\d+$'),
                CallbackQueryHandler(admin_nodes.delete_node_confirm, pattern=r'^admin_delete_node_\d+$'),
                CallbackQueryHandler(admin_nodes.ping_node, pattern=r'^admin_node_ping_\d+$'),
                CallbackQueryHandler(admin_nodes.update_node_usercount, pattern=r'^admin_node_update_count_\d+$'),
                CallbackQueryHandler(admin_nodes.show_node_usage, pattern=r'^admin_node_usage_\d+$'),
                CallbackQueryHandler(admin_nodes.list_nodes, pattern=r'^admin_list_nodes$'),
                CallbackQueryHandler(admin_nodes.nodes_menu, pattern=r'^admin_nodes$'),
            ],
            admin_nodes.EDIT_FIELD_PICK: [
                CallbackQueryHandler(admin_nodes.edit_field_pick, pattern=r'^admin_edit_field_')
            ],
            admin_nodes.EDIT_FIELD_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_nodes.edit_field_value_received),
            ],
            admin_nodes.DELETE_CONFIRM: [
                CallbackQueryHandler(admin_nodes.delete_node_execute, pattern=r'^admin_delete_node_yes_\d+$'),
            ],
        },
        fallbacks=[CommandHandler('cancel', admin_nodes.cancel)],
        map_to_parent={ConversationHandler.END: constants.ADMIN_MENU},
        per_user=True, per_chat=True, allow_reentry=True
    )

    # =========================
    # Main Admin Conversation
    # =========================
    admin_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f'^{constants.BTN_ADMIN_PANEL}$') & admin_filter, admin_c.admin_entry),
            CallbackQueryHandler(admin_c.admin_entry, pattern="^admin_panel$")
        ],
        states={
            constants.ADMIN_MENU: [
                MessageHandler(filters.Regex('^➕ مدیریت پلن‌ها$') & admin_filter, admin_plans.plan_management_menu),
                MessageHandler(filters.Regex('^📈 گزارش‌ها و آمار$') & admin_filter, admin_reports.reports_menu),
                MessageHandler(filters.Regex('^💾 پشتیبان‌گیری$') & admin_filter, admin_backup.backup_restore_menu),
                MessageHandler(filters.Regex('^👥 مدیریت کاربران$') & admin_filter, admin_users.user_management_menu),
                MessageHandler(filters.Regex('^🎁 مدیریت کد هدیه$') & admin_filter, admin_gift.gift_code_management_menu),
                MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$') & admin_filter, admin_c.shutdown_bot),

                # Nested conversations and callbacks
                CallbackQueryHandler(admin_plans.plan_management_menu, pattern="^admin_plans$"),
                CallbackQueryHandler(admin_reports.reports_menu, pattern="^admin_reports$"),
                CallbackQueryHandler(admin_backup.backup_restore_menu, pattern="^admin_backup$"),
                CallbackQueryHandler(admin_users.user_management_menu, pattern="^admin_users$"),
                CallbackQueryHandler(admin_gift.gift_code_management_menu, pattern="^admin_gift$"),
                CallbackQueryHandler(admin_c.shutdown_bot, pattern="^admin_shutdown$"),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),

                nodes_conv,
                admin_settings_conv,
                broadcast_conv,
            ],

            constants.PLAN_MENU: [
                MessageHandler(filters.Regex(r'^📋 لیست پلن‌ها$') & admin_filter, admin_plans.list_plans_admin),
                CallbackQueryHandler(admin_plans.list_plans_admin, pattern=r'^admin_list_plans$'),
                CallbackQueryHandler(admin_plans.admin_toggle_plan_visibility_callback, pattern=r'^admin_toggle_plan_\d+$'),
                CallbackQueryHandler(admin_plans.admin_delete_plan_callback, pattern=r'^admin_delete_plan_\d+$'),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
                add_plan_conv,
                edit_plan_conv,
            ],

            constants.REPORTS_MENU: [
                MessageHandler(filters.Regex(r'^📊 آمار کلی$') & admin_filter, admin_reports.show_stats_report),
                MessageHandler(filters.Regex(r'^📈 گزارش فروش امروز$') & admin_filter, admin_reports.show_daily_report),
                MessageHandler(filters.Regex(r'^📅 گزارش فروش ۷ روز اخیر$') & admin_filter, admin_reports.show_weekly_report),
                MessageHandler(filters.Regex(r'^🏆 محبوب‌ترین پلن‌ها$') & admin_filter, admin_reports.show_popular_plans_report),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
            ],

            constants.BACKUP_MENU: [
                MessageHandler(filters.Regex(r'^📥 دریافت فایل پشتیبان$') & admin_filter, admin_backup.send_backup_file),
                MessageHandler(filters.Regex(r'^📤 بارگذاری فایل پشتیبان$') & admin_filter, admin_backup.restore_start),
                MessageHandler(filters.Regex(r'^⚙️ تنظیمات پشتیبان‌گیری خودکار$') & admin_filter, admin_backup.edit_auto_backup_start),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
                CallbackQueryHandler(admin_backup.backup_restore_menu, pattern=r'^back_to_backup_menu$'),
                CallbackQueryHandler(admin_backup.edit_auto_backup_start, pattern=r'^edit_auto_backup$'),
                CallbackQueryHandler(admin_backup.edit_backup_interval_start, pattern=r'^edit_backup_interval$'),
                CallbackQueryHandler(admin_backup.set_backup_interval, pattern=r'^set_backup_interval_\d+$'),
                CallbackQueryHandler(admin_backup.edit_backup_target_start, pattern=r'^edit_backup_target$'),
                CallbackQueryHandler(admin_backup.admin_confirm_restore_callback, pattern=r'^admin_confirm_restore$'),
                CallbackQueryHandler(admin_backup.admin_cancel_restore_callback, pattern=r'^admin_cancel_restore$'),
            ],

            constants.RESTORE_UPLOAD: [
                MessageHandler(filters.Document.ALL & admin_filter, admin_backup.restore_receive_file),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
            ],

            constants.USER_MANAGEMENT_MENU: [
                MessageHandler(filters.Regex(r'^\d+$') & admin_filter, admin_users.manage_user_id_received),
                CallbackQueryHandler(admin_users.admin_user_addbal_cb, pattern=r'^admin_user_addbal_\d+$'),
                CallbackQueryHandler(admin_users.admin_user_subbal_cb, pattern=r'^admin_user_subbal_\d+$'),
                CallbackQueryHandler(admin_users.admin_user_services_cb, pattern=r'^admin_user_services_\d+$'),
                CallbackQueryHandler(admin_users.admin_user_purchases_cb, pattern=r'^admin_user_purchases_\d+$'),
                CallbackQueryHandler(admin_users.admin_user_trial_reset_cb, pattern=r'^admin_user_trial_reset_\d+$'),
                CallbackQueryHandler(admin_users.admin_user_toggle_ban_cb, pattern=r'^admin_user_toggle_ban_\d+$'),
                CallbackQueryHandler(admin_users.admin_user_refresh_cb, pattern=r'^admin_user_refresh_\d+$'),
                CallbackQueryHandler(admin_users.admin_delete_service, pattern=r'^admin_delete_service_\d+(_\d+)?$'),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
            ],

            constants.MANAGE_USER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_users.manage_user_amount_received),
                CallbackQueryHandler(admin_users.admin_user_amount_cancel_cb, pattern=r'^admin_user_amount_cancel_\d+$'),
            ],

            constants.GIFT_CODES_MENU: [
                MessageHandler(filters.Regex(r'^🎁 مدیریت کدهای هدیه$'), admin_gift.admin_gift_codes_submenu),
                MessageHandler(filters.Regex(r'^💳 مدیریت کدهای تخفیف$'), admin_gift.admin_promo_codes_submenu),
                MessageHandler(filters.Regex(r'^📋 لیست کدهای هدیه$'), admin_gift.list_gift_codes),
                CallbackQueryHandler(admin_gift.delete_gift_code_callback, pattern=r'^delete_gift_code_'),
                MessageHandler(filters.Regex(r'^📋 لیست کدهای تخفیف$'), admin_gift.list_promo_codes),
                CallbackQueryHandler(admin_gift.delete_promo_code_callback, pattern=r'^delete_promo_code_'),
                MessageHandler(filters.Regex(f'^{constants.BTN_BACK_TO_ADMIN_MENU}$') & admin_filter, admin_c.admin_entry),
                gift_code_create_conv,
                promo_create_conv,
                referral_bonus_conv,
            ],

            constants.AWAIT_SETTING_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin_backup.backup_target_received),
                CommandHandler('cancel', admin_backup.cancel_backup_settings),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{constants.BTN_EXIT_ADMIN_PANEL}$') & admin_filter, admin_c.exit_admin_panel),
            CommandHandler('cancel', admin_c.admin_generic_cancel)
        ],
        per_user=True, per_chat=True, allow_reentry=True
    )

    # =========================
    # Register Conversations
    # =========================
    application.add_handler(buy_conv)
    application.add_handler(gift_conv)
    application.add_handler(charge_conv)
    application.add_handler(transfer_conv)
    application.add_handler(gift_from_balance_conv)
    application.add_handler(support_conv)
    application.add_handler(admin_conv)

    # Admin-only trial command handlers
    application.add_handler(CommandHandler("set_trial_days", set_trial_days, filters=admin_filter))
    application.add_handler(CommandHandler("set_trial_gb", set_trial_gb, filters=admin_filter))

    # =========================
    # Global Callbacks & Handlers
    # =========================
    application.add_handler(CallbackQueryHandler(buy_h.confirm_purchase_callback, pattern="^confirmbuy$"), group=2)
    application.add_handler(CallbackQueryHandler(buy_h.cancel_purchase_callback, pattern="^cancelbuy$"), group=2)
    application.add_handler(MessageHandler(filters.REPLY & admin_filter, support_h.admin_reply_handler))
    application.add_handler(CallbackQueryHandler(support_h.close_ticket, pattern="^close_ticket_"))
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.start), pattern="^check_membership$"))
    # «☰ منوی اصلی» اینلاین
    application.add_handler(CallbackQueryHandler(check_channel_membership(start_h.start), pattern="^home_menu$"))

    # Usage aggregate menu (in Account info)
    application.add_handler(CallbackQueryHandler(usage_h.show_usage_menu, pattern="^acc_usage$"))
    application.add_handler(CallbackQueryHandler(usage_h.show_usage_menu, pattern="^acc_usage_refresh$"))

    application.add_handler(CallbackQueryHandler(admin_users.admin_confirm_charge_callback, pattern=r'^admin_confirm_charge_'), group=1)
    application.add_handler(CallbackQueryHandler(admin_users.admin_reject_charge_callback, pattern=r'^admin_reject_charge_'), group=1)

    # =========================
    # Other (user) handlers
    # =========================
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
    for h in user_services_handlers:
        application.add_handler(h, group=2)

    account_info_handlers = [
        CallbackQueryHandler(check_channel_membership(start_h.show_purchase_history_callback), pattern="^acc_purchase_history$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_charge_history_callback), pattern="^acc_charge_history$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_charging_guide_callback), pattern="^acc_charging_guide$"),
        CallbackQueryHandler(check_channel_membership(start_h.show_account_info), pattern="^acc_back_to_main$"),
    ]
    for h in account_info_handlers:
        application.add_handler(h)

    guide_handlers = [
        CallbackQueryHandler(check_channel_membership(start_h.show_guide_content), pattern="^guide_(connection|charging|buying)$"),
        CallbackQueryHandler(check_channel_membership(start_h.back_to_guide_menu), pattern="^guide_back_to_menu$"),
    ]
    for h in guide_handlers:
        application.add_handler(h)

    plan_category_handlers = [
        CallbackQueryHandler(check_channel_membership(buy_h.show_plans_in_category), pattern="^user_cat_"),
        CallbackQueryHandler(check_channel_membership(buy_h.buy_service_list), pattern="^back_to_cats$"),
    ]
    for h in plan_category_handlers:
        application.add_handler(h)

    main_menu_handlers = [
        CommandHandler("start", check_channel_membership(start_h.start)),
        MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), check_channel_membership(buy_h.buy_service_list)),
        MessageHandler(filters.Regex('^📋 سرویس‌های من$'), check_channel_membership(us_h.list_my_services)),
        MessageHandler(filters.Regex('^👤 اطلاعات حساب کاربری$'), check_channel_membership(start_h.show_account_info)),
        MessageHandler(filters.Regex('^📚 راهنما$'), check_channel_membership(start_h.show_guide)),
        MessageHandler(filters.Regex('^🧪 دریافت سرویس تست رایگان$'), check_channel_membership(trial_get_trial_service)),
        MessageHandler(filters.Regex('^🎁 معرفی دوستان$'), check_channel_membership(start_h.show_referral_link)),
    ]
    for h in main_menu_handlers:
        application.add_handler(h)

    return application