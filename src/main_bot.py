# -*- coding: utf-8 -*-

import logging
import os
import shutil
import asyncio
import random
import sqlite3
import io
import re
from types import SimpleNamespace
from datetime import datetime, timedelta, time
import jdatetime
from typing import Union
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
    PANEL_DOMAIN, SUB_PATH, TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB,
    REFERRAL_BONUS_AMOUNT, EXPIRY_REMINDER_DAYS, USAGE_ALERT_THRESHOLD
)
import qrcode

# Setup
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

# Buttons (Persian labels only)
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

def get_main_menu_keyboard(user_id):
    user_info = db.get_or_create_user(user_id)
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["💰 موجودی و شارژ", "🎁 کد هدیه"],
        ["🎁 معرفی دوستان"]
    ]
    if TRIAL_ENABLED and user_info and not user_info.get('has_used_trial'):
        keyboard.insert(2, ["🧪 دریافت سرویس تست رایگان"])
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

# Helpers
def _parse_date_flexible(date_str: str) -> Union[datetime.date, None]:
    if not date_str:
        return None
    date_part = date_str.split('T')[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_part, fmt).date()
        except (ValueError, TypeError):
            continue
    logger.error(f"Date parse failed for '{date_str}'.")
    return None

async def _get_service_status(hiddify_info):
    date_keys = ['start_date', 'last_reset_time', 'created_at']
    start_date_str = None
    for key in date_keys:
        if hiddify_info.get(key):
            start_date_str = hiddify_info.get(key)
            break
    package_days = hiddify_info.get('package_days', 0)
    if not start_date_str:
        logger.warning(f"Missing date keys in hiddify info: {hiddify_info}")
        return "Unknown", "N/A", True

    start_date_obj = _parse_date_flexible(start_date_str)
    if not start_date_obj:
        return "Unknown", "N/A", True

    expiry_date_obj = start_date_obj + timedelta(days=package_days)
    jalali_expiry_date = jdatetime.date.fromgregorian(date=expiry_date_obj)
    jalali_display_str = jalali_expiry_date.strftime("%Y/%m/%d")
    is_expired = expiry_date_obj < datetime.now().date()
    status = "Expired" if is_expired else "Active"
    return status, jalali_display_str, is_expired

def is_valid_sqlite(filepath):
    try:
        with sqlite3.connect(filepath) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
        return result[0] == 'ok'
    except sqlite3.DatabaseError:
        return False

# Background jobs (PTB JobQueue handlers)
async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: checking low-usage services...")
    all_services = db.get_all_active_services()
    for service in all_services:
        if service['low_usage_alert_sent']:
            continue
        try:
            info = await hiddify_api.get_user_info(service['sub_uuid'])
            if not info:
                logger.warning(f"Could not fetch info for service {service['service_id']}.")
                continue

            _, _, is_expired = await _get_service_status(info)
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
                        f"Usage alert!\n\n"
                        f"You have used more than {int(USAGE_ALERT_THRESHOLD * 100)}% of your quota for {service_name}.\n"
                        f"({current_usage:.2f} GB of {usage_limit:.0f} GB)\n\n"
                        "To avoid disconnection, please renew your service."
                    )
                )
                db.set_low_usage_alert_sent(service['service_id'])
                logger.info(f"Low-usage alert sent to {user_id} for service {service['service_id']}.")
                await asyncio.sleep(0.2)
        except (Forbidden, BadRequest) as e:
            logger.warning(f"Failed to send low-usage alert to {service['user_id']}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in low-usage job for service {service['service_id']}: {e}", exc_info=True)

async def check_expiring_services(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Job: checking expiring services...")
    all_services = db.get_all_active_services()
    for service in all_services:
        try:
            info = await hiddify_api.get_user_info(service['sub_uuid'])
            if not info:
                continue

            _, expiry_date_str, is_expired = await _get_service_status(info)
            if is_expired or expiry_date_str == "N/A":
                continue

            parts = expiry_date_str.split('/')
            jalali_date = jdatetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
            gregorian_expiry_date = jalali_date.togregorian()
            days_left = (gregorian_expiry_date - datetime.now().date()).days

            if days_left == EXPIRY_REMINDER_DAYS:
                user_id = service['user_id']
                service_name = f"'{service['name']}'" if service['name'] else ""
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"Service expiry reminder\n\n"
                        f"Only {days_left} day(s) left until your service {service_name} expires.\n\n"
                        f"Please renew to avoid disconnection."
                    )
                )
                logger.info(f"Expiry reminder sent to {user_id} for service {service['service_id']}.")
                await asyncio.sleep(0.2)
        except (Forbidden, BadRequest) as e:
            logger.warning(f"Failed to send expiry reminder to {service['user_id']}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in expiry reminder job for service {service['service_id']}: {e}", exc_info=True)

# Fallback loops (used if JobQueue is unavailable)
async def _low_usage_loop(app: Application, interval_s: int = 4 * 60 * 60):
    ctx = SimpleNamespace(bot=app.bot)
    while True:
        try:
            await check_low_usage(ctx)
        except Exception:
            logger.exception("Error in _low_usage_loop")
        await asyncio.sleep(interval_s)

async def _daily_expiry_loop(app: Application, hour: int = 9, minute: int = 0):
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), time(hour, minute))
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        ctx = SimpleNamespace(bot=app.bot)
        try:
            await check_expiring_services(ctx)
        except Exception:
            logger.exception("Error in _daily_expiry_loop")

# Generic Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username)

    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != user.id:
                db.set_referrer(user.id, referrer_id)
        except (ValueError, IndexError):
            logger.warning(f"Invalid referral link: {context.args[0]}")

    user_info = db.get_user(user.id)
    if user_info and user_info.get('is_banned'):
        await update.message.reply_text("You are banned from using this bot.")
        return ConversationHandler.END

    await update.message.reply_text("Welcome to the VPN Sales Bot!", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Operation cancelled.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Operation cancelled.", reply_markup=get_admin_menu_keyboard())
    return ConversationHandler.END

async def user_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Operation cancelled.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END

# User Service Management
async def list_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.effective_message

    services = db.get_user_services(user_id)
    if not services:
        await message.reply_text("You have no active services yet.")
        return

    keyboard = []
    for service in services:
        button_text = f"⚙️ {service['name']}"
        callback_data = f"view_service_{service['service_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await message.edit_text("Please choose a service to manage:", reply_markup=reply_markup)
    else:
        await message.reply_text("Please choose a service to manage:", reply_markup=reply_markup)

async def view_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = int(query.data.split('_')[-1])
    await query.edit_message_text("Fetching service info... ⏳")
    await send_service_details(context, query.from_user.id, service_id, original_message=query.message, is_from_menu=True)

async def send_service_details(context: ContextTypes.DEFAULT_TYPE, chat_id: int, service_id: int, original_message=None, is_from_menu: bool = False):
    service = db.get_service(service_id)
    if not service:
        error_text = "Service not found."
        if original_message:
            await original_message.edit_text(error_text)
        else:
            await context.bot.send_message(chat_id=chat_id, text=error_text)
        return
    try:
        info = await hiddify_api.get_user_info(service['sub_uuid'])
        if info:
            status, expiry_date_display, is_expired = await _get_service_status(info)
            renewal_plan = db.get_plan(service['plan_id'])

            sub_path = SUB_PATH or ADMIN_PATH
            sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
            base_link = f"https://{sub_domain}/{sub_path}/{service['sub_uuid']}"
            config_name = info.get('name', 'config')
            final_link = f"{base_link}/?name={config_name.replace(' ', '_')}"
            qr_image = qrcode.make(final_link)
            bio = io.BytesIO()
            bio.name = 'qrcode.png'
            qr_image.save(bio, 'PNG')
            bio.seek(0)

            caption = (
                f"Service name: **{service['name']}**\n\n"
                f"Usage: **{info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f}** GB\n"
                f"Expiry date (Jalali): **{expiry_date_display}**\n"
                f"Status: {status}\n\n"
                f"Subscription link:\n`{final_link}`"
            )

            keyboard = [
                [InlineKeyboardButton("🔄 به‌روزرسانی اطلاعات", callback_data=f"refresh_{service['service_id']}")]
            ]
            if renewal_plan and service.get('plan_id', 0) > 0:
                keyboard.append([InlineKeyboardButton(f"⏳ تمدید سرویس ({renewal_plan['price']:.0f} تومان)", callback_data=f"renew_{service['service_id']}")])
            if is_from_menu:
                keyboard.append([InlineKeyboardButton("⬅️ بازگشت به لیست سرویس‌ها", callback_data="back_to_services")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            if original_message:
                try:
                    await original_message.delete()
                except BadRequest:
                    pass

            await context.bot.send_photo(
                chat_id=chat_id,
                photo=bio,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        else:
            raise ConnectionError(f"API returned no info for UUID {service['sub_uuid']}")
    except Exception as e:
        logger.error(f"send_service_details error for service_id {service_id}: {e}", exc_info=True)
        error_text = "Failed to retrieve service info. Please try again later."
        if original_message:
            try:
                await original_message.edit_text(error_text)
            except BadRequest:
                pass
        else:
            await context.bot.send_message(chat_id=chat_id, text=error_text)

async def refresh_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = int(query.data.split('_')[1])
    service = db.get_service(service_id)
    if service and service['user_id'] == query.from_user.id:
        await query.message.delete()
        msg = await context.bot.send_message(chat_id=query.from_user.id, text="Updating info...")
        await send_service_details(context, query.from_user.id, service_id, original_message=msg, is_from_menu=True)
    else:
        await query.answer("Error: This service does not belong to you.", show_alert=True)

async def back_to_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except BadRequest:
        pass
    await list_my_services(update, context)

# Renewal
async def renew_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()

    service_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    service = db.get_service(service_id)
    if not service:
        await context.bot.send_message(chat_id=user_id, text="Invalid service.")
        return
    plan = db.get_plan(service['plan_id'])
    if not plan:
        await context.bot.send_message(chat_id=user_id, text="Renewal plan not found.")
        return
    user = db.get_or_create_user(user_id)
    if user['balance'] < plan['price']:
        await context.bot.send_message(chat_id=user_id, text=f"Insufficient balance to renew. Required: {plan['price']:.0f} Toman.")
        return

    msg = await context.bot.send_message(chat_id=user_id, text="Checking service status... ⏳")
    hiddify_info = await hiddify_api.get_user_info(service['sub_uuid'])
    if not hiddify_info:
        await msg.edit_text("Could not fetch service info from panel. Please try again later.")
        return

    _, _, is_expired = await _get_service_status(hiddify_info)
    context.user_data['renewal_service_id'] = service_id
    context.user_data['renewal_plan_id'] = plan['plan_id']

    if is_expired:
        await proceed_with_renewal(update, context, original_message=msg)
    else:
        keyboard = [
            [InlineKeyboardButton("✅ بله، تمدید کن", callback_data=f"confirmrenew")],
            [InlineKeyboardButton("❌ خیر، لغو کن", callback_data=f"cancelrenew")]
        ]
        await msg.edit_text(
            "Warning!\n\nYour service is still active. Renewing now will reset your remaining time and data and start a new period from today.\n\nDo you want to continue?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

async def confirm_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await proceed_with_renewal(update, context, original_message=query.message)

async def proceed_with_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE, original_message=None):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    service_id = context.user_data.get('renewal_service_id')
    plan_id = context.user_data.get('renewal_plan_id')

    if not all([service_id, plan_id]):
        if original_message:
            await original_message.edit_text("Internal error: renewal state not found.")
        return

    if original_message:
        await original_message.edit_text("Submitting renewal request... ⏳")

    transaction_id = db.initiate_renewal_transaction(user_id, service_id, plan_id)
    if not transaction_id:
        if original_message:
            await original_message.edit_text("Failed to start renewal (insufficient balance or internal error).")
        return

    service = db.get_service(service_id)
    plan = db.get_plan(plan_id)

    logger.info(
        f"Renewing service {service_id} for user {user_id} with UUID {service['sub_uuid']}. "
        f"Plan days={plan['days']}, gb={plan['gb']}"
    )

    new_hiddify_info = await hiddify_api.renew_user_subscription(service['sub_uuid'], plan['days'], plan['gb'])
    logger.info(f"Renewal API result: {new_hiddify_info}")

    if new_hiddify_info:
        db.finalize_renewal_transaction(transaction_id, plan_id)
        if original_message:
            await original_message.edit_text("Service renewed successfully. Showing updated details...")
        await send_service_details(context, user_id, service_id, original_message=original_message, is_from_menu=True)
    else:
        db.cancel_renewal_transaction(transaction_id)
        if original_message:
            await original_message.edit_text("Renewal failed due to panel communication issue. Please contact support.")

    context.user_data.clear()

async def cancel_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Renewal cancelled.")
    context.user_data.clear()

# Main User Flow
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="user_start_charge")]]
    await update.message.reply_text(
        f"Your current balance: **{user['balance']:.0f}** Toman",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"For support, message @{SUPPORT_USERNAME}")

async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Connection guide:\n\n(Provide your instructions here)")

async def show_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    bonus_str = db.get_setting('referral_bonus_amount')
    try:
        bonus = int(float(bonus_str)) if bonus_str is not None else REFERRAL_BONUS_AMOUNT
    except (ValueError, TypeError):
        bonus = REFERRAL_BONUS_AMOUNT

    text = (
        f"Invite friends and earn rewards!\n\n"
        f"Share your unique link below with your friends.\n\n"
        f"Link:\n`{referral_link}`\n\n"
        f"When a friend joins via your link and completes their first purchase, "
        f"you both receive **{bonus:,.0f} Toman** in your wallet!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def get_trial_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = db.get_or_create_user(user_id, update.effective_user.username)
    if not TRIAL_ENABLED:
        await update.message.reply_text("Free trial is currently disabled.")
        return
    if user_info.get('has_used_trial'):
        await update.message.reply_text("You have already used your free trial.")
        return
    msg_loading = await update.message.reply_text("Creating your trial service... ⏳")
    result = await hiddify_api.create_hiddify_user(TRIAL_DAYS, TRIAL_GB, user_id, custom_name="Trial Service")
    if result and result.get('uuid'):
        db.set_user_trial_used(user_id)
        db.add_active_service(user_id, "Trial Service", result['uuid'], result['full_link'], 0)
        await show_link_options_menu(update.message, result['uuid'], is_edit=False)
    else:
        await msg_loading.edit_text("Failed to create trial service. Please try again later.")

# Gift Code
async def gift_code_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please enter your gift code:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return REDEEM_GIFT

async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.upper()
    user_id = update.effective_user.id
    amount = db.use_gift_code(code, user_id)
    if amount is not None:
        await update.message.reply_text(f"Success! {amount:.0f} Toman added to your wallet.", reply_markup=get_main_menu_keyboard(user_id))
    else:
        await update.message.reply_text("Invalid or used gift code.", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

# Charge
async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Please enter the amount in Toman (numbers only):", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return CHARGE_AMOUNT

async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount < 1000:
            raise ValueError
        context.user_data['charge_amount'] = amount
        card_number = db.get_setting('card_number') or "[not set]"
        card_holder = db.get_setting('card_holder') or "[not set]"
        await update.message.reply_text(
            f"Please transfer **{amount:,} Toman** to the card below:\n\n`{card_number}`\nAccount holder: {card_holder}\n\nThen send a photo of your receipt.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
        )
        return CHARGE_RECEIPT
    except (ValueError, TypeError):
        await update.message.reply_text("Please enter a valid integer amount (>= 1000).")
        return CHARGE_AMOUNT

async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = context.user_data.get('charge_amount')
    if not amount:
        await update.message.reply_text("Error: charge amount is missing. Start over.", reply_markup=get_main_menu_keyboard(user.id))
        return ConversationHandler.END
    receipt_photo = update.message.photo[-1]
    caption = (
        f"New charge request\n\n"
        f"User: {user.full_name} (@{user.username or 'N/A'})\n"
        f"Numeric ID: `{user.id}`\n"
        f"Requested amount: **{amount:,} Toman**"
    )
    keyboard = [[InlineKeyboardButton("✅ تایید شارژ", callback_data=f"admin_confirm_charge_{user.id}_{int(amount)}"),
                 InlineKeyboardButton("❌ رد درخواست", callback_data=f"admin_reject_charge_{user.id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=receipt_photo.file_id, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_text("Your receipt has been sent to the admin. Please wait for review.", reply_markup=get_main_menu_keyboard(user.id))
    context.user_data.clear()
    return ConversationHandler.END

# Buy
async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans(only_visible=True)
    if not plans:
        await update.message.reply_text("No plans are available at the moment.")
        return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان", callback_data=f"user_buy_{p['plan_id']}")] for p in plans]
    await update.message.reply_text("Please select a plan:", reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    transaction_id = db.initiate_purchase_transaction(query.from_user.id, plan_id)
    if not transaction_id:
        user = db.get_or_create_user(query.from_user.id)
        plan = db.get_plan(plan_id)
        await query.edit_message_text(f"Insufficient balance.\nYour balance: {user['balance']:.0f} Toman\nPlan price: {plan['price']:.0f} Toman")
        return ConversationHandler.END
    context.user_data['transaction_id'] = transaction_id
    context.user_data['plan_to_buy_id'] = plan_id
    await query.edit_message_text(
        f"Plan selected.\n\nEnter a custom name for this service (e.g., Personal Phone).\nSend {CMD_SKIP} to use the default name.",
        reply_markup=None
    )
    return GET_CUSTOM_NAME

async def get_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_name = update.message.text
    if len(custom_name) > 50:
        await update.message.reply_text("Name is too long (max 50).")
        return GET_CUSTOM_NAME
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
        await message.reply_text("Internal error. Please try again.", reply_markup=get_main_menu_keyboard(user_id))
        context.user_data.clear()
        return

    plan = db.get_plan(plan_id)
    custom_name = custom_name_input if custom_name_input else f"Service {plan['gb']}GB"

    msg_loading = await message.reply_text("Creating your service... ⏳", reply_markup=get_main_menu_keyboard(user_id))
    result = await hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id, custom_name=custom_name)

    if result and result.get('uuid'):
        db.finalize_purchase_transaction(transaction_id, result['uuid'], result['full_link'], custom_name)
        referrer_id, bonus_amount = db.apply_referral_bonus(user_id)
        if referrer_id:
            try:
                await context.bot.send_message(user_id, f"Congrats! {bonus_amount:,.0f} Toman bonus was added to your wallet for your first purchase.")
                await context.bot.send_message(referrer_id, f"Congrats! Your friend completed a purchase and {bonus_amount:,.0f} Toman was added to your wallet.")
            except (Forbidden, BadRequest):
                logger.warning(f"Could not send referral notifications to {user_id} or {referrer_id}.")
        try:
            await msg_loading.delete()
        except BadRequest as e:
            logger.warning(f"Could not delete 'loading' message: {e}")
        await show_link_options_menu(message, result['uuid'], is_edit=False)
    else:
        db.cancel_purchase_transaction(transaction_id)
        await msg_loading.edit_text("Failed to create service. Please contact support.")

    context.user_data.clear()
    return ConversationHandler.END

# Link & QR Code
async def show_link_options_menu(message: Update.message, user_uuid: str, is_edit: bool = True):
    keyboard = [
        [InlineKeyboardButton("🔗 لینک هوشمند (Auto)", callback_data=f"getlink_auto_{user_uuid}")],
        [InlineKeyboardButton("📱 لینک SingBox", callback_data=f"getlink_singbox_{user_uuid}")],
        [InlineKeyboardButton("💻 لینک استاندارد (V2ray)", callback_data=f"getlink_sub_{user_uuid}")]
    ]
    text = "Your service has been created. Please select a subscription link type:"
    try:
        if is_edit:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except BadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"show_link_options_menu error: {e}")

async def get_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, link_type, user_uuid = query.data.split('_')
    await query.message.edit_text("Generating link and QR Code... ⏳")
    sub_path = SUB_PATH or ADMIN_PATH
    sub_domain = random.choice(SUB_DOMAINS) if SUB_DOMAINS else PANEL_DOMAIN
    base_link = f"https://{sub_domain}/{sub_path}/{user_uuid}"
    user_info = await hiddify_api.get_user_info(user_uuid)
    config_name = user_info.get('name', 'config') if user_info else 'config'
    final_link = f"{base_link}/" if link_type == "auto" else f"{base_link}/{link_type}/"
    final_link_with_fragment = f"{final_link}?name={config_name.replace(' ', '_')}"
    qr_image = qrcode.make(final_link_with_fragment)
    bio = io.BytesIO(); bio.name = 'qrcode.png'; qr_image.save(bio, 'PNG'); bio.seek(0)
    caption = (
        f"Config name: **{config_name}**\n\n"
        f"Scan the QR or use the link to connect.\n\n"
        f"Your subscription link:\n`{final_link_with_fragment}`"
    )
    await query.message.delete()
    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=bio,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_keyboard(query.from_user.id)
    )

# ADMIN SECTION (texts in English, buttons remain Persian)
async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to the admin panel.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("You have exited the admin panel.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END

async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Back to admin main menu.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def admin_delete_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    db.delete_plan(plan_id)
    await query.message.delete()
    await query.from_user.send_message("Plan deleted successfully.")
    return PLAN_MENU

async def admin_toggle_plan_visibility_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    db.toggle_plan_visibility(plan_id)
    await query.answer("Plan visibility toggled.")
    await query.message.delete()
    await query.from_user.send_message("Visibility changed. Reopen the list to refresh.")
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
        logger.error(f"admin_confirm_charge_callback parse error: {query.data} | {e}")
        try:
            if query.message.photo:
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n---\nFailed to process the button data.")
            else:
                await query.edit_message_text("Failed to process the button data.")
        except Exception as edit_error:
            logger.error(f"Fallback error send failed: {edit_error}")
        return

    db.update_balance(target_user_id, amount)
    original_caption = query.message.caption or ""
    admin_feedback = f"{original_caption}\n\n---\nSuccessfully added {amount:,} Toman to user `{target_user_id}`."

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"Your account was successfully charged by **{amount:,} Toman**!",
            parse_mode=ParseMode.MARKDOWN
        )
    except (Forbidden, BadRequest):
        admin_feedback += "\n\nWarning: User has blocked the bot. Confirmation not delivered."

    try:
        await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"edit_message_caption failed: {e}. Sending new message.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_feedback, parse_mode=ParseMode.MARKDOWN)

async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        target_user_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"admin_reject_charge_callback parse error: {query.data} | {e}")
        try:
            if query.message.photo:
                await query.edit_message_caption(caption=f"{query.message.caption}\n\n---\nFailed to process the button data.")
            else:
                await query.edit_message_text("Failed to process the button data.")
        except Exception as edit_error:
            logger.error(f"Fallback error send failed: {edit_error}")
        return

    original_caption = query.message.caption or ""
    admin_feedback = f"{original_caption}\n\n---\nCharge request of user `{target_user_id}` was rejected."

    try:
        await context.bot.send_message(chat_id=target_user_id, text="Unfortunately, your charge request was rejected by the admin.")
    except (Forbidden, BadRequest):
        admin_feedback += "\n\nWarning: User has blocked the bot."

    try:
        await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"edit_message_caption failed: {e}. Sending new message.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_feedback, parse_mode=ParseMode.MARKDOWN)

async def admin_confirm_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    restore_path = context.user_data.get('restore_path')
    if not restore_path or not os.path.exists(restore_path):
        await query.edit_message_text("Error: backup file not found.")
        return BACKUP_MENU
    try:
        db.close_db()
        shutil.move(restore_path, db.DB_NAME)
        db.init_db()
        await query.edit_message_text("Database restored successfully.\n\nImportant: Please restart the bot to apply changes.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"DB restore error: {e}", exc_info=True)
        await query.edit_message_text(f"Error replacing database file: {e}")
    context.user_data.clear()
    return BACKUP_MENU

async def admin_cancel_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    restore_path = context.user_data.get('restore_path')
    if restore_path and os.path.exists(restore_path):
        os.remove(restore_path)
    await query.edit_message_text("Restore cancelled.")
    context.user_data.clear()
    return BACKUP_MENU

# Plan Management
async def plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["➕ افزودن پلن جدید", "📋 لیست پلن‌ها"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("Plans Management", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return PLAN_MENU

async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans:
        await update.message.reply_text("No plans defined.")
        return PLAN_MENU
    await update.message.reply_text("Defined plans:")
    for plan in plans:
        visibility_icon = "👁️" if plan['is_visible'] else "🙈"
        text = (f"**{plan['name']}** (ID: {plan['plan_id']})\n"
                f"Price: {plan['price']:.0f} Toman\n"
                f"Duration: {plan['days']} days\n"
                f"Volume: {plan['gb']} GB\n"
                f"Visibility: {'Visible' if plan['is_visible'] else 'Hidden'}")
        keyboard = [[
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"admin_edit_plan_{plan['plan_id']}"),
            InlineKeyboardButton(f"{visibility_icon} تغییر وضعیت", callback_data=f"admin_toggle_plan_{plan['plan_id']}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"admin_delete_plan_{plan['plan_id']}")
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return PLAN_MENU

async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter plan name:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return PLAN_NAME

async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_name'] = update.message.text
    await update.message.reply_text("Enter price (Toman):")
    return PLAN_PRICE

async def plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_price'] = float(update.message.text)
        await update.message.reply_text("Enter duration (days):")
        return PLAN_DAYS
    except ValueError:
        await update.message.reply_text("Please enter a numeric price.")
        return PLAN_PRICE

async def plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_days'] = int(update.message.text)
        await update.message.reply_text("Enter volume (GB):")
        return PLAN_GB
    except ValueError:
        await update.message.reply_text("Please enter a numeric duration (days).")
        return PLAN_DAYS

async def plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_gb'] = int(update.message.text)
        db.add_plan(context.user_data['plan_name'], context.user_data['plan_price'], context.user_data['plan_days'], context.user_data['plan_gb'])
        await update.message.reply_text("Plan added successfully.", reply_markup=get_admin_menu_keyboard())
        context.user_data.clear()
        return ADMIN_MENU
    except ValueError:
        await update.message.reply_text("Please enter a numeric volume (GB).")
        return PLAN_GB

# Edit Plan
async def edit_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    plan = db.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("Plan not found.")
        return ConversationHandler.END
    context.user_data['edit_plan_id'] = plan_id
    context.user_data['edit_plan_data'] = {}
    await query.message.reply_text(
        f"Editing plan: **{plan['name']}**\n\nEnter new name or {CMD_SKIP} to skip.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup([[CMD_SKIP], [CMD_CANCEL]], resize_keyboard=True)
    )
    return EDIT_PLAN_NAME

async def edit_plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_plan_data']['name'] = update.message.text
    await update.message.reply_text(f"Enter new price (Toman) or {CMD_SKIP} to skip.")
    return EDIT_PLAN_PRICE

async def skip_edit_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Enter new price (Toman) or {CMD_SKIP} to skip.")
    return EDIT_PLAN_PRICE

async def edit_plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['price'] = float(update.message.text)
        await update.message.reply_text(f"Enter new duration (days) or {CMD_SKIP} to skip.")
        return EDIT_PLAN_DAYS
    except ValueError:
        await update.message.reply_text("Please enter a numeric price.")
        return EDIT_PLAN_PRICE

async def skip_edit_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Enter new duration (days) or {CMD_SKIP} to skip.")
    return EDIT_PLAN_DAYS

async def edit_plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['days'] = int(update.message.text)
        await update.message.reply_text(f"Enter new volume (GB) or {CMD_SKIP} to skip.")
        return EDIT_PLAN_GB
    except ValueError:
        await update.message.reply_text("Please enter a numeric duration (days).")
        return EDIT_PLAN_DAYS

async def skip_edit_plan_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Enter new volume (GB) or {CMD_SKIP} to skip.")
    return EDIT_PLAN_GB

async def edit_plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['edit_plan_data']['gb'] = int(update.message.text)
        await finish_plan_edit(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Please enter a numeric volume (GB).")
        return EDIT_PLAN_GB

async def skip_edit_plan_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Skipping volume change.")
    await finish_plan_edit(update, context)
    return ConversationHandler.END

async def finish_plan_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plan_id = context.user_data.get('edit_plan_id')
    new_data = context.user_data.get('edit_plan_data')
    if not new_data:
        await update.message.reply_text("No changes applied.", reply_markup=get_admin_menu_keyboard())
    else:
        db.update_plan(plan_id, new_data)
        await update.message.reply_text("Plan updated successfully.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ADMIN_MENU

# Reports
async def reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📊 آمار کلی", "📈 گزارش‌ها و آمار"], ["📅 گزارش فروش ۷ روز اخیر", "🏆 محبوب‌ترین پلن‌ها"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("Reports & Analytics", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return REPORTS_MENU

async def show_stats_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    text = (
        f"Bot Stats\n\n"
        f"Total users: {stats.get('total_users', 0)}\n"
        f"Active services: {stats.get('active_services', 0)}\n"
        f"Total revenue: {stats.get('total_revenue', 0):,.0f} Toman\n"
        f"Banned users: {stats.get('banned_users', 0)}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return REPORTS_MENU

async def show_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sales = db.get_sales_report(days=1)
    total_revenue = sum(s['price'] for s in sales)
    await update.message.reply_text(f"Today's sales\n\nCount: {len(sales)}\nRevenue: {total_revenue:,.0f} Toman", parse_mode=ParseMode.MARKDOWN)
    return REPORTS_MENU

async def show_weekly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sales = db.get_sales_report(days=7)
    total_revenue = sum(s['price'] for s in sales)
    await update.message.reply_text(f"Last 7 days sales\n\nCount: {len(sales)}\nRevenue: {total_revenue:,.0f} Toman", parse_mode=ParseMode.MARKDOWN)
    return REPORTS_MENU

async def show_popular_plans_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.get_popular_plans(limit=5)
    if not plans:
        await update.message.reply_text("No plan has been sold yet.")
        return REPORTS_MENU
    text = "Top plans\n\n" + "\n".join([f"{i}. **{plan['name']}** - {plan['sales_count']} sales" for i, plan in enumerate(plans, 1)])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return REPORTS_MENU

# Settings
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number = db.get_setting('card_number') or "not set"
    card_holder = db.get_setting('card_holder') or "not set"
    referral_bonus = db.get_setting('referral_bonus_amount') or str(REFERRAL_BONUS_AMOUNT)
    text = (f"Bot Settings\n\n"
            f"Card number: `{card_number}`\n"
            f"Account holder: `{card_holder}`\n"
            f"Referral bonus (Toman): `{referral_bonus}`\n\n"
            "Use the buttons to edit.")
    keyboard = [
        [InlineKeyboardButton("ویرایش شماره کارت", callback_data="admin_edit_setting_card_number"),
         InlineKeyboardButton("ویرایش نام صاحب حساب", callback_data="admin_edit_setting_card_holder")],
        [InlineKeyboardButton("ویرایش مبلغ هدیه معرفی", callback_data="admin_edit_setting_referral_bonus_amount")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU

async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    setting_key = query.data.split('admin_edit_setting_')[-1]
    context.user_data['setting_to_edit'] = setting_key
    prompt_map = {
        'card_number': "Enter a new card number:",
        'card_holder': "Enter a new account holder name:",
        'referral_bonus_amount': "Enter the referral bonus amount (Toman):"
    }
    prompt_text = prompt_map.get(setting_key)
    if not prompt_text:
        await query.message.edit_text("Unknown setting.")
        return ConversationHandler.END
    await query.message.reply_text(prompt_text, reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return AWAIT_SETTING_VALUE

async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting_key = context.user_data.get('setting_to_edit')
    if not setting_key:
        return await admin_conv_cancel(update, context)
    value = update.message.text.strip()
    if setting_key == 'referral_bonus_amount':
        try:
            value_num = int(float(value))
            value = str(value_num)
        except (ValueError, TypeError):
            await update.message.reply_text("Please enter a valid integer amount (e.g., 5000).")
            return AWAIT_SETTING_VALUE
    db.set_setting(setting_key, value)
    await update.message.reply_text("Settings updated.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# Broadcast
async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["ارسال به همه کاربران", "ارسال به کاربر خاص"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("Broadcast menu", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return BROADCAST_MENU

async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send the message to broadcast to all users:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return BROADCAST_MESSAGE

async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.message
    total_users = db.get_stats()['total_users']
    await update.message.reply_text(f"Are you sure you want to send this to {total_users} users?", reply_markup=ReplyKeyboardMarkup([["بله، ارسال کن"], ["خیر، لغو کن"]], resize_keyboard=True))
    return BROADCAST_CONFIRM

async def broadcast_to_all_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_to_send = context.user_data.get('broadcast_message')
    if not message_to_send:
        await update.message.reply_text("Error: no message to send.", reply_markup=get_admin_menu_keyboard())
        return ADMIN_MENU
    user_ids = db.get_all_user_ids()
    sent_count, failed_count = 0, 0
    await update.message.reply_text(f"Broadcasting to {len(user_ids)} users...", reply_markup=get_admin_menu_keyboard())
    for user_id in user_ids:
        try:
            await message_to_send.copy_to(chat_id=user_id)
            sent_count += 1
            await asyncio.sleep(0.1)
        except (Forbidden, BadRequest):
            failed_count += 1
    await update.message.reply_text(f"Broadcast finished.\n\nSent: {sent_count}\nFailed: {failed_count}")
    context.user_data.clear()
    return ADMIN_MENU

async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter the numeric user ID:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return BROADCAST_TO_USER_ID

async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        context.user_data['target_user_id'] = target_id
        await update.message.reply_text("User ID set. Now send the message to deliver to this user:")
        return BROADCAST_TO_USER_MESSAGE
    except ValueError:
        await update.message.reply_text("Please enter a valid numeric user ID.")
        return BROADCAST_TO_USER_ID

async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = context.user_data.get('target_user_id')
    if not target_id:
        await update.message.reply_text("Error: target user is not set.", reply_markup=get_admin_menu_keyboard())
        return ADMIN_MENU
    message_to_send = update.message
    try:
        await message_to_send.copy_to(chat_id=target_id)
        await update.message.reply_text("Message sent to the user.", reply_markup=get_admin_menu_keyboard())
    except (Forbidden, BadRequest):
        await update.message.reply_text("Failed to send message. The user may have blocked the bot or the ID is wrong.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ADMIN_MENU

# User Management
async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter a user numeric ID or Telegram username (with or without @):", reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True))
    return MANAGE_USER_ID

async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    user_info = None
    if user_input.isdigit():
        user_info = db.get_user(int(user_input))
    elif re.fullmatch(r'@?[A-Za-z0-9_]{5,32}', user_input):
        user_info = db.get_user_by_username(user_input)
    else:
        await update.message.reply_text("Invalid input. Please enter a numeric ID or a Telegram username.")
        return MANAGE_USER_ID
    if not user_info:
        await update.message.reply_text("No user found with the given identifier.")
        return MANAGE_USER_ID
    context.user_data['target_user_id'] = user_info['user_id']
    ban_text = "آزاد کردن کاربر" if user_info['is_banned'] else "مسدود کردن کاربر"
    keyboard = [["افزایش موجودی", "کاهش موجودی"], ["📜 سوابق خرید", ban_text], [BTN_BACK_TO_ADMIN_MENU]]
    info_text = (
        f"Managing user: `{user_info['user_id']}`\n"
        f"Username: @{user_info.get('username', 'N/A')}\n"
        f"Balance: {user_info['balance']:.0f} Toman\n"
        f"Status: {'Banned' if user_info['is_banned'] else 'Active'}"
    )
    await update.message.reply_text(info_text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
    return MANAGE_USER_ACTION

async def manage_user_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id:
        await update.message.reply_text("Error: target user is not set.")
        return await back_to_admin_menu(update, context)
    if action in ["افزایش موجودی", "کاهش موجودی"]:
        context.user_data['manage_action'] = action
        await update.message.reply_text("Enter the amount (Toman):", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
        return MANAGE_USER_AMOUNT
    elif "مسدود" in action or "آزاد" in action:
        user_info = db.get_user(target_user_id)
        new_ban_status = not user_info['is_banned']
        db.set_user_ban_status(target_user_id, new_ban_status)
        await update.message.reply_text(f"User status changed to: {'Banned' if new_ban_status else 'Active'}.")
        update.message.text = str(target_user_id)
        return await manage_user_id_received(update, context)
    elif action == "📜 سوابق خرید":
        history = db.get_user_sales_history(target_user_id)
        if not history:
            await update.message.reply_text("This user has no purchase history.")
            return MANAGE_USER_ACTION
        response_message = "User purchase history:\n\n"
        for sale in history:
            sale_date = datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S').strftime('%Y/%m/%d - %H:%M')
            response_message += f"- {sale['plan_name'] or 'Deleted plan'} | Price: {sale['price']:.0f} Toman | Date: {sale_date}\n"
        await update.message.reply_text(response_message, parse_mode=ParseMode.MARKDOWN)
        return MANAGE_USER_ACTION
    else:
        await update.message.reply_text("Invalid command. Please use the buttons.")
        return MANAGE_USER_ACTION

async def manage_user_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        action = context.user_data['manage_action']
        target_user_id = context.user_data['target_user_id']
        is_add = True if action == "افزایش موجودی" else False
        db.update_balance(target_user_id, amount if is_add else -amount)
        await update.message.reply_text(f"{amount:.0f} Toman has been {'added to' if is_add else 'deducted from'} the user's balance.")
        update.message.text = str(target_user_id)
        return await manage_user_id_received(update, context)
    except (ValueError, TypeError):
        await update.message.reply_text("Please enter a valid numeric amount.")
        return MANAGE_USER_AMOUNT

# Backup & Restore
async def backup_restore_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📥 دریافت فایل پشتیبان", "📤 بارگذاری فایل پشتیبان"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("Backup & Restore", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return BACKUP_MENU

async def send_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_filename = f"backups/backup_{timestamp}.db"
    try:
        db.close_db()
        shutil.copy(db.DB_NAME, backup_filename)
        db.init_db()
        await update.message.reply_text("Preparing the backup file...")
        await context.bot.send_document(chat_id=update.effective_user.id, document=open(backup_filename, 'rb'), caption=f"Database Backup - {timestamp}")
    except Exception as e:
        await update.message.reply_text(f"Error sending file: {e}")
        logger.error(f"Backup sending error: {e}", exc_info=True)
    finally:
        if os.path.exists(backup_filename):
            os.remove(backup_filename)
    return BACKUP_MENU

async def restore_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Warning: restoring the database will remove current data.\n"
        f"Send your SQLite .db file to continue. Use {CMD_CANCEL} to cancel.",
        parse_mode=ParseMode.MARKDOWN
    )
    return RESTORE_UPLOAD

async def restore_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.endswith('.db'):
        await update.message.reply_text("Invalid file format. Please send a .db file.")
        return RESTORE_UPLOAD
    file = await document.get_file()
    temp_path = os.path.join("backups", f"restore_temp_{datetime.now().timestamp()}.db")
    await file.download_to_drive(temp_path)
    if not is_valid_sqlite(temp_path):
        await update.message.reply_text("The uploaded file is not a valid SQLite database.", reply_markup=get_admin_menu_keyboard())
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return ADMIN_MENU
    context.user_data['restore_path'] = temp_path
    keyboard = [[InlineKeyboardButton("✅ بله، مطمئنم", callback_data="admin_confirm_restore"), InlineKeyboardButton("❌ خیر، لغو کن", callback_data="admin_cancel_restore")]]
    await update.message.reply_text("Are you sure you want to replace the current database? This action is irreversible.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return BACKUP_MENU

async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Shutting down the bot...")
    db.close_db()
    asyncio.create_task(context.application.shutdown())

# Post-init scheduler: use JobQueue if available; otherwise fallback loops
async def _post_init(app: Application):
    jq = app.job_queue
    if jq:
        jq.run_repeating(check_low_usage, interval=timedelta(hours=4), first=10)
        jq.run_daily(check_expiring_services, time=time(hour=9, minute=0))
        logger.info("JobQueue initialized. Background jobs scheduled.")
    else:
        logger.warning('No JobQueue available. Install PTB extra: pip install "python-telegram-bot[job-queue]"')
        app.create_task(_low_usage_loop(app))
        app.create_task(_daily_expiry_loop(app))

def main():
    db.init_db()
    if db.get_setting('referral_bonus_amount') is None:
        db.set_setting('referral_bonus_amount', str(REFERRAL_BONUS_AMOUNT))

    application = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).build()

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
                MessageHandler(filters.Regex('^📈 گزارش‌ها و آمار$'), show_daily_report),
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

    application.add_handler(CallbackQueryHandler(view_service_callback, pattern="^view_service_"), group=2)
    application.add_handler(CallbackQueryHandler(back_to_services_callback, pattern="^back_to_services$"), group=2)
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
    application.add_handler(MessageHandler(filters.Regex('^🎁 معرفی دوستان$'), show_referral_link), group=3)

    print("Bot is running.")
    application.run_polling()

if __name__ == "__main__":
    main()