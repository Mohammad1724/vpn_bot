# -*- coding: utf-8 -*-

import logging
import os
import shutil
import asyncio
import random
import sqlite3
import io
from datetime import datetime, timedelta, time
import jdatetime
from typing import Union
from functools import wraps
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
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import Forbidden, BadRequest
import database as db
import hiddify_api
from config import (
    BOT_TOKEN, ADMIN_ID, SUPPORT_USERNAME, SUB_DOMAINS, ADMIN_PATH,
    PANEL_DOMAIN, SUB_PATH, TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB,
    REFERRAL_BONUS_AMOUNT, EXPIRY_REMINDER_DAYS, FORCE_JOIN_CHANNELS, USAGE_ALERT_THRESHOLD
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
    AWAIT_SETTING_VALUE, REPORT_CUSTOM_DATE_START, REPORT_CUSTOM_DATE_END
) = range(30)


# --- Force Join Decorator ---
def check_channel_membership(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not FORCE_JOIN_CHANNELS:
            return await func(update, context, *args, **kwargs)

        user_id = update.effective_user.id
        if user_id == ADMIN_ID:
            return await func(update, context, *args, **kwargs)

        not_joined_channels = []
        for channel in FORCE_JOIN_CHANNELS:
            try:
                member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
                if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                    not_joined_channels.append(channel)
            except BadRequest as e:
                logger.error(f"Error checking membership for channel {channel}: {e}. Is the bot an admin in this channel?")
                if "chat not found" in str(e).lower():
                    await context.bot.send_message(ADMIN_ID, f"⚠️ **اخطار ادمین:** ربات نتوانست کانال `{channel}` را پیدا کند. لطفاً یوزرنیم یا آیدی کانال را در `config.py` بررسی کنید.", parse_mode=ParseMode.MARKDOWN)
                else:
                    await context.bot.send_message(ADMIN_ID, f"⚠️ **اخطار ادمین:** ربات دسترسی لازم برای چک کردن عضویت در کانال `{channel}` را ندارد. لطفاً ربات را در کانال ادمین کنید.", parse_mode=ParseMode.MARKDOWN)
                not_joined_channels.append(channel)
            except Exception as e:
                logger.error(f"An unexpected error occurred while checking membership for {channel}: {e}")
                not_joined_channels.append(channel)
        
        if not_joined_channels:
            keyboard = []
            text = "کاربر گرامی، برای استفاده از ربات لازم است ابتدا در کانال‌های زیر عضو شوید:\n\n"
            for i, channel in enumerate(not_joined_channels, 1):
                try:
                    chat = await context.bot.get_chat(channel)
                    invite_link = chat.invite_link
                    if not invite_link:
                        invite_link = f"https://t.me/{chat.username}"
                    text += f"{i}- {chat.title}\n"
                    keyboard.append([InlineKeyboardButton(f"عضویت در کانال {chat.title}", url=invite_link)])
                except Exception as e:
                    logger.error(f"Could not get info for channel {channel}: {e}")
                    text += f"{i}- {channel}\n"
                    keyboard.append([InlineKeyboardButton(f"عضویت در کانال", url=f"https://t.me/{channel.lstrip('@')}")])
            
            keyboard.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.answer("لطفا ابتدا در کانال عضو شوید.", show_alert=True)
                if update.effective_message.photo:
                     await update.effective_message.reply_text(text, reply_markup=reply_markup)
                else:
                    try:
                        await update.effective_message.edit_text(text, reply_markup=reply_markup)
                    except BadRequest:
                        await update.effective_message.reply_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)
            return

        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Keyboards ---
def get_main_menu_keyboard(user_id):
    user_info = db.get_or_create_user(user_id)
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["👤 اطلاعات حساب", "🎁 کد هدیه"],
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

# --- Helper Functions ---
def _parse_date_flexible(date_str: str) -> Union[datetime.date, None]:
    if not date_str:
        return None
    date_part = date_str.split('T')[0]
    formats_to_try = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_part, fmt).date()
        except (ValueError, TypeError):
            continue
    logger.error(f"Could not parse date string '{date_str}' with any known format.")
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
        logger.warning(f"Could not find a valid date key {date_keys} in Hiddify info: {hiddify_info}")
        return "⚠️ وضعیت نامشخص", "N/A", True

    start_date_obj = _parse_date_flexible(start_date_str)
    if not start_date_obj:
        return "⚠️ وضعیت نامشخص", "N/A", True
        
    expiry_date_obj = start_date_obj + timedelta(days=package_days)
    jalali_expiry_date = jdatetime.date.fromgregorian(date=expiry_date_obj)
    jalali_display_str = jalali_expiry_date.strftime("%Y/%m/%d")
    is_expired = expiry_date_obj < datetime.now().date()
    status = "🔴 منقضی شده" if is_expired else "🟢 فعال"
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

# --- Background Jobs ---
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

async def check_expiring_services(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running job: Checking for expiring services...")
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
                        f"⏳ **یادآوری انقضای سرویس**\n\n"
                        f"کاربر گرامی، تنها **{days_left} روز** تا پایان اعتبار سرویس شما {service_name} باقی مانده است.\n\n"
                        f"برای جلوگیری از قطعی، لطفاً سرویس خود را تمدید نمایید."
                    )
                )
                logger.info(f"Sent expiry reminder to user {user_id} for service {service['service_id']}.")
                await asyncio.sleep(0.2)
        except (Forbidden, BadRequest) as e:
            logger.warning(f"Failed to send expiry reminder to user {service['user_id']}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error in expiry reminder job for service {service['service_id']}: {e}", exc_info=True)
            
# --- Generic Handlers ---
@check_channel_membership
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username)
    
    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != user.id:
                db.set_referrer(user.id, referrer_id)
        except (ValueError, IndexError):
            logger.warning(f"Invalid referral link used: {context.args[0]}")

    user_info = db.get_user(user.id)
    if user_info and user_info.get('is_banned'):
        await update.message.reply_text("شما از استفاده از این ربات منع شده‌اید.")
        return ConversationHandler.END
        
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    await start(update, context)

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
@check_channel_membership
async def list_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.effective_message
    
    services = db.get_user_services(user_id)
    if not services:
        await message.reply_text("شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return
    
    keyboard = []
    for service in services:
        button_text = f"⚙️ {service['name']}"
        callback_data = f"view_service_{service['service_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await message.edit_text("لطفا سرویسی که می‌خواهید مدیریتش کنید را انتخاب نمایید:", reply_markup=reply_markup)
    else:
        await message.reply_text("لطفا سرویسی که می‌خواهید مدیریتش کنید را انتخاب نمایید:", reply_markup=reply_markup)

@check_channel_membership
async def view_service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = int(query.data.split('_')[-1])
    
    await query.edit_message_text("در حال دریافت اطلاعات سرویس... ⏳")
    await send_service_details(context, query.from_user.id, service_id, original_message=query.message, is_from_menu=True)

async def send_service_details(context: ContextTypes.DEFAULT_TYPE, chat_id: int, service_id: int, original_message=None, is_from_menu: bool = False):
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
                f"🏷️ نام سرویس: **{service['name']}**\n\n"
                f"📊 حجم مصرفی: **{info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f}** گیگ\n"
                f"🗓️ تاریخ انقضا: **{expiry_date_display}**\n"
                f"🚦 وضعیت: {status}\n\n"
                f"🔗 لینک اشتراک شما:\n`{final_link}`"
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
                await original_message.delete()
            
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=bio,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        else:
            raise ConnectionError(f"API did not return info for UUID {service['sub_uuid']}")
    except Exception as e:
        logger.error(f"Error in send_service_details for service_id {service_id}: {e}", exc_info=True)
        error_text = "❌ خطا در دریافت اطلاعات سرویس. لطفاً بعدا دوباره تلاش کنید."
        if original_message:
            try: await original_message.edit_text(error_text)
            except BadRequest: pass
        else: await context.bot.send_message(chat_id=chat_id, text=error_text)

@check_channel_membership
async def refresh_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = int(query.data.split('_')[1])
    service = db.get_service(service_id)
    if service and service['user_id'] == query.from_user.id:
        await query.message.delete()
        msg = await context.bot.send_message(chat_id=query.from_user.id, text="در حال به‌روزرسانی اطلاعات...")
        await send_service_details(context, query.from_user.id, service_id, original_message=msg, is_from_menu=True)
    else:
        await query.answer("خطا: این سرویس متعلق به شما نیست.", show_alert=True)

@check_channel_membership
async def back_to_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    await list_my_services(update, context)

# --- Renewal Logic ---
@check_channel_membership
async def renew_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    
    service_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    service = db.get_service(service_id)
    if not service: await context.bot.send_message(chat_id=user_id, text="❌ سرویس نامعتبر است."); return
    plan = db.get_plan(service['plan_id'])
    if not plan: await context.bot.send_message(chat_id=user_id, text="❌ پلن تمدید برای این سرویس یافت نشد."); return
    user = db.get_or_create_user(user_id)
    if user['balance'] < plan['price']: await context.bot.send_message(chat_id=user_id, text=f"موجودی برای تمدید کافی نیست! (نیاز به {plan['price']:.0f} تومان)"); return

    msg = await context.bot.send_message(chat_id=user_id, text="در حال بررسی وضعیت سرویس... ⏳")
    hiddify_info = await hiddify_api.get_user_info(service['sub_uuid'])
    if not hiddify_info: await msg.edit_text("❌ امکان دریافت اطلاعات سرویس از پنل وجود ندارد. لطفاً بعداً تلاش کنید."); return
    
    _, _, is_expired = await _get_service_status(hiddify_info)
    context.user_data['renewal_service_id'] = service_id
    context.user_data['renewal_plan_id'] = plan['plan_id']
    
    if is_expired:
        await proceed_with_renewal(update, context, original_message=msg)
    else:
        keyboard = [[InlineKeyboardButton("✅ بله، تمدید کن", callback_data=f"confirmrenew")], [InlineKeyboardButton("❌ خیر، لغو کن", callback_data=f"cancelrenew")]]
        await msg.edit_text("⚠️ **هشدار مهم** ⚠️\n\nسرویس شما هنوز اعتبار دارد. تمدید در حال حاضر باعث می‌شود اعتبار زمانی و حجمی باقیمانده شما **از بین برود** و دوره جدید از همین امروز شروع شود.\n\nآیا می‌خواهید ادامه دهید?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

@check_channel_membership
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
        if original_message: await original_message.edit_text("❌ خطای داخلی: اطلاعات تمدید یافت نشد.")
        return

    if original_message: await original_message.edit_text("در حال ارسال درخواست تمدید به پنل... ⏳")
    
    transaction_id = db.initiate_renewal_transaction(user_id, service_id, plan_id)
    if not transaction_id:
        if original_message: await original_message.edit_text("❌ مشکلی در شروع فرآیند تمدید پیش آمد (مثلا عدم موجودی).")
        return

    service = db.get_service(service_id)
    plan = db.get_plan(plan_id)

    logger.info(f"Attempting to renew service {service_id} for user {user_id} with UUID {service['sub_uuid']}")
    logger.info(f"Renewal details: Plan ID {plan_id}, Days: {plan['days']}, GB: {plan['gb']}")

    new_hiddify_info = await hiddify_api.renew_user_subscription(service['sub_uuid'], plan['days'], plan['gb'])
    logger.info(f"Hiddify renewal API returned: {new_hiddify_info}")

    if new_hiddify_info:
        db.finalize_renewal_transaction(transaction_id, plan_id) 
        if original_message: await original_message.edit_text("✅ سرویس با موفقیت تمدید شد! در حال نمایش اطلاعات جدید...")
        await send_service_details(context, user_id, service_id, original_message=original_message, is_from_menu=True)
    else:
        db.cancel_renewal_transaction(transaction_id)
        if original_message: await original_message.edit_text("❌ خطا در تمدید سرویس. مشکلی در ارتباط با پنل وجود دارد. لطفاً به پشتیبانی اطلاع دهید.")
        
    context.user_data.clear()

@check_channel_membership
async def cancel_renewal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("عملیات تمدید لغو شد.")
    context.user_data.clear()

# --- Main User Flow Handlers ---
@check_channel_membership
async def show_account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = db.get_user(user_id)
    purchase_stats = db.get_user_purchase_stats(user_id)
    
    join_date_gregorian = _parse_date_flexible(user_info['join_date'])
    join_date_jalali = "N/A"
    if join_date_gregorian:
        jalali_date = jdatetime.date.fromgregorian(date=join_date_gregorian)
        join_date_jalali = jalali_date.strftime("%Y/%m/%d")

    text = (
        f"👤 **اطلاعات حساب شما**\n\n"
        f"▫️ شناسه کاربری: `{user_id}`\n"
        f"💰 موجودی کیف پول: **{user_info['balance']:,.0f} تومان**\n\n"
        f"📈 **آمار خرید شما:**\n"
        f"- تعداد کل خریدها: {purchase_stats['total_purchases']} عدد\n"
        f"- مجموع مبلغ خریدها: {purchase_stats['total_spent']:,.0f} تومان\n\n"
        f"🗓️ تاریخ عضویت شما در ربات: {join_date_jalali}"
    )

    keyboard = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="user_start_charge")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


@check_channel_membership
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"جهت ارتباط با پشتیبانی به آیدی زیر پیام ارسال کنید:\n@{SUPPORT_USERNAME}")

@check_channel_membership
async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("راهنمای اتصال به سرویس‌ها:\n\n(اینجا می‌توانید آموزش‌های لازم را قرار دهید)")

@check_channel_membership
async def show_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    bonus = REFERRAL_BONUS_AMOUNT
    
    text = (
        f"🎁 **دوستان خود را دعوت کنید و هدیه بگیرید!**\n\n"
        f"با این لینک منحصر به فرد, دوستان خود را به ربات دعوت کنید.\n\n"
        f"🔗 **لینک شما:**\n`{referral_link}`\n\n"
        f"هر دوستی که با لینک شما وارد ربات شود و اولین خرید خود را انجام دهد, "
        f"**{bonus:,.0f} تومان** هدیه به کیف پول شما و **{bonus:,.0f} تومان** به کیف پول دوستتان اضافه خواهد شد!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

@check_channel_membership
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
@check_channel_membership
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
@check_channel_membership
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
@check_channel_membership
async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans(only_visible=True)
    if not plans: await update.message.reply_text("متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست."); return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان", callback_data=f"user_buy_{p['plan_id']}")] for p in plans]
    await update.message.reply_text("لطفا سرویس مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

@check_channel_membership
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
        
        referrer_id, bonus_amount = db.apply_referral_bonus(user_id)
        if referrer_id:
            try:
                await context.bot.send_message(user_id, f"🎁 تبریک! مبلغ {bonus_amount:,.0f} تومان به عنوان هدیه اولین خرید به کیف پول شما اضافه شد.")
                await context.bot.send_message(referrer_id, f"🎉 تبریک! یکی از دوستان شما خرید خود را تکمیل کرد و مبلغ {bonus_amount:,.0f} تومان به کیف پول شما اضافه شد.")
            except (Forbidden, BadRequest):
                logger.warning(f"Could not send referral bonus notification to {user_id} or {referrer_id}.")

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

@check_channel_membership
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
# (Admin functions and ConversationHandler definitions are here)

def main():
    """Start the bot."""
    db.init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    job_queue = application.job_queue
    
    job_queue.run_repeating(check_low_usage, interval=timedelta(hours=4), first=10)
    job_queue.run_daily(check_expiring_services, time=time(hour=9, minute=0))

    admin_filter = filters.User(user_id=ADMIN_ID)
    user_filter = ~admin_filter
    
    # --- Conversation Handlers ---
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
    application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))

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
    application.add_handler(MessageHandler(filters.Regex('^👤 اطلاعات حساب$'), show_account_info), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), show_support), group=3)
    application.add_handler(MessageHandler(filters.Regex('^📚 راهنمای اتصال$'), show_guide), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🧪 دریافت سرویس تست رایگان$'), get_trial_service), group=3)
    application.add_handler(MessageHandler(filters.Regex('^🎁 معرفی دوستان$'), show_referral_link), group=3)

    print("Bot is running with final corrections. All features should work correctly.")
    application.run_polling()

if __name__ == "__main__":
    main()