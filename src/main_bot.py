# HiddifyBotProject/src/main_bot.py

import logging
import os
import shutil
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
                          filters, ContextTypes, ConversationHandler, ApplicationBuilder)
from telegram.error import Forbidden, BadRequest

import database as db
import hiddify_api
from config import BOT_TOKEN, ADMIN_ID

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(
    ADMIN_MENU, PLAN_MENU, SETTINGS_MENU, BROADCAST_MENU, BACKUP_MENU, GIFT_MENU,
    PLAN_NAME, PLAN_PRICE, PLAN_DAYS, PLAN_GB,
    SET_CARD_NUMBER, SET_CARD_HOLDER,
    BROADCAST_MESSAGE, BROADCAST_CONFIRM,
    CHARGE_AMOUNT, CHARGE_RECEIPT,
    GIFT_AMOUNT, GIFT_COUNT,
    REDEEM_GIFT
) = range(19)

# --- USER COMMANDS & MENUS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.get_or_create_user(user_id)
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["💰 موجودی و شارژ", "🎁 کد هدیه"],
        ["📞 پشتیبانی", " راهنمای اتصال 📚"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 ورود به پنل ادمین"])
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!", reply_markup=reply_markup)
    return ConversationHandler.END

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="start_charge")]]
    await update.message.reply_text(f"💰 موجودی فعلی شما: **{user['balance']:.0f}** تومان", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("جهت ارتباط با پشتیبانی به آیدی زیر پیام ارسال کنید:\n@YOUR_SUPPORT_USERNAME")

async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("راهنمای اتصال به سرویس‌ها:\n\n(اینجا می‌توانید آموزش‌های لازم برای پلتفرم‌های مختلف را قرار دهید)")

async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text("شما در حال حاضر هیچ سرویس فعالی ندارید."); return
    
    await update.message.reply_text("در حال دریافت اطلاعات سرویس‌های شما...")
    for service in services:
        info = hiddify_api.get_user_info(service['sub_uuid'])
        if info:
            is_expired = datetime.strptime(info['expiry_date'], "%Y-%m-%d").date() < datetime.now().date()
            status = "🔴 منقضی شده" if is_expired else "🟢 فعال"
            message = (f"🔗 لینک: `{service['sub_link']}`\n"
                       f"🗓️ تاریخ انقضا: {info['expiry_date']}\n"
                       f"📊 حجم مصرفی: {info['current_usage_GB']:.2f} / {info['usage_limit_GB']:.0f} گیگ\n"
                       f"🚦 وضعیت: {status}")
            keyboard = [[InlineKeyboardButton("🔄 تمدید سرویس", callback_data=f"renew_{service['service_id']}_{info['usage_limit_GB']}_{info['package_days']}")]]
            await update.message.reply_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(f"خطا در دریافت اطلاعات برای لینک:\n`{service['sub_link']}`", parse_mode='Markdown')

async def gift_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 لطفا کد هدیه خود را وارد کنید:")
    return REDEEM_GIFT
async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.upper()
    user_id = update.effective_user.id
    amount = db.use_gift_code(code, user_id)
    if amount:
        await update.message.reply_text(f"✅ تبریک! مبلغ {amount:.0f} تومان به کیف پول شما اضافه شد.")
    else:
        await update.message.reply_text("❌ کد هدیه نامعتبر یا منقضی شده است.")
    return ConversationHandler.END


# --- MAIN BUTTON HANDLER (CallbackQuery) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id, data = query.from_user.id, query.data.split('_')
    action = data[0]

    if action == "buy":
        plan_id = int(data[1]); plan = db.get_plan(plan_id); user = db.get_or_create_user(user_id)
        if not plan: await query.edit_message_text("❌ این پلن دیگر موجود نیست."); return
        if user['balance'] < plan['price']: await query.edit_message_text(f"موجودی شما کافی نیست!\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان"); return
        
        await query.edit_message_text("در حال ساخت سرویس شما... ⏳")
        result = hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id)
        
        if result and result.get('link'):
            db.update_balance(user_id, plan['price'], add=False)
            db.add_active_service(user_id, result['uuid'], result['link'], plan['days'])
            db.log_sale(user_id, plan['plan_id'], plan['price'])
            await query.edit_message_text(f"✅ سرویس شما با موفقیت ساخته شد!\n\nلینک اتصال:\n`{result['link']}`\n\nبا کلیک روی لینک، به صورت خودکار کپی می‌شود.", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. لطفا به پشتیبانی اطلاع دهید.")
    
    # ... (بقیه منطق button_handler برای تایید شارژ و ...) ...


# --- ADMIN CONVERSATION & FUNCTIONS ---
# (این بخش به دلیل طولانی بودن خلاصه شده است، اما ساختار کلی آن در main() مشخص است)

async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enters the admin main menu."""
    keyboard = [
        ["➕ مدیریت پلن‌ها", "📊 آمار ربات"],
        ["⚙️ تنظیمات", "🎁 مدیریت کد هدیه"],
        ["📩 ارسال پیام", "💾 پشتیبان‌گیری"],
        ["🛑 خاموش کردن ربات", "↩️ خروج از پنل"]
    ]
    await update.message.reply_text( "👑 به پنل ادمین خوش آمدید.", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return ADMIN_MENU

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    message = (f"📊 **آمار کلی ربات**\n\n👥 تعداد کل کاربران: {stats['user_count']} نفر\n"
               f"🛒 تعداد کل فروش‌ها: {stats['sales_count']} عدد\n"
               f"💳 درآمد کل: {stats['total_revenue']:.0f} تومان")
    await update.message.reply_text(message, parse_mode='Markdown')

async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات در حال خاموش شدن است...")
    # A gracefull shutdown
    asyncio.create_task(context.application.shutdown())

async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This helper function brings the admin back to the main admin menu
    await admin_entry(update, context)
    return ADMIN_MENU

# ... (تمام توابع دیگر ادمین مثل مدیریت پلن، تنظیمات، ارسال پیام و...)


# --- MAIN FUNCTION ---
def main():
    db.init_db()
    
    # Create the Application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Filters
    admin_filter = filters.User(user_id=ADMIN_ID)
    
    # --- Conversation Handlers ---
    # 1. User Gift Code redemption
    gift_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🎁 کد هدیه$'), gift_code_start)],
        states={REDEEM_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_gift_code)]},
        fallbacks=[CommandHandler('start', start)]
    )

    # 2. User Charge Wallet
    charge_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(charge_start, pattern='^start_charge$')],
        states={
            CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_amount_received)],
            CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_receipt_received)],
        },
        fallbacks=[CommandHandler('cancel', start)]
    )
    
    # 3. Main Admin Conversation Handler
    admin_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^👑 ورود به پنل ادمین$') & admin_filter, admin_entry)],
        states={
            ADMIN_MENU: [
                MessageHandler(filters.Regex('^📊 آمار ربات$') & admin_filter, show_stats),
                MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$') & admin_filter, shutdown_bot),
                # ... other admin menu handlers would go here ...
            ],
            # ... other admin states like PLAN_MENU, SETTINGS_MENU, etc. would be defined here ...
        },
        fallbacks=[MessageHandler(filters.Regex('^↩️ خروج از پنل$') & admin_filter, start)],
    )

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(gift_handler)
    application.add_handler(charge_handler)
    application.add_handler(admin_handler)
    application.add_handler(CallbackQueryHandler(button_handler))

    # User menu handlers
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), buy_service_list))
    application.add_handler(MessageHandler(filters.Regex('^📋 سرویس‌های من$'), list_my_services))
    application.add_handler(MessageHandler(filters.Regex('^💰 موجودی و شارژ$'), show_balance))
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), show_support))
    application.add_handler(MessageHandler(filters.Regex('^ راهنمای اتصال 📚$'), show_guide))

    print("Advanced Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
