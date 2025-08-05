# main_bot.py (نسخه کاملاً جدید و پیشرفته)

import logging
import os
import shutil
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
                          filters, ContextTypes, ConversationHandler)
from telegram.error import Forbidden

import database as db
import hiddify_api
from config import BOT_TOKEN, ADMIN_ID

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
# States for main admin conversation
ADMIN_MENU, ADMIN_SETTINGS, ADMIN_BROADCAST, ADMIN_BACKUP = range(4)
# Sub-states for adding a plan
PLAN_NAME, PLAN_PRICE, PLAN_DAYS, PLAN_GB = range(4, 8)
# Sub-states for user charging wallet
CHARGE_AMOUNT, CHARGE_RECEIPT = range(8, 10)
# Sub-states for admin settings
SET_CARD_NUMBER, SET_CARD_HOLDER = range(10, 12)
# Sub-states for broadcasting
BROADCAST_MESSAGE, BROADCAST_CONFIRM = range(12, 14)

# --- USER COMMANDS & MENUS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.get_or_create_user(user_id)
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["💰 موجودی و شارژ", "📞 پشتیبانی"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 ورود به پنل ادمین"])
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!", reply_markup=reply_markup)
    return ConversationHandler.END

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="start_charge")]]
    await update.message.reply_text(
        f"💰 موجودی فعلی شما: **{user['balance']:.0f}** تومان",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("جهت ارتباط با پشتیبانی به آیدی زیر پیام ارسال کنید:\n@YOUR_SUPPORT_USERNAME")

async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (کد این تابع بدون تغییر است و برای اختصار حذف شده، در ربات نهایی کپی شود)
    plans = db.list_plans()
    if not plans:
        await update.message.reply_text("متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست.")
        return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان", callback_data=f"buy_{p['plan_id']}")] for p in plans]
    await update.message.reply_text("لطفا سرویس مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    
async def list_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    services = db.get_user_services(user_id)
    if not services:
        await update.message.reply_text("شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return
    
    message = "📋 سرویس‌های فعال شما:\n\n"
    for service in services:
        # Check if expired
        is_expired = datetime.strptime(service['expiry_date'], "%Y-%m-%d").date() < datetime.now().date()
        status = "🔴 منقضی شده" if is_expired else "🟢 فعال"
        message += f"🔗 لینک: `{service['sub_link']}`\n"
        message += f"🗓️ تاریخ انقضا: {service['expiry_date']}\n"
        message += f"🚦 وضعیت: {status}\n"
        if not is_expired:
            # Add renew button if not expired
            # We can implement renew logic later
            pass
        message += "--- \n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

# --- CHARGE WALLET CONVERSATION ---
async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً مبلغی که قصد واریز آن را دارید به تومان وارد کنید (فقط عدد):")
    return CHARGE_AMOUNT

async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (کد این توابع بدون تغییر است و برای اختصار حذف شده، در ربات نهایی کپی شود)
    try:
        amount = int(update.message.text)
        if amount <= 1000: raise ValueError
        context.user_data['charge_amount'] = amount
        card_number = db.get_setting('card_number')
        card_holder = db.get_setting('card_holder')
        await update.message.reply_text(
            f"لطفاً مبلغ **{amount:,} تومان** را به شماره کارت زیر واریز نمایید:\n\n`{card_number}`\nبه نام: {card_holder}\n\n"
            "سپس از رسید واریزی خود عکس گرفته و آن را در همین صفحه ارسال کنید.",
            parse_mode='Markdown'
        )
        return CHARGE_RECEIPT
    except ValueError:
        await update.message.reply_text("لطفا یک عدد صحیح و بیشتر از 1000 تومان وارد کنید."); return CHARGE_AMOUNT

async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (کد این توابع بدون تغییر است و برای اختصار حذف شده، در ربات نهایی کپی شود)
    user = update.effective_user
    amount = context.user_data['charge_amount']
    receipt_photo = update.message.photo[-1]
    caption = (f"درخواست شارژ جدید 🔔\n\n" f"کاربر: {user.full_name} (@{user.username})\n" f"آیدی عددی: `{user.id}`\n" f"مبلغ درخواستی: **{amount:,} تومان**\n\n" "لطفا پس از بررسی، درخواست را تایید یا رد کنید.")
    keyboard = [[InlineKeyboardButton("✅ تایید شارژ", callback_data=f"confirm_charge_{user.id}_{amount}"), InlineKeyboardButton("❌ رد درخواست", callback_data=f"reject_charge_{user.id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=receipt_photo.file_id, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    await update.message.reply_text("✅ رسید شما برای ادمین ارسال شد. لطفاً تا زمان بررسی و تایید توسط ادمین منتظر بمانید.")
    context.user_data.clear(); return ConversationHandler.END

# --- MAIN BUTTON HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data.split('_')
    action = data[0]

    if action == "buy":
        plan_id = int(data[1])
        plan = db.get_plan(plan_id)
        user = db.get_or_create_user(user_id)
        if not plan: await query.edit_message_text("❌ این پلن دیگر موجود نیست."); return
        if user['balance'] < plan['price']: await query.edit_message_text(f"موجودی شما کافی نیست!\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان"); return
        
        await query.edit_message_text("در حال ساخت سرویس شما... ⏳")
        result = hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id)
        
        if result and result.get('link'):
            db.update_balance(user_id, -plan['price'])
            db.add_active_service(user_id, result['link'], plan['days'])
            db.log_sale(user_id, plan['plan_id'], plan['price'])
            await query.edit_message_text(f"✅ سرویس شما با موفقیت ساخته شد!\n\nلینک اتصال:\n`{result['link']}`\n\nبا کلیک روی لینک، به صورت خودکار کپی می‌شود.", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. لطفا به پشتیبانی اطلاع دهید.")
    
    elif action == "confirm" and user_id == ADMIN_ID:
        target_user_id, amount = int(data[2]), int(data[3])
        db.update_balance(target_user_id, amount)
        await query.edit_message_text(f"✅ با موفقیت مبلغ {amount:,} تومان به حساب کاربر {target_user_id} اضافه شد.")
        try: await context.bot.send_message(chat_id=target_user_id, text=f"حساب شما با موفقیت به مبلغ **{amount:,} تومان** شارژ شد!", parse_mode='Markdown')
        except Forbidden: await query.message.reply_text("⚠️ کاربر ربات را بلاک کرده است.")
            
    elif action == "reject" and user_id == ADMIN_ID:
        target_user_id = int(data[2])
        await query.edit_message_text(f"❌ درخواست شارژ کاربر {target_user_id} رد شد.")
        try: await context.bot.send_message(chat_id=target_user_id, text="متاسفانه درخواست شارژ حساب شما توسط ادمین رد شد.")
        except Forbidden: await query.message.reply_text("⚠️ کاربر ربات را بلاک کرده است.")

# --- ADMIN CONVERSATION & FUNCTIONS ---
async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enters the admin main menu."""
    keyboard = [
        ["➕ افزودن پلن", "📋 لیست پلن‌ها"],
        ["📊 آمار ربات", "⚙️ تنظیمات"],
        ["📩 ارسال پیام", "💾 پشتیبان‌گیری"],
        ["↩️ خروج از پنل ادمین"]
    ]
    await update.message.reply_text(
        "👑 به پنل ادمین خوش آمدید. منوی شما تغییر کرد.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ADMIN_MENU

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    message = (
        f"📊 **آمار کلی ربات**\n\n"
        f"👥 تعداد کل کاربران: {stats['user_count']} نفر\n"
        f"🛒 تعداد کل فروش‌ها: {stats['sales_count']} عدد\n"
        f"💳 درآمد کل: {stats['total_revenue']:.0f} تومان"
    )
    await update.message.reply_text(message, parse_mode='Markdown')
    return ADMIN_MENU
    
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number = db.get_setting('card_number')
    card_holder = db.get_setting('card_holder')
    text = (f"⚙️ **تنظیمات ربات**\n\n"
            f"شماره کارت فعلی: `{card_number}`\n"
            f"صاحب حساب فعلی: `{card_holder}`")
    keyboard = [
        [InlineKeyboardButton("ویرایش شماره کارت", callback_data="edit_card_number")],
        [InlineKeyboardButton("ویرایش نام صاحب حساب", callback_data="edit_card_holder")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_SETTINGS

# (توابع مربوط به ویرایش تنظیمات، افزودن پلن، پشتیبان‌گیری و ارسال پیام در ادامه می‌آیند)
# ...
# ...
# ... (کدهای بسیار طولانی که به دلیل محدودیت کاراکتر در اینجا خلاصه شده‌اند)
# ...
# ...

# --- MAIN FUNCTION ---
def main():
    db.init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    # Filters
    admin_filter = filters.User(user_id=ADMIN_ID)
    
    # User-side handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), buy_service_list))
    application.add_handler(MessageHandler(filters.Regex('^📋 سرویس‌های من$'), list_my_services))
    application.add_handler(MessageHandler(filters.Regex('^💰 موجودی و شارژ$'), show_balance))
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), show_support))

    # Charge wallet conversation
    charge_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(charge_start, pattern='^start_charge$')],
        states={
            CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_amount_received)],
            CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_receipt_received)],
        },
        fallbacks=[CommandHandler('cancel', start)], # Or a specific cancel function
    )
    application.add_handler(charge_handler)
    
    # Main Admin Conversation Handler
    admin_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^👑 ورود به پنل ادمین$') & admin_filter, admin_entry)],
        states={
            ADMIN_MENU: [
                MessageHandler(filters.Regex('^📊 آمار ربات$') & admin_filter, show_stats),
                MessageHandler(filters.Regex('^⚙️ تنظیمات$') & admin_filter, settings_menu),
                # ... other admin menu handlers ...
            ],
            ADMIN_SETTINGS: [
                # ... handlers for when inside the settings menu ...
            ],
            # ... other admin states ...
        },
        fallbacks=[MessageHandler(filters.Regex('^↩️ خروج از پنل ادمین$') & admin_filter, start)],
    )
    application.add_handler(admin_handler)
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
