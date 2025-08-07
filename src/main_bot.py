# -*- coding: utf-8 -*-

import logging
import os
import shutil
import asyncio
import random
import sqlite3
import io
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    ApplicationBuilder
)
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest
import database as db
import hiddify_api
from config import (
    BOT_TOKEN, ADMIN_ID, SUPPORT_USERNAME, SUB_DOMAINS, ADMIN_PATH,
    PANEL_DOMAIN, SUB_PATH, TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB
)
import qrcode

# --- Setup ---
os.makedirs('backups', exist_ok=True)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Constants & States ---
USAGE_ALERT_THRESHOLD = 0.8
BTN_ADMIN_PANEL = "👑 ورود به پنل ادمین"
BTN_EXIT_ADMIN_PANEL = "↩️ خروج از پنل"
BTN_BACK_TO_ADMIN_MENU = "بازگشت به منوی ادمین"
CMD_CANCEL = "/cancel"
CMD_SKIP = "/skip"
(
    ADMIN_MENU, PLAN_MENU, REPORTS_MENU, USER_MANAGEMENT_MENU, PLAN_NAME,
    PLAN_PRICE, PLAN_DAYS, PLAN_GB, EDIT_PLAN_NAME, EDIT_PLAN_PRICE,
    EDIT_PLAN_DAYS, EDIT_PLAN_GB, MANAGE_USER_ID, MANAGE_USER_ACTION,
    MANAGE_USER_AMOUNT, GET_CUSTOM_NAME, REDEEM_GIFT, CHARGE_AMOUNT,
    CHARGE_RECEIPT, SETTINGS_MENU, BACKUP_MENU, BROADCAST_MENU, BROADCAST_MESSAGE,
    BROADCAST_CONFIRM, BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE, RESTORE_UPLOAD,
    AWAIT_SETTING_VALUE
) = range(28)


# --- Keyboards ---
def get_main_menu_keyboard(user_id):
    user_info = db.get_or_create_user(user_id)
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["💰 موجودی و شارژ", "🎁 کد هدیه"]
    ]
    if TRIAL_ENABLED and user_info and not user_info.get('has_used_trial'):
        keyboard.append(["🧪 دریافت سرویس تست رایگان"])
    keyboard.append(["📞 پشتیبانی", "📚 راهنمای اتصال"])
    if user_id == ADMIN_ID:
        keyboard.append([BTN_ADMIN_PANEL])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu_keyboard():
    keyboard = [
        ["➕ مدیریت پلن‌ها", "📈 گزارش‌ها و آمار"],
        ["⚙️ تنظیمات", "🎁 مدیریت کد هدیه"],
        ["📩 ارسال پیام", "💾 پشتیبان‌گیری"],
        ["👥 مدیریت کاربران"],
        ["🛑 خاموش کردن ربات", BTN_EXIT_ADMIN_PANEL]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Helper Functions ---
async def _get_service_status(hiddify_info):
    start_date_str = hiddify_info.get('start_date')
    package_days = hiddify_info.get('package_days', 0)
    if not start_date_str: return "🟢 فعال (جدید)", "N/A", False
    try:
        start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        expiry_date_obj = start_date_obj + timedelta(days=package_days)
        is_expired = expiry_date_obj < datetime.now().date()
        return ("🔴 منقضی شده", expiry_date_obj.strftime("%Y-%m-%d"), True) if is_expired else ("🟢 فعال", expiry_date_obj.strftime("%Y-%m-%d"), False)
    except (ValueError, TypeError):
        logger.error(f"Could not parse start_date: {start_date_str}")
        return "⚠️ وضعیت نامشخص", "N/A", True

def is_valid_sqlite(filepath):
    try:
        with sqlite3.connect(filepath) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
        return result[0] == 'ok'
    except sqlite3.DatabaseError:
        return False

# --- Background Job ---
async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running job: Checking for low usage services...")
    all_services = db.get_all_active_services()
    for service in all_services:
        if service['low_usage_alert_sent']:
            continue
        try:
            info = await hiddify_api.get_user_info(service['sub_uuid'])
            if not info:
                logger.warning(f"Could not get info for service {service['service_id']} during usage check.")
                continue

            status, expiry_date, is_expired = await _get_service_status(info)
            if is_expired:
                continue

            usage_limit = info.get('usage_limit_GB', 0)
            current_usage = info.get('current_usage_GB', 0)

            if usage_limit > 0 and (current_usage / usage_limit) >= USAGE_ALERT_THRESHOLD:
                user_id = service['user_id']
                service_name = f"'{service['name']}'" if service['name'] else ""
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"📢 هشدار اتمام حجم!\n\n"
                        f"کاربر گرامی، بیش از {int(USAGE_ALERT_THRESHOLD * 100)}٪ از حجم سرویس شما {service_name} مصرف شده است.\n"
                        f"({current_usage:.2f} گیگ از {usage_limit:.0f} گیگ)\n\n"
                        "برای جلوگیری از قطعی، پیشنهاد می‌کنیم سرویس خود را تمدید نمایید."
                    )
                )
                db.set_low_usage_alert_sent(service['service_id'])
                logger.info(f"Sent low usage alert to user {user_id} for service {service['service_id']}.")
                await asyncio.sleep(0.2)
        except (Forbidden, BadRequest) as e:
            logger.warning(f"Failed to send low usage alert to user {service['user_id']}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error in low usage job for service {service['service_id']}: {e}", exc_info=True)

# --- Generic Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_info = db.get_or_create_user(user.id, user.username)
    if user_info and user_info.get('is_banned'):
        await update.message.reply_text("شما از استفاده از این ربات منع شده‌اید.")
        return ConversationHandler.END
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ConversationHandler.END

async def user_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END

# --- User Service Management ---
async def list_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    services = db.get_user_services(user_id)
    if not services:
        await update.message.reply_text("شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return
    msg = await update.message.reply_text("در حال دریافت اطلاعات سرویس‌های شما... ⏳")
    for service in services:
        await send_service_details(context, user_id, service['service_id'])
        await asyncio.sleep(0.2)
    try: await msg.delete()
    except BadRequest: pass

async def send_service_details(context: ContextTypes.DEFAULT_TYPE, chat_id: int, service_id: int, original_message=None):
    service = db.get_service(service_id)
    if not service:
        error_text = "❌ سرویس مورد نظر یافت نشد."
        if original_message: await original_message.edit_text(error_text)
        else: await context.bot.send_message(chat_id=chat_id, text=error_text)
        return
    try:
        info = await hiddify_api.get_user_info(service['sub_uuid'])
        if info:
            status, expiry_date_display, is_expired = await _get_service_status(info)
            renewal_plan = db.get_plan(service['plan_id'])
            service_name_display = f"🏷️ نام سرویس: **{service['name']}**\n\n" if service['name'] else ""
            message_text = (f"{service_name_display}🔗 لینک پروفایل: `{service['sub_link']}`\n🗓️ تاریخ انقضا: **{expiry_date_display}**\n"
                       f"📊 حجم مصرفی: **{info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f}** گیگ\n🚦 وضعیت: {status}")
            keyboard = [[InlineKeyboardButton("📋 دریافت لینک‌های اشتراک", callback_data=f"showlinks_{service['sub_uuid']}")],
                        [InlineKeyboardButton("🔄 به‌روزرسانی اطلاعات", callback_data=f"refresh_{service['service_id']}")]
                       ]
            if renewal_plan and service.get('plan_id', 0) > 0:
                keyboard.append([InlineKeyboardButton(f"⏳ تمدید سرویس ({renewal_plan['price']:.0f} تومان)", callback_data=f"renew_{service['service_id']}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            if original_message: await original_message.edit_text(message_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            else: await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else: raise ConnectionError(f"API did not return info for UUID {service['sub_uuid']}")
    except Exception as e:
        logger.error(f"Error in send_service_details for service_id {service_id}: {e}", exc_info=True)
        error_text = "❌ خطا در دریافت اطلاعات سرویس. لطفاً بعدا دوباره تلاش کنید."
        if original_message:
            try: await original_message.edit_text(error_text)
            except BadRequest: pass
        else: await context.bot.send_message(chat_id=chat_id, text=error_text)

async def refresh_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = int(query.data.split('_')[1])
    service = db.get_service(service_id)
    if service and service['user_id'] == query.from_user.id:
        await query.edit_message_text("در حال به‌روزرسانی اطلاعات...", reply_markup=None)
        await send_service_details(context, query.from_user.id, service_id, original_message=query.message)
    else: await query.answer("خطا: این سرویس متعلق به شما نیست.", show_alert=True)

# --- Renewal Logic ---
async def renew_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    service = db.get_service(service_id)
    if not service: await query.edit_message_text("❌ سرویس نامعتبر است."); return
    plan = db.get_plan(service['plan_id'])
    if not plan: await query.edit_message_text("❌ پلن تمدید برای این سرویس یافت نشد."); return
    user = db.get_or_create_user(user_id)
    if user['balance'] < plan['price']: await query.edit_message_text(f"موجودی برای تمدید کافی نیست! (نیاز به {plan['price']:.0f} تومان)"); return
    await query.edit_message_text("در حال بررسی وضعیت سرویس... ⏳")
    hiddify_info = await hiddify_api.get_user_info(service['sub_uuid'])
    if not hiddify_info: await query.edit_message_text("❌ امکان دریافت اطلاعات سرویس از پنل وجود ندارد. لطفاً بعداً تلاش کنید."); return
    _, _, is_expired = await _get_service_status(hiddify_info)
    context.user_data['renewal_service_id'] = service_id
    context.user_data['renewal_plan_id'] = plan['plan_id']
    if is_expired: await proceed_with_renewal(query, context)
    else:
        keyboard = [[InlineKeyboardButton("✅ بله، تمدید کن", callback_data=f"confirmrenew")], [InlineKeyboardButton("❌ خیر، لغو کن", callback_data=f"cancelrenew")]]
        await query.edit_message_text("⚠️ **هشدار مهم** ⚠️\n\nسرویس شما هنوز اعتبار دارد. تمدید در حال حاضر باعث می‌شود اعتبار زمانی و حجمی باقیمانده شما **از بین برود** و دوره جدید از همین امروز شروع شود.\n\nآیا می‌خواهید ادامه دهید?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def confirm_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await proceed_with_renewal(query, context)

async def proceed_with_renewal(query: Update.callback_query, context: ContextTypes.DEFAULT_TYPE):
    service_id = context.user_data.get('renewal_service_id')
    plan_id = context.user_data.get('renewal_plan_id')
    
    if not all([service_id, plan_id]):
        await query.edit_message_text("❌ خطای داخلی: اطلاعات تمدید یافت نشد. لطفا دوباره تلاش کنید.")
        return

    await query.edit_message_text("در حال ارسال درخواست تمدید به پنل... ⏳")
    
    transaction_id = db.initiate_renewal_transaction(query.from_user.id, service_id, plan_id)
    if not transaction_id:
        await query.edit_message_text("❌ مشکلی در شروع فرآیند تمدید پیش آمد (مثلا عدم موجودی).")
        return

    service = db.get_service(service_id)
    plan = db.get_plan(plan_id)

    logger.info(f"Attempting to renew service {service_id} for user {query.from_user.id} with UUID {service['sub_uuid']}")
    logger.info(f"Renewal details: Plan ID {plan_id}, Days: {plan['days']}, GB: {plan['gb']}")

    new_hiddify_info = await hiddify_api.renew_user_subscription(service['sub_uuid'], plan['days'], plan['gb'])

    logger.info(f"Hiddify renewal API returned: {new_hiddify_info}")

    if new_hiddify_info:
        db.finalize_renewal_transaction(transaction_id, plan_id) 
        await query.edit_message_text("✅ سرویس با موفقیت تمدید شد! در حال دریافت اطلاعات جدید...")
        await send_service_details(context, query.from_user.id, service_id, original_message=query.message)
    else:
        db.cancel_renewal_transaction(transaction_id)
        await query.edit_message_text("❌ خطا در تمدید سرویس. مشکلی در ارتباط با پنل وجود دارد. لطفاً به پشتیبانی اطلاع دهید.")
        
    context.user_data.clear()

async def cancel_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = context.user_data.get('renewal_service_id')
    context.user_data.clear()
    await query.edit_message_text("عملیات تمدید لغو شد. در حال بازگشت به منوی سرویس...")
    if service_id: await send_service_details(context, query.from_user.id, service_id, original_message=query.message)
    else: await query.edit_message_text("سرویس مورد نظر یافت نشد.")

# --- Main User Flow Handlers ---
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="user_start_charge")]]
    await update.message.reply_text(f"💰 موجودی فعلی شما: **{user['balance']:.0f}** تومان", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"جهت ارتباط با پشتیبانی به آیدی زیر پیام ارسال کنید:\n@{SUPPORT_USERNAME}")

async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("راهنمای اتصال به سرویس‌ها:\n\n(اینجا می‌توانید آموزش‌های لازم را قرار دهید)")

async def get_trial_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = db.get_or_create_user(user_id, update.effective_user.username)
    if not TRIAL_ENABLED: await update.message.reply_text("در حال حاضر سرویس تست فعال نمی‌باشد."); return
    if user_info.get('has_used_trial'): await update.message.reply_text("شما قبلاً از سرویس تست رایگان استفاده کرده‌اید."); return
    msg_loading = await update.message.reply_text("در حال ساخت سرویس تست شما... ⏳")
    result = await hiddify_api.create_hiddify_user(TRIAL_DAYS, TRIAL_GB, user_id, custom_name="سرویس تست")
    if result and result.get('uuid'):
        db.set_user_trial_used(user_id)
        db.add_active_service(user_id, "سرویس تست", result['uuid'], result['full_link'], 0)
        await show_link_options_menu(update.message, result['uuid'], is_edit=False)
    else: await msg_loading.edit_text("❌ متاسفانه در ساخت سرویس تست مشکلی پیش آمد. لطفا بعداً تلاش کنید.")

# --- Gift Code Conversation ---
async def gift_code_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 لطفا کد هدیه خود را وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return REDEEM_GIFT

async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.upper()
    user_id = update.effective_user.id
    amount = db.use_gift_code(code, user_id)
    if amount is not None: await update.message.reply_text(f"✅ تبریک! مبلغ {amount:.0f} تومان به کیف پول شما اضافه شد.", reply_markup=get_main_menu_keyboard(user_id))
    else: await update.message.reply_text("❌ کد هدیه نامعتبر یا استفاده شده است.", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# --- Charge Account Conversation ---
async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً مبلغی که قصد واریز آن را دارید به تومان وارد کنید (فقط عدد):", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return CHARGE_AMOUNT

async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount < 1000: raise ValueError
        context.user_data['charge_amount'] = amount
        card_number = db.get_setting('card_number') or "[تنظیم نشده]"
        card_holder = db.get_setting('card_holder') or "[تنظیم نشده]"
        await update.message.reply_text(f"لطفاً مبلغ **{amount:,} تومان** را به شماره کارت زیر واریز نمایید:\n\n`{card_number}`\nبه نام: {card_holder}\n\nسپس از رسید واریزی خود عکس گرفته و آن را ارسال کنید.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
        return CHARGE_RECEIPT
    except (ValueError, TypeError):
        await update.message.reply_text("لطفا یک عدد صحیح و بیشتر از 1000 تومان وارد کنید.")
        return CHARGE_AMOUNT

async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = context.user_data.get('charge_amount')
    if not amount:
        await update.message.reply_text("خطا! مبلغ شارژ مشخص نیست. لطفا از ابتدا شروع کنید.", reply_markup=get_main_menu_keyboard(user.id))
        return ConversationHandler.END
    receipt_photo = update.message.photo[-1]
    caption = (f"درخواست شارژ جدید 🔔\n\n" f"کاربر: {user.full_name} (@{user.username or 'N/A'})\n" f"آیدی عددی: `{user.id}`\n" f"مبلغ درخواستی: **{amount:,} تومان**")
    keyboard = [[InlineKeyboardButton("✅ تایید شارژ", callback_data=f"admin_confirm_charge_{user.id}_{int(amount)}"), InlineKeyboardButton("❌ رد درخواست", callback_data=f"admin_reject_charge_{user.id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=receipt_photo.file_id, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_text("✅ رسید شما برای ادمین ارسال شد. لطفاً تا زمان بررسی منتظر بمانید.", reply_markup=get_main_menu_keyboard(user.id))
    context.user_data.clear()
    return ConversationHandler.END

# --- Buy Service Conversation ---
async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans(only_visible=True)
    if not plans: await update.message.reply_text("متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست."); return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان", callback_data=f"user_buy_{p['plan_id']}")] for p in plans]
    await update.message.reply_text("لطفا سرویس مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    transaction_id = db.initiate_purchase_transaction(query.from_user.id, plan_id)
    if not transaction_id:
        user = db.get_or_create_user(query.from_user.id)
        plan = db.get_plan(plan_id)
        await query.edit_message_text(f"موجودی شما کافی نیست!\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان")
        return ConversationHandler.END
    context.user_data['transaction_id'] = transaction_id
    context.user_data['plan_to_buy_id'] = plan_id
    await query.edit_message_text(f"✅ پلن شما انتخاب شد.\n\nلطفاً یک نام دلخواه برای این سرویس وارد کنید (مثلاً: گوشی شخصی).\nبرای استفاده از نام پیش‌فرض، دستور {CMD_SKIP} را ارسال کنید.", reply_markup=None)
    return GET_CUSTOM_NAME

async def get_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_name = update.message.text
    if len(custom_name) > 50: await update.message.reply_text("نام وارد شده بیش از حد طولانی است."); return GET_CUSTOM_NAME
    context.user_data['custom_name'] = custom_name
    await create_service_after_name(update.message, context)
    return ConversationHandler.END

async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['custom_name'] = ""
    await create_service_after_name(update.message, context)
    return ConversationHandler.END

async def create_service_after_name(message: Update.message, context: ContextTypes.DEFAULT_TYPE):
    user_id = message.chat_id
    plan_id = context.user_data.get('plan_to_buy_id')
    transaction_id = context.user_data.get('transaction_id')
    custom_name_input = context.user_data.get('custom_name', "")
    if not all([plan_id, transaction_id]):
        await message.reply_text("خطای داخلی رخ داده است. لطفا مجددا تلاش کنید.", reply_markup=get_main_menu_keyboard(user_id))
        context.user_data.clear()
        return
        
    plan = db.get_plan(plan_id)
    custom_name = custom_name_input if custom_name_input else f"سرویس {plan['gb']} گیگ"
    
    msg_loading = await message.reply_text("در حال ساخت سرویس شما... ⏳", reply_markup=get_main_menu_keyboard(user_id))
    
    result = await hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id, custom_name=custom_name)

    if result and result.get('uuid'):
        db.finalize_purchase_transaction(transaction_id, result['uuid'], result['full_link'], custom_name)
        
        try:
            await msg_loading.delete()
        except BadRequest as e:
            logger.warning(f"Could not delete 'loading' message: {e}")
            
        await show_link_options_menu(message, result['uuid'], is_edit=False) 
        
    else:
        db.cancel_purchase_transaction(transaction_id)
        await msg_loading.edit_text("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. لطفا به پشتیبانی اطلاع دهید.")
        
    context.user_data.clear()
    return ConversationHandler.END

# --- Link & QR Code ---
async def show_link_options_menu(message: Update.message, user_uuid: str, is_edit: bool = True):
    keyboard = [[InlineKeyboardButton("🔗 لینک هوشمند (Auto)", callback_data=f"getlink_auto_{user_uuid}")],
                [InlineKeyboardButton("📱 لینک SingBox", callback_data=f"getlink_singbox_{user_uuid}")],
                [InlineKeyboardButton("💻 لینک استاندارد (V2ray)", callback_data=f"getlink_sub_{user_uuid}")]]
    text = "سرویس شما با موفقیت ساخته شد. لطفاً نوع لینک اشتراک مورد نظر خود را انتخاب کنید:"
    try:
        if is_edit: await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else: await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except BadRequest as e:
        if "message is not modified" not in str(e): logger.error(f"Error in show_link_options_menu: {e}")

async def get_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, link_type, user_uuid = query.data.split('_')
    await query.message.edit_text("در حال ساخت لینک و QR Code... ⏳")
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    base_link = f"https://{sub_domain}/{sub_path}/{user_uuid}"
    user_info = await hiddify_api.get_user_info(user_uuid)
    config_name = user_info.get('name', 'config') if user_info else 'config'
    final_link = f"{base_link}/" if link_type == "auto" else f"{base_link}/{link_type}/"
    final_link_with_fragment = f"{final_link}?name={config_name.replace(' ', '_')}"
    qr_image = qrcode.make(final_link_with_fragment)
    bio = io.BytesIO(); bio.name = 'qrcode.png'; qr_image.save(bio, 'PNG'); bio.seek(0)
    caption = (f"نام کانفیگ: **{config_name}**\n\n"
               "می‌توانید با اسکن QR کد زیر یا با استفاده از لینک اشتراک، به سرویس متصل شوید.\n\n"
               f"لینک اشتراک شما:\n`{final_link_with_fragment}`")
    await query.message.delete()

    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=bio,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_keyboard(query.from_user.id)
    )

# ====================================================================
# ADMIN SECTION
# ====================================================================

async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👑 به پنل ادمین خوش آمدید.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("شما از پنل ادمین خارج شدید.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END

async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("به منوی اصلی ادمین بازگشتید.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def admin_delete_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    db.delete_plan(plan_id)
    await query.message.delete()
    await query.from_user.send_message("پلن با موفقیت حذف شد.")
    return PLAN_MENU

async def admin_toggle_plan_visibility_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    db.toggle_plan_visibility(plan_id)
    await query.answer("وضعیت نمایش پلن تغییر کرد.")
    await query.message.delete()
    await query.from_user.send_message("وضعیت نمایش پلن تغییر کرد. برای دیدن تغییرات، لیست را مجددا باز کنید.")
    return PLAN_MENU

async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    prefix = "admin_confirm_charge_"
    try:
        data_part = query.data[len(prefix):]
        user_id_str, amount_str = data_part.split('_', 1)
        target_user_id = int(user_id_str)
        amount = int(float(amount_str))
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing admin_confirm_charge_callback data: {query.data} | Error: {e}")
        try:
            if query.message.photo:
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n---\n❌ خطا در پردازش اطلاعات دکمه.")
            else:
                await query.edit_message_text("❌ خطا در پردازش اطلاعات دکمه.")
        except Exception as edit_error:
            logger.error(f"Fallback error message failed to send: {edit_error}")
        return

    db.update_balance(target_user_id, amount)
    original_caption = query.message.caption or ""
    admin_feedback = f"{original_caption}\n\n---\n✅ با موفقیت مبلغ {amount:,} تومان به حساب کاربر `{target_user_id}` اضافه شد."
    
    try:
        await context.bot.send_message(
            chat_id=target_user_id, 
            text=f"حساب شما با موفقیت به مبلغ **{amount:,} تومان** شارژ شد!", 
            parse_mode=ParseMode.MARKDOWN
        )
    except (Forbidden, BadRequest):
        admin_feedback += "\n\n⚠️ **اخطار:** کاربر ربات را بلاک کرده و پیام تایید را دریافت نکرد."
    
    try:
        await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"edit_message_caption failed: {e}. Sending new message as fallback.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_feedback, parse_mode=ParseMode.MARKDOWN)

async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        target_user_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing admin_reject_charge_callback data: {query.data} | Error: {e}")
        try:
            if query.message.photo:
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n---\n❌ خطا در پردازش اطلاعات دکمه.")
            else:
                await query.edit_message_text("❌ خطا در پردازش اطلاعات دکمه.")
        except Exception as edit_error:
            logger.error(f"Fallback error message failed to send: {edit_error}")
        return

    original_caption = query.message.caption or ""
    admin_feedback = f"{original_caption}\n\n---\n❌ درخواست شارژ کاربر `{target_user_id}` رد شد."
    
    try: 
        await context.bot.send_message(chat_id=target_user_id, text="متاسفانه درخواست شارژ حساب شما توسط ادمین رد شد.")
    except (Forbidden, BadRequest): 
        admin_feedback += "\n\n⚠️ **اخطار:** کاربر ربات را بلاک کرده است."
    
    try:
        await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"edit_message_caption failed: {e}. Sending new message as fallback.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_feedback, parse_mode=ParseMode.MARKDOWN)

async def admin_confirm_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    restore_path = context.user_data.get('restore_path')
    if not restore_path or not os.path.exists(restore_path): 
        await query.edit_message_text("خطا: فایل پشتیبان یافت نشد."); 
        return BACKUP_MENU
    try:
        db.close_db()
        shutil.move(restore_path, db.DB_NAME)
        db.init_db()
        await query.edit_message_text("✅ دیتابیس با موفقیت بازیابی شد.\n\n**مهم:** برای اعمال کامل تغییرات، لطفاً ربات را ری‌استارت کنید.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error during DB restore: {e}", exc_info=True)
        await query.edit_message_text(f"خطا در هنگام جایگزینی فایل دیتابیس: {e}")
    context.user_data.clear()
    return BACKUP_MENU

async def admin_cancel_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    restore_path = context.user_data.get('restore_path')
    if restore_path and os.path.exists(restore_path): os.remove(restore_path)
    await query.edit_message_text("عملیات بازیابی لغو شد.")
    context.user_data.clear()
    return BACKUP_MENU

async def plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["➕ افزودن پلن جدید", "📋 لیست پلن‌ها"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("بخش مدیریت پلن‌ها", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return PLAN_MENU

async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans: 
        await update.message.reply_text("هیچ پلنی تعریف نشده است."); 
        return PLAN_MENU
    await update.message.reply_text("لیست پلن‌های تعریف شده:")
    for plan in plans:
        visibility_icon = "👁️" if plan['is_visible'] else "🙈"
        text = (f"**{plan['name']}** (ID: {plan['plan_id']})\n▫️ قیمت: {plan['price']:.0f} تومان\n▫️ مدت: {plan['days']} روز\n▫️ حجم: {plan['gb']} گیگ\n▫️ وضعیت: {'نمایش' if plan['is_visible'] else 'مخفی'}")
        keyboard = [[InlineKeyboardButton("✏️ ویرایش", callback_data=f"admin_edit_plan_{plan['plan_id']}"), InlineKeyboardButton(f"{visibility_icon} تغییر وضعیت", callback_data=f"admin_toggle_plan_{plan['plan_id']}"), InlineKeyboardButton("🗑️ حذف", callback_data=f"admin_delete_plan_{plan['plan_id']}")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return PLAN_MENU

async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا نام پلن را وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)); return PLAN_NAME

async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_name'] = update.message.text
    await update.message.reply_text("نام ثبت شد. قیمت را به تومان وارد کنید:"); return PLAN_PRICE

async def plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_price'] = float(update.message.text)
        await update.message.reply_text("قیمت ثبت شد. تعداد روزهای اعتبار را وارد کنید:"); return PLAN_DAYS
    except ValueError: 
        await update.message.reply_text("لطفا قیمت را به صورت عدد وارد کنید."); 
        return PLAN_PRICE

async def plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_days'] = int(update.message.text)
        await update.message.reply_text("تعداد روز ثبت شد. حجم سرویس به گیگابایت را وارد کنید:"); return PLAN_GB
    except ValueError: 
        await update.message.reply_text("لطفا تعداد روز را به صورت عدد وارد کنید."); 
        return PLAN_DAYS

async def plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_gb'] = int(update.message.text)
        db.add_plan(context.user_data['plan_name'], context.user_data['plan_price'], context.user_data['plan_days'], context.user_data['plan_gb'])
        await update.message.reply_text("✅ پلن جدید اضافه شد!", reply_markup=get_admin_menu_keyboard())
        context.user_data.clear(); return ADMIN_MENU
    except ValueError: 
        await update.message.reply_text("لطفا حجم را به صورت عدد وارد کنید."); 
        return PLAN_GB

async def edit_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    plan_id = int(query.data.split('_')[-1])
    plan = db.get_plan(plan_id)
    if not plan: 
        await query.edit_message_text("خطا: پلن یافت نشد."); 
        return ConversationHandler.END
    context.user_data['edit_plan_id'] = plan_id
    context.user_data['edit_plan_data'] = {}
    await query.message.reply_text(f"در حال ویرایش پلن: **{plan['name']}**\n\nلطفا نام جدید را وارد کنید. برای رد شدن، {CMD_SKIP} را بزنید.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup([[CMD_SKIP],[CMD_CANCEL]], resize_keyboard=True)); return EDIT_PLAN_NAME

async def edit_plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_plan_data']['name'] = update.message.text
    await update.message.reply_text(f"نام جدید ثبت شد. لطفاً قیمت جدید را به تومان وارد کنید (یا {CMD_SKIP})."); return EDIT_PLAN_PRICE

async def skip_edit_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر نام صرف نظر شد. لطفاً قیمت جدید را به تومان وارد کنید (یا {CMD_SKIP})."); return EDIT_PLAN_PRICE

async def edit_plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['price'] = float(update.message.text)
        await update.message.reply_text(f"قیمت جدید ثبت شد. لطفاً تعداد روزهای جدید را وارد کنید (یا {CMD_SKIP})."); return EDIT_PLAN_DAYS
    except ValueError: 
        await update.message.reply_text("لطفا قیمت را به صورت عدد وارد کنید."); 
        return EDIT_PLAN_PRICE

async def skip_edit_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر قیمت صرف نظر شد. لطفاً تعداد روزهای جدید را وارد کنید (یا {CMD_SKIP})."); return EDIT_PLAN_DAYS

async def edit_plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['days'] = int(update.message.text)
        await update.message.reply_text(f"تعداد روز جدید ثبت شد. لطفاً حجم جدید به گیگابایت را وارد کنید (یا {CMD_SKIP})."); return EDIT_PLAN_GB
    except ValueError: 
        await update.message.reply_text("لطفا تعداد روز را به صورت عدد وارد کنید."); 
        return EDIT_PLAN_DAYS

async def skip_edit_plan_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"از تغییر تعداد روز صرف نظر شد. لطفاً حجم جدید به گیگابایت را وارد کنید (یا {CMD_SKIP})."); return EDIT_PLAN_GB

async def edit_plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['gb'] = int(update.message.text)
        await finish_plan_edit(update, context)
        return ConversationHandler.END
    except ValueError: 
        await update.message.reply_text("لطفا حجم را به صورت عدد وارد کنید."); 
        return EDIT_PLAN_GB

async def skip_edit_plan_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("از تغییر حجم صرف نظر شد.")
    await finish_plan_edit(update, context)
    return ConversationHandler.END

async def finish_plan_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_id = context.user_data.get('edit_plan_id')
    new_data = context.user_data.get('edit_plan_data')
    if not new_data: 
        await update.message.reply_text("هیچ تغییری اعمال نشد.", reply_markup=get_admin_menu_keyboard())
    else:
        db.update_plan(plan_id, new_data)
        await update.message.reply_text("✅ پلن با موفقیت به‌روزرسانی شد!", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ADMIN_MENU

async def reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📊 آمار کلی", "📈 گزارش فروش امروز"], ["📅 گزارش فروش ۷ روز اخیر", "🏆 محبوب‌ترین پلن‌ها"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("بخش گزارش‌ها و آمار", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return REPORTS_MENU

async def show_stats_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    text = (f"📊 **آمار کلی ربات**\n\n" f"👥 تعداد کل کاربران: {stats.get('total_users', 0)}\n" f"✅ تعداد سرویس‌های فعال: {stats.get('active_services', 0)}\n"
            f"💰 مجموع فروش کل: {stats.get('total_revenue', 0):,.0f} تومان\n" f"🚫 تعداد کاربران مسدود: {stats.get('banned_users', 0)}")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN); return REPORTS_MENU

async def show_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sales = db.get_sales_report(days=1)
    total_revenue = sum(s['price'] for s in sales)
    await update.message.reply_text(f"📈 **گزارش فروش امروز**\n\nتعداد فروش: {len(sales)}\nمجموع درآمد: {total_revenue:,.0f} تومان", parse_mode=ParseMode.MARKDOWN); return REPORTS_MENU

async def show_weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sales = db.get_sales_report(days=7)
    total_revenue = sum(s['price'] for s in sales)
    await update.message.reply_text(f"📅 **گزارش فروش ۷ روز اخیر**\n\nتعداد فروش: {len(sales)}\nمجموع درآمد: {total_revenue:,.0f} تومان", parse_mode=ParseMode.MARKDOWN); return REPORTS_MENU

async def show_popular_plans_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.get_popular_plans(limit=5)
    if not plans: await update.message.reply_text("هنوز هیچ پلنی فروخته نشده است."); return REPORTS_MENU
    text = "🏆 **محبوب‌ترین پلن‌ها**\n\n" + "\n".join([f"{i}. **{plan['name']}** - {plan['sales_count']} بار فروش" for i, plan in enumerate(plans, 1)])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN); return REPORTS_MENU

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number = db.get_setting('card_number') or "تنظیم نشده"
    card_holder = db.get_setting('card_holder') or "تنظیم نشده"
    text = (f"⚙️ **تنظیمات ربات**\n\n" f"شماره کارت فعلی: `{card_number}`\n" f"صاحب حساب فعلی: `{card_holder}`\n\n" "برای تغییر هر مورد روی دکمه مربوطه کلیک کنید.")
    keyboard = [[InlineKeyboardButton("ویرایش شماره کارت", callback_data="admin_edit_setting_card_number"), InlineKeyboardButton("ویرایش نام صاحب حساب", callback_data="admin_edit_setting_card_holder")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN); return ADMIN_MENU

async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    setting_key = query.data.split('admin_edit_setting_')[-1]
    context.user_data['setting_to_edit'] = setting_key
    prompt_map = {'card_number': "لطفا شماره کارت جدید را وارد کنید:", 'card_holder': "لطفا نام جدید صاحب حساب را وارد کنید:"}
    prompt_text = prompt_map.get(setting_key)
    if not prompt_text: await query.message.edit_text("خطا: تنظیمات ناشناخته."); return ConversationHandler.END
    await query.message.reply_text(prompt_text, reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)); return AWAIT_SETTING_VALUE

async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting_key = context.user_data.get('setting_to_edit')
    if not setting_key: return await admin_conv_cancel(update, context)
    db.set_setting(setting_key, update.message.text)
    await update.message.reply_text("✅ تنظیمات با موفقیت به‌روز شد.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear(); return ConversationHandler.END

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["ارسال به همه کاربران", "ارسال به کاربر خاص"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("بخش ارسال پیام", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return BROADCAST_MENU

async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا پیام خود را برای ارسال به همه کاربران وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)); return BROADCAST_MESSAGE

async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.message
    total_users = db.get_stats()['total_users']
    await update.message.reply_text(f"آیا از ارسال این پیام به {total_users} کاربر مطمئن هستید؟", reply_markup=ReplyKeyboardMarkup([["بله، ارسال کن"], ["خیر، لغو کن"]], resize_keyboard=True)); return BROADCAST_CONFIRM

async def broadcast_to_all_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_to_send = context.user_data.get('broadcast_message')
    if not message_to_send: await update.message.reply_text("خطا: پیامی برای ارسال یافت نشد.", reply_markup=get_admin_menu_keyboard()); return ADMIN_MENU
    user_ids = db.get_all_user_ids()
    sent_count, failed_count = 0, 0
    await update.message.reply_text(f"در حال ارسال پیام به {len(user_ids)} کاربر...", reply_markup=get_admin_menu_keyboard())
    for user_id in user_ids:
        try: 
            await message_to_send.copy(chat_id=user_id)
            sent_count += 1
            await asyncio.sleep(0.1)
        except (Forbidden, BadRequest): 
            failed_count += 1
    await update.message.reply_text(f"✅ پیام همگانی با موفقیت ارسال شد.\n\nتعداد ارسال موفق: {sent_count}\nتعداد ارسال ناموفق: {failed_count}")
    context.user_data.clear(); return ADMIN_MENU

async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا آیدی عددی کاربر هدف را وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)); return BROADCAST_TO_USER_ID

async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        context.user_data['target_user_id'] = target_id
        await update.message.reply_text("آیدی ثبت شد. حالا پیامی که می‌خواهید برای این کاربر ارسال کنید را وارد نمایید:"); return BROADCAST_TO_USER_MESSAGE
    except ValueError: await update.message.reply_text("لطفا یک آیدی عددی معتبر وارد کنید."); return BROADCAST_TO_USER_ID

async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = context.user_data.get('target_user_id')
    if not target_id: await update.message.reply_text("خطا: کاربر هدف مشخص نیست.", reply_markup=get_admin_menu_keyboard()); return ADMIN_MENU
    message_to_send = update.message
    try:
        await message_to_send.copy(chat_id=target_id)
        await update.message.reply_text("✅ پیام با موفقیت به کاربر ارسال شد.", reply_markup=get_admin_menu_keyboard())
    except (Forbidden, BadRequest): await update.message.reply_text("❌ ارسال پیام ناموفق بود. احتمالا کاربر ربات را بلاک کرده یا آیدی اشتباه است.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear(); return ADMIN_MENU

async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا آیدی عددی یا یوزرنیم تلگرام (با یا بدون @) کاربری که می‌خواهید مدیریت کنید را وارد نمایید:", reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)); return MANAGE_USER_ID

async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    user_info = None
    if user_input.isdigit(): 
        user_info = db.get_user(int(user_input))
    elif user_input.isalnum() or (user_input.startswith('@') and user_input[1:].isalnum()): 
        user_info = db.get_user_by_username(user_input)
    else: 
        await update.message.reply_text("ورودی نامعتبر است. لطفاً یک آیدی عددی یا یوزرنیم تلگرام وارد کنید."); 
        return MANAGE_USER_ID
    if not user_info: 
        await update.message.reply_text("کاربری با این مشخصات یافت نشد."); 
        return MANAGE_USER_ID
    context.user_data['target_user_id'] = user_info['user_id']
    ban_text = "آزاد کردن کاربر" if user_info['is_banned'] else "مسدود کردن کاربر"
    keyboard = [["افزایش موجودی", "کاهش موجودی"], ["📜 سوابق خرید", ban_text], [BTN_BACK_TO_ADMIN_MENU]]
    info_text = (f"👤 مدیریت کاربر: `{user_info['user_id']}`\n" f"🔹 یوزرنیم: @{user_info.get('username', 'N/A')}\n"
                 f"💰 موجودی: {user_info['balance']:.0f} تومان\n" f"🚦 وضعیت: {'مسدود' if user_info['is_banned'] else 'فعال'}")
    await update.message.reply_text(info_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN); return MANAGE_USER_ACTION

async def manage_user_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id: 
        await update.message.reply_text("خطا: کاربر هدف مشخص نیست."); 
        return await back_to_admin_menu(update, context)
    if action in ["افزایش موجودی", "کاهش موجودی"]:
        context.user_data['manage_action'] = action
        await update.message.reply_text("لطفا مبلغ مورد نظر را به تومان وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)); return MANAGE_USER_AMOUNT
    elif "مسدود" in action or "آزاد" in action:
        user_info = db.get_user(target_user_id)
        new_ban_status = not user_info['is_banned']
        db.set_user_ban_status(target_user_id, new_ban_status)
        await update.message.reply_text(f"✅ وضعیت کاربر با موفقیت به '{'مسدود' if new_ban_status else 'فعال'}' تغییر کرد.")
        update.message.text = str(target_user_id)
        return await manage_user_id_received(update, context)
    elif action == "📜 سوابق خرید":
        history = db.get_user_sales_history(target_user_id)
        if not history: 
            await update.message.reply_text("این کاربر تاکنون خریدی نداشته است."); 
            return MANAGE_USER_ACTION
        response_message = "📜 **سوابق خرید کاربر:**\n\n"
        for sale in history:
            sale_date = datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S').strftime('%Y/%m/%d - %H:%M')
            response_message += f"🔹 **{sale['plan_name'] or 'پلن حذف شده'}**\n - قیمت: {sale['price']:.0f} تومان\n - تاریخ: {sale_date}\n\n"
        await update.message.reply_text(response_message, parse_mode=ParseMode.MARKDOWN); return MANAGE_USER_ACTION
    else: 
        await update.message.reply_text("دستور نامعتبر است. لطفاً از دکمه‌ها استفاده کنید."); 
        return MANAGE_USER_ACTION

async def manage_user_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        action = context.user_data['manage_action']
        target_user_id = context.user_data['target_user_id']
        is_add = True if action == "افزایش موجودی" else False
        db.update_balance(target_user_id, amount if is_add else -amount)
        await update.message.reply_text(f"✅ مبلغ {amount:.0f} تومان به حساب کاربر {'اضافه' if is_add else 'کسر'} شد.")
        update.message.text = str(target_user_id)
        return await manage_user_id_received(update, context)
    except (ValueError, TypeError): 
        await update.message.reply_text("لطفا مبلغ را به صورت عدد وارد کنید."); 
        return MANAGE_USER_AMOUNT

async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("بخش پشتیبان‌گیری و بازیابی.", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return BACKUP_MENU

async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"backups/backup_{timestamp}.db"
    try:
        db.close_db()
        shutil.copy(db.DB_NAME, backup_filename)
        db.init_db()
        await update.message.reply_text("در حال آماده‌سازی فایل پشتیبان...")
        await context.bot.send_document(chat_id=update.effective_user.id, document=open(backup_filename, 'rb'), caption=f"پشتیبان دیتابیس - {timestamp}")
    except Exception as e: 
        await update.message.reply_text(f"خطا در ارسال فایل: {e}")
        logger.error(f"Backup file sending error: {e}", exc_info=True)
    finally:
        if os.path.exists(backup_filename): 
            os.remove(backup_filename)
    return BACKUP_MENU

async def restore_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⚠️ **اخطار:** بازیابی دیتابیس تمام اطلاعات فعلی را پاک می‌کند.\n" f"برای ادامه، فایل دیتابیس (`.db`) خود را ارسال کنید. برای لغو {CMD_CANCEL} را بزنید.", parse_mode=ParseMode.MARKDOWN); return RESTORE_UPLOAD

async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.endswith('.db'): 
        await update.message.reply_text("فرمت فایل نامعتبر است. لطفاً یک فایل `.db` ارسال کنید."); 
        return RESTORE_UPLOAD
    file = await document.get_file()
    temp_path = os.path.join("backups", f"restore_temp_{datetime.now().timestamp()}.db")
    await file.download_to_drive(temp_path)
    if not is_valid_sqlite(temp_path):
        await update.message.reply_text("❌ فایل ارسالی یک دیتابیس SQLite معتبر نیست.", reply_markup=get_admin_menu_keyboard())
        if os.path.exists(temp_path): os.remove(temp_path); 
        return ADMIN_MENU
    context.user_data['restore_path'] = temp_path
    keyboard = [[InlineKeyboardButton("✅ بله، مطمئنم", callback_data="admin_confirm_restore"), InlineKeyboardButton("❌ خیر، لغو کن", callback_data="admin_cancel_restore")]]
    await update.message.reply_text("**آیا از جایگزینی دیتابیس فعلی کاملاً مطمئن هستید؟ این عمل غیرقابل بازگشت است.**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN); return BACKUP_MENU

async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات در حال خاموش شدن است...")
    db.close_db()
    asyncio.create_task(context.application.shutdown())

def main():
    """Start the bot."""
    db.init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    job_queue = application.job_queue
    job_queue.run_repeating(check_low_usage, interval=timedelta(hours=4), first=10)
    admin_filter = filters.User(user_id=ADMIN_ID)
    user_filter = ~admin_filter
    
    buy_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_start, pattern='^user_buy_')],
        states={GET_CUSTOM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_name), CommandHandler('skip', skip_custom_name)]},
        fallbacks=[CommandHandler('cancel', user_generic_cancel)],
        per_user=True, per_chat=True, per_message=False
    )
    gift_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🎁 کد هدیه$') & user_filter, gift_code_entry)],
        states={REDEEM_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_gift_code)]},
        fallbacks=[CommandHandler('cancel', user_generic_cancel)],
        per_user=True, per_chat=True, per_message=False
    )
    charge_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(charge_start, pattern='^user_start_charge$')],
        states={
            CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_amount_received)],
            CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_receipt_received)]
        },
        fallbacks=[CommandHandler('cancel', user_generic_cancel)],
        per_user=True, per_chat=True, per_message=False
    )
    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_setting_start, pattern="^admin_edit_setting_")],
        states={AWAIT_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_value_received)]},
        fallbacks=[CommandHandler('cancel', admin_conv_cancel)],
        per_user=True, per_chat=True,
    )
    edit_plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_plan_start, pattern="^admin_edit_plan_")],
        states={
            EDIT_PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_plan_name_received), CommandHandler('skip', skip_edit_plan_name)],
            EDIT_PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_plan_price_received), CommandHandler('skip', skip_edit_plan_price)],
            EDIT_PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_plan_days_received), CommandHandler('skip', skip_edit_plan_days)],
            EDIT_PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_plan_gb_received), CommandHandler('skip', skip_edit_plan_gb)],
        },
        fallbacks=[CommandHandler('cancel', admin_conv_cancel)],
        per_user=True, per_chat=True,
    )
    
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{BTN_ADMIN_PANEL}$') & admin_filter, admin_entry)],
        states={
            ADMIN_MENU: [
                MessageHandler(filters.Regex('^➕ مدیریت پلن‌ها$'), plan_management_menu),
                MessageHandler(filters.Regex('^📈 گزارش‌ها و آمار$'), reports_menu),
                MessageHandler(filters.Regex('^⚙️ تنظیمات$'), settings_menu),
                MessageHandler(filters.Regex('^💾 پشتیبان‌گیری$'), backup_restore_menu),
                MessageHandler(filters.Regex('^📩 ارسال پیام$'), broadcast_menu),
                MessageHandler(filters.Regex('^👥 مدیریت کاربران$'), user_management_menu),
                MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$'), shutdown_bot),
                CallbackQueryHandler(edit_setting_start, pattern="^admin_edit_setting_"),
            ],
            REPORTS_MENU: [
                MessageHandler(filters.Regex('^📊 آمار کلی$'), show_stats_report),
                MessageHandler(filters.Regex('^📈 گزارش فروش امروز$'), show_daily_report),
                MessageHandler(filters.Regex('^📅 گزارش فروش ۷ روز اخیر$'), show_weekly_report),
                MessageHandler(filters.Regex('^🏆 محبوب‌ترین پلن‌ها$'), show_popular_plans_report),
                MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
            ],
            PLAN_MENU: [
                MessageHandler(filters.Regex('^➕ افزودن پلن جدید$'), add_plan_start),
                MessageHandler(filters.Regex('^📋 لیست پلن‌ها$'), list_plans_admin),
                MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
                CallbackQueryHandler(admin_delete_plan_callback, pattern="^admin_delete_plan_"),
                CallbackQueryHandler(admin_toggle_plan_visibility_callback, pattern="^admin_toggle_plan_"),
                CallbackQueryHandler(edit_plan_start, pattern="^admin_edit_plan_")
            ],
            PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_name_received)],
            PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_price_received)],
            PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_days_received)],
            PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_gb_received)],
            MANAGE_USER_ID: [
                MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_id_received)
            ],
            MANAGE_USER_ACTION: [
                MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_action_handler)
            ],
            MANAGE_USER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_user_amount_received)],
            BROADCAST_MENU: [
                MessageHandler(filters.Regex('^ارسال به همه کاربران$'), broadcast_to_all_start),
                MessageHandler(filters.Regex('^ارسال به کاربر خاص$'), broadcast_to_user_start),
                MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu)
            ],
            BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_to_all_confirm)],
            BROADCAST_CONFIRM: [MessageHandler(filters.Regex('^بله، ارسال کن$'), broadcast_to_all_send), MessageHandler(filters.Regex('^خیر، لغو کن$'), admin_generic_cancel)],
            BROADCAST_TO_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_to_user_id_received)],
            BROADCAST_TO_USER_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_to_user_message_received)],
            BACKUP_MENU: [
                MessageHandler(filters.Regex('^📥 دریافت فایل پشتیبان$'), send_backup_file),
                MessageHandler(filters.Regex('^📤 بارگذاری فایل پشتیبان$'), restore_start),
                MessageHandler(filters.Regex(f'^{BTN_BACK_TO_ADMIN_MENU}$'), back_to_admin_menu),
                CallbackQueryHandler(admin_confirm_restore_callback, pattern="^admin_confirm_restore$"),
                CallbackQueryHandler(admin_cancel_restore_callback, pattern="^admin_cancel_restore$"),
            ],
            RESTORE_UPLOAD: [MessageHandler(filters.Document.FileExtension("db"), restore_receive_file)]
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{BTN_EXIT_ADMIN_PANEL}$'), exit_admin_panel),
            CommandHandler('cancel', admin_generic_cancel),
        ],
        per_user=True, per_chat=True, allow_reentry=True
    )
    
    application.add_handler(charge_handler, group=1)
    application.add_handler(gift_handler, group=1)
    application.add_handler(buy_handler, group=1)
    application.add_handler(settings_conv, group=1)
    application.add_handler(edit_plan_conv, group=1)
    application.add_handler(admin_conv, group=1)
    
    application.add_handler(CallbackQueryHandler(admin_confirm_charge_callback, pattern="^admin_confirm_charge_"))
    application.add_handler(CallbackQueryHandler(admin_reject_charge_callback, pattern="^admin_reject_charge_"))

    application.add_handler(CallbackQueryHandler(show_link_options_menu, pattern="^showlinks_"), group=2)
    application.add_handler(CallbackQueryHandler(get_link_callback, pattern="^getlink_"), group=2)
    application.add_handler(CallbackQueryHandler(refresh_service_details, pattern="^refresh_"), group=2)
    application.add_handler(CallbackQueryHandler(renew_service_handler, pattern="^renew_"), group=2)
    application.add_handler(CallbackQueryHandler(confirm_renewal_callback, pattern="^confirmrenew$"), group=2)
    application.add_handler(CallbackQueryHandler(cancel_renewal_callback, pattern="^cancelrenew$"), group=2)
    
    application.add_handler(CommandHandler("start", start), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), buy_service_list), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📋 سرویس‌های من$'), list_my_services), group=3)
    application.add_handler(MessageHandler(filters.Regex('^💰 موجودی و شارژ$'), show_balance), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), show_support), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📚 راهنمای اتصال$'), show_guide), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🧪 دریافت سرویس تست رایگان$'), get_trial_service), group=3)

    print("Bot is running with final corrections. All features should work correctly.")
    application.run_polling()

if __name__ == "__main__":
    main()