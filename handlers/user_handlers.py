# -*- coding: utf-8 -*-
import logging
import io
import random
import qrcode
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from telegram.constants import ParseMode, ChatAction

import database as db
import hiddify_api
import keyboards
from utils import get_service_status_and_expiry, parse_date_flexible
from handlers.decorators import check_channel_membership
from config import (
    TRIAL_DAYS, TRIAL_GB, TRIAL_ENABLED, SUPPORT_USERNAME, REFERRAL_BONUS_AMOUNT,
    SUB_DOMAINS, PANEL_DOMAIN, SUB_PATH, ADMIN_PATH
)
from constants import (
    CMD_CANCEL, CMD_SKIP, GET_CUSTOM_NAME, REDEEM_GIFT, CHARGE_AMOUNT, CHARGE_RECEIPT
)

logger = logging.getLogger(__name__)

# --- Reusable Helper Functions ---

async def send_service_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int):
    """
    A helper function to send or edit the service management menu.
    This avoids code duplication and removes the need for mock objects.
    """
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("در حال دریافت اطلاعات سرویس... ⏳")
        message_to_use = query.message
    else:
        message_to_use = await update.message.reply_text("در حال دریافت اطلاعات سرویس... ⏳")

    service = await db.get_service(service_id)
    if not service:
        await message_to_use.edit_text("❌ سرویس مورد نظر یافت نشد.")
        return

    info = await hiddify_api.get_user_info(service['sub_uuid'])
    if not info:
        await message_to_use.edit_text("❌ خطا در ارتباط با پنل. لطفاً بعداً تلاش کنید.")
        return

    status, expiry_date_display, _ = await get_service_status_and_expiry(info)

    caption = (
        f"🏷️ **مدیریت سرویس: {service['name']}**\n\n"
        f"📊 حجم مصرفی: **{info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f}** گیگ\n"
        f"🗓️ تاریخ انقضا: **{expiry_date_display}**\n"
        f"🚦 وضعیت: {status}\n\n"
        "لطفاً عملیات مورد نظر خود را انتخاب کنید:"
    )

    keyboard = await keyboards.get_service_management_keyboard(service['service_id'], service['sub_uuid'], service['plan_id'])
    await message_to_use.edit_text(caption, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


# --- Main Commands & Message Handlers ---

@check_channel_membership
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.get_or_create_user(user.id, user.username)

    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != user.id:
                await db.set_referrer(user.id, referrer_id)
                logger.info(f"User {user.id} was referred by {referrer_id}")
        except (ValueError, IndexError):
            logger.warning(f"Invalid referral link used by user {user.id}: {context.args[0]}")

    user_info = await db.get_user(user.id)
    if user_info and user_info.get('is_banned'):
        await update.message.reply_text("شما از استفاده از این ربات منع شده‌اید.")
        return

    await update.message.reply_text(
        "👋 به ربات فروش VPN خوش آمدید!",
        reply_markup=await keyboards.get_main_menu_keyboard(user.id)
    )

@check_channel_membership
async def show_account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    user_info = await db.get_user(user_id)
    purchase_stats = await db.get_user_purchase_stats(user_id)

    join_date_gregorian = parse_date_flexible(user_info['join_date'])
    join_date_jalali = "N/A"
    if join_date_gregorian:
        import jdatetime
        jalali_date = jdatetime.date.fromgregorian(date=join_date_gregorian)
        join_date_jalali = jalali_date.strftime("%Y/%m/%d")

    text = (
        f"👤 **اطلاعات حساب شما**\n\n"
        f"▫️ شناسه کاربری: `{user_id}`\n"
        f"💰 موجودی کیف پول: **{user_info['balance']:,.0f} تومان**\n\n"
        f"📈 **آمار خرید شما:**\n"
        f"- تعداد کل خریدها: {purchase_stats['total_purchases']} عدد\n"
        f"- مجموع مبلغ خریدها: {purchase_stats.get('total_spent', 0) or 0:,.0f} تومان\n\n"
        f"🗓️ تاریخ عضویت شما در ربات: {join_date_jalali}"
    )

    keyboard = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="user_start_charge")]]
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

@check_channel_membership
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"جهت ارتباط با پشتیبانی به آیدی زیر پیام ارسال کنید:\n@{SUPPORT_USERNAME}")

@check_channel_membership
async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guide_text = await db.get_setting('connection_guide_text')
    if not guide_text:
        guide_text = "راهنمای اتصال هنوز توسط ادمین تنظیم نشده است."
    await update.message.reply_text(guide_text, parse_mode=ParseMode.MARKDOWN)

@check_channel_membership
async def show_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    bonus_str = await db.get_setting('referral_bonus_amount') or REFERRAL_BONUS_AMOUNT
    bonus = float(bonus_str)

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
    user_info = await db.get_or_create_user(user_id, update.effective_user.username)
    if not TRIAL_ENABLED:
        await update.message.reply_text("در حال حاضر سرویس تست فعال نمی‌باشد.")
        return
    if user_info.get('has_used_trial'):
        await update.message.reply_text("شما قبلاً از سرویس تست رایگان استفاده کرده‌اید.")
        return
    
    msg_loading = await update.message.reply_text("در حال ساخت سرویس تست شما... ⏳")
    result = await hiddify_api.create_hiddify_user(TRIAL_DAYS, TRIAL_GB, user_id, custom_name="سرویس تست")
    
    if result and result.get('uuid'):
        await db.set_user_trial_used(user_id)
        service = await db.add_active_service(user_id, "سرویس تست", result['uuid'], result['full_link'], 0) # plan_id 0 for trial
        
        # Directly call the helper to show the menu
        await msg_loading.delete()
        # To reuse the 'update' object correctly for the helper function
        fake_update = Update(update.update_id, message=update.message)
        await send_service_management_menu(fake_update, context, service['service_id'])
    else: 
        await msg_loading.edit_text("❌ متاسفانه در ساخت سرویس تست مشکلی پیش آمد. لطفا بعداً تلاش کنید.")

async def user_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic cancel handler for user conversations."""
    context.user_data.clear()
    await update.message.reply_text(
        "عملیات لغو شد.",
        reply_markup=await keyboards.get_main_menu_keyboard(update.effective_user.id)
    )
    return ConversationHandler.END

# --- Buy Service Flow ---

@check_channel_membership
async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = await db.list_plans(only_visible=True)
    if not plans:
        await update.message.reply_text("متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست.")
        return
    
    keyboard = [[InlineKeyboardButton(
        f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان",
        callback_data=f"user_buy_{p['plan_id']}"
    )] for p in plans]
    
    await update.message.reply_text("لطفا سرویس مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    
    # Check balance before starting
    user = await db.get_user(user_id)
    plan = await db.get_plan(plan_id)
    if not user or not plan or user['balance'] < plan['price']:
        await query.edit_message_text(f"موجودی شما کافی نیست!\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان")
        return ConversationHandler.END

    context.user_data['plan_to_buy_id'] = plan_id
    await query.edit_message_text(
        f"✅ پلن شما انتخاب شد.\n\n"
        f"لطفاً یک نام دلخواه برای این سرویس وارد کنید (مثلاً: گوشی شخصی).\n"
        f"برای استفاده از نام پیش‌فرض، دستور {CMD_SKIP} را ارسال کنید.",
        reply_markup=None
    )
    return GET_CUSTOM_NAME

async def get_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_name = update.message.text
    if len(custom_name) > 50:
        await update.message.reply_text("نام وارد شده بیش از حد طولانی است. لطفاً نام کوتاه‌تری انتخاب کنید.")
        return GET_CUSTOM_NAME
    
    context.user_data['custom_name'] = custom_name
    await create_service_after_name(update, context)
    return ConversationHandler.END

async def skip_custom_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['custom_name'] = ""
    await create_service_after_name(update, context)
    return ConversationHandler.END

async def create_service_after_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan_id = context.user_data.get('plan_to_buy_id')
    custom_name_input = context.user_data.get('custom_name', "")

    if not plan_id:
        await update.message.reply_text(
            "خطای داخلی رخ داده است. لطفا مجددا تلاش کنید.",
            reply_markup=await keyboards.get_main_menu_keyboard(user_id)
        )
        context.user_data.clear()
        return

    # Start financial transaction first
    transaction_id = await db.initiate_purchase_transaction(user_id, plan_id)
    if not transaction_id:
        await update.message.reply_text(
            "خطا در پردازش مالی (مانند عدم موجودی). لطفاً دوباره تلاش کنید.",
            reply_markup=await keyboards.get_main_menu_keyboard(user_id)
        )
        context.user_data.clear()
        return
        
    plan = await db.get_plan(plan_id)
    custom_name = custom_name_input if custom_name_input else f"سرویس {plan['gb']} گیگ"

    msg_loading = await update.message.reply_text(
        "در حال ساخت سرویس شما... ⏳",
        reply_markup=await keyboards.get_main_menu_keyboard(user_id)
    )

    result = await hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id, custom_name=custom_name)

    if result and result.get('uuid'):
        service = await db.finalize_purchase_transaction(transaction_id, result['uuid'], result['full_link'], custom_name)
        
        referrer_id, bonus_amount = await db.apply_referral_bonus(user_id)
        if referrer_id:
            try:
                await context.bot.send_message(user_id, f"🎁 تبریک! مبلغ {bonus_amount:,.0f} تومان به عنوان هدیه اولین خرید به کیف پول شما اضافه شد.")
                await context.bot.send_message(referrer_id, f"🎉 تبریک! یکی از دوستان شما خرید خود را تکمیل کرد و مبلغ {bonus_amount:,.0f} تومان به کیف پول شما اضافه شد.")
            except (Forbidden, BadRequest):
                logger.warning(f"Could not send referral bonus notification to {user_id} or {referrer_id}.")

        await msg_loading.delete()
        # To reuse the 'update' object correctly for the helper function
        fake_update = Update(update.update_id, message=update.message)
        await send_service_management_menu(fake_update, context, service['service_id'])
    else:
        await db.cancel_purchase_transaction(transaction_id)
        await msg_loading.edit_text("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. هزینه به حساب شما بازگشت. لطفا به پشتیبانی اطلاع دهید.")

    context.user_data.clear()


# --- Gift Code Conversation ---
@check_channel_membership
async def gift_code_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎁 لطفا کد هدیه خود را وارد کنید:",
        reply_markup=keyboards.get_cancel_keyboard()
    )
    return REDEEM_GIFT

async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    user_id = update.effective_user.id
    amount = await db.use_gift_code(code, user_id)
    
    if amount is not None:
        await update.message.reply_text(
            f"✅ تبریک! مبلغ {amount:,.0f} تومان به کیف پول شما اضافه شد.",
            reply_markup=await keyboards.get_main_menu_keyboard(user_id)
        )
    else:
        await update.message.reply_text(
            "❌ کد هدیه نامعتبر، استفاده شده یا منقضی شده است.",
            reply_markup=await keyboards.get_main_menu_keyboard(user_id)
        )
    return ConversationHandler.END


# --- Charge Account Conversation ---
async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "لطفاً مبلغی که قصد واریز آن را دارید به تومان وارد کنید (فقط عدد):",
        reply_markup=keyboards.get_cancel_keyboard()
    )
    return CHARGE_AMOUNT

async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount < 1000:
            await update.message.reply_text("مبلغ باید حداقل 1,000 تومان باشد.")
            return CHARGE_AMOUNT
            
        context.user_data['charge_amount'] = amount
        card_number = await db.get_setting('card_number') or "[تنظیم نشده]"
        card_holder = await db.get_setting('card_holder') or "[تنظیم نشده]"
        
        text = (f"لطفاً مبلغ **{amount:,} تومان** را به شماره کارت زیر واریز نمایید:\n\n"
                f"`{card_number}`\n"
                f"به نام: {card_holder}\n\n"
                "سپس از رسید واریزی خود عکس گرفته و آن را ارسال کنید.")
                
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboards.get_cancel_keyboard()
        )
        return CHARGE_RECEIPT
    except (ValueError, TypeError):
        await update.message.reply_text("لطفا یک عدد صحیح به تومان وارد کنید.")
        return CHARGE_AMOUNT

async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    user = update.effective_user
    amount = context.user_data.get('charge_amount')
    
    if not amount:
        await update.message.reply_text("خطا! مبلغ شارژ مشخص نیست. لطفا از ابتدا شروع کنید.", reply_markup=await keyboards.get_main_menu_keyboard(user.id))
        return ConversationHandler.END
        
    receipt_photo = update.message.photo[-1]
    
    caption = (f"🔔 درخواست شارژ جدید\n\n"
               f"کاربر: {user.full_name} (@{user.username or 'N/A'})\n"
               f"آیدی عددی: `{user.id}`\n"
               f"مبلغ درخواستی: **{amount:,} تومان**")
               
    keyboard = [[
        InlineKeyboardButton("✅ تایید شارژ", callback_data=f"admin_confirm_charge_{user.id}_{int(amount)}"),
        InlineKeyboardButton("❌ رد درخواست", callback_data=f"admin_reject_charge_{user.id}")
    ]]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=receipt_photo.file_id,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    
    await update.message.reply_text(
        "✅ رسید شما برای ادمین ارسال شد. لطفاً تا زمان بررسی منتظر بمانید.",
        reply_markup=await keyboards.get_main_menu_keyboard(user.id)
    )
    context.user_data.clear()
    return ConversationHandler.END


# --- Conversation Handler Definitions ---
buy_service_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(buy_start, pattern='^user_buy_')],
    states={
        GET_CUSTOM_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_custom_name),
            CommandHandler('skip', skip_custom_name)
        ]
    },
    fallbacks=[CommandHandler(CMD_CANCEL, user_generic_cancel)],
    per_user=True, per_chat=True
)

gift_code_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex('^🎁 کد هدیه$'), gift_code_entry)],
    states={
        REDEEM_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_gift_code)]
    },
    fallbacks=[CommandHandler(CMD_CANCEL, user_generic_cancel)],
    per_user=True, per_chat=True
)

charge_account_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(charge_start, pattern='^user_start_charge$')],
    states={
        CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_amount_received)],
        CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_receipt_received)]
    },
    fallbacks=[CommandHandler(CMD_CANCEL, user_generic_cancel)],
    per_user=True, per_chat=True
)
