# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.constants import ParseMode

import database as db
from bot.keyboards import get_main_menu_keyboard, get_admin_menu_keyboard
from bot.constants import ADMIN_MENU
from config import SUPPORT_USERNAME, REFERRAL_BONUS_AMOUNT

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)

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
        if update.message:
            await update.message.reply_text("شما از استفاده از این ربات منع شده‌اید.")
        elif update.callback_query:
            await update.callback_query.answer("شما از استفاده از این ربات منع شده‌اید.", show_alert=True)
        return ConversationHandler.END

    text = "👋 به ربات خوش آمدید!"
    reply_markup = get_main_menu_keyboard(user.id)

    if update.callback_query:
        q = update.callback_query
        await q.answer("عضویت شما تایید شد. خوش آمدید!")
        try:
            await q.message.delete()
        except Exception:
            pass
        await q.from_user.send_message(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

    return ConversationHandler.END


async def user_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END

async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ConversationHandler.END

async def show_account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    services_count = len(db.get_user_services(user_id))
    referral_count = db.get_user_referral_count(user_id)
    join_date = user.get('join_date', 'N/A')

    join_date_jalali = "N/A"
    if jdatetime and join_date != "N/A":
        try:
            dt = datetime.strptime(join_date.split(' ')[0], '%Y-%m-%d')
            join_date_jalali = jdatetime.date.fromgregorian(date=dt).strftime('%Y/%m/%d')
        except Exception:
            pass

    text = (
        f"👤 **اطلاعات حساب شما**\n\n"
        f"▫️ شناسه عددی: `{user_id}`\n"
        f"▫️ موجودی کیف پول: **{user['balance']:.0f} تومان**\n"
        f"▫️ تعداد سرویس‌های فعال: **{services_count}**\n"
        f"▫️ تعداد دوستان دعوت‌شده: **{referral_count}**\n"
        f"▫️ تاریخ عضویت: **{join_date_jalali}**"
    )

    keyboard = [
        [InlineKeyboardButton("💳 شارژ حساب", callback_data="user_start_charge")],
        [InlineKeyboardButton("📜 سوابق خرید", callback_data="acc_purchase_history"),
         InlineKeyboardButton("💸 سوابق شارژ", callback_data="acc_charge_history")],
        [InlineKeyboardButton("🤝 انتقال موجودی", callback_data="acc_transfer_start"),
         InlineKeyboardButton("🎁 ساخت کد هدیه", callback_data="acc_gift_from_balance_start")],
        [InlineKeyboardButton("📚 منوی راهنما", callback_data="guide_back_to_menu")],
    ]

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_purchase_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    history = db.get_user_sales_history(q.from_user.id)
    if not history:
        await q.answer("شما تاکنون خریدی نداشته‌اید.", show_alert=True)
        return

    # حذف پیام قبلی (پنل اطلاعات حساب)
    try:
        await q.message.delete()
    except Exception:
        pass

    header = "🛍️ **سوابق خرید شما:**\n\n"
    
    # ارسال سوابق در چند پیام
    message_parts = [header]
    current_part = ""
    for sale in history:
        try:
            sale_date = datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S').strftime('%Y/%m/%d')
        except (ValueError, TypeError):
            sale_date = sale['sale_date']

        line = f"🔹 {sale['plan_name'] or 'پلن حذف شده'} | {sale['price']:.0f} تومان | {sale_date}\n"
        
        if len(current_part) + len(line) > 4000:
            message_parts.append(current_part)
            current_part = ""
        current_part += line
    
    if current_part:
        message_parts.append(current_part)

    for part in message_parts:
        await q.from_user.send_message(part, parse_mode="Markdown")
    
    # ارسال مجدد پنل اطلاعات حساب با دکمه بازگشت
    await show_account_info(update, context)


async def show_charge_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    history = db.get_user_charge_history(q.from_user.id)
    if not history:
        await q.answer("شما تاکنون سابقه شارژ موفقی نداشته‌اید.", show_alert=True)
        return
    
    try:
        await q.message.delete()
    except Exception:
        pass
    
    header = "💸 **سوابق شارژ موفق شما:**\n\n"
    
    message_parts = [header]
    current_part = ""
    for ch in history:
        try:
            charge_date = datetime.strptime(ch['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%Y/%m/%d')
        except (ValueError, TypeError):
            charge_date = ch['created_at']
            
        line = f"🔹 {ch['amount']:.0f} تومان | {charge_date}\n"
        if len(current_part) + len(line) > 4000:
            message_parts.append(current_part)
            current_part = ""
        current_part += line
        
    if current_part:
        message_parts.append(current_part)
        
    for part in message_parts:
        await q.from_user.send_message(part, parse_mode="Markdown")
        
    await show_account_info(update, context)


async def show_charging_guide_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    guide = _get_payment_info_text()
    kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data="acc_back_to_main")]]
    await q.edit_message_text(guide, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 راهنمای اتصال", callback_data="guide_connection")],
        [InlineKeyboardButton("💳 راهنمای شارژ حساب", callback_data="guide_charging")],
        [InlineKeyboardButton("🛍️ راهنمای خرید از ربات", callback_data="guide_buying")],
    ]
    await update.message.reply_text("📚 لطفاً موضوع راهنمای مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_guide_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    guide_key = q.data

    guide_text = db.get_setting(guide_key)
    if not guide_text:
        guide_text = "متاسفانه هنوز راهنمایی برای این بخش ثبت نشده است."

    kb = [[InlineKeyboardButton("🔙 بازگشت به منوی راهنما", callback_data="guide_back_to_menu")]]

    if q.message and q.message.photo:
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=q.from_user.id,
            text=guide_text,
            reply_markup=InlineKeyboardMarkup(kb),
            disable_web_page_preview=True
        )
        return

    try:
        await q.edit_message_text(
            guide_text,
            reply_markup=InlineKeyboardMarkup(kb),
            disable_web_page_preview=True
        )
    except BadRequest as e:
        if "message is not modified" in str(e):
            return
        await context.bot.send_message(
            chat_id=q.from_user.id,
            text=guide_text,
            reply_markup=InlineKeyboardMarkup(kb),
            disable_web_page_preview=True
        )

async def back_to_guide_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    try:
        await q.message.delete()
    except Exception:
        pass

    keyboard = [
        [InlineKeyboardButton("📱 راهنمای اتصال", callback_data="guide_connection")],
        [InlineKeyboardButton("💳 راهنمای شارژ حساب", callback_data="guide_charging")],
        [InlineKeyboardButton("🛍️ راهنمای خرید از ربات", callback_data="guide_buying")],
    ]
    await q.from_user.send_message("📚 لطفاً موضوع راهنمای مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

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
        f"🎁 دوستان خود را دعوت کنید و هدیه بگیرید!\n\n"
        f"با لینک اختصاصی زیر دوستان خود را دعوت کنید:\n"
        f"`{referral_link}`\n\n"
        f"با اولین خرید دوست شما، مبلغ **{bonus:,.0f} تومان** به کیف پول شما و **{bonus:,.0f} تومان** به کیف پول دوستتان اضافه می‌شود."
    )
    await update.message.reply_text(text, parse_mode="Markdown")