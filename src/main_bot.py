import logging
import os
import shutil
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, InputFile
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
                          filters, ContextTypes, ConversationHandler, ApplicationBuilder)
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest

import database as db
import hiddify_api
from config import BOT_TOKEN, ADMIN_ID, SUPPORT_USERNAME

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
    REDEEM_GIFT,
    BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE
) = range(21)

# --- KEYBOARDS ---
def get_main_menu_keyboard(user_id):
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["💰 موجودی و شارژ", "🎁 کد هدیه"],
        ["📞 پشتیبانی", " راهنمای اتصال 📚"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 ورود به پنل ادمین"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu_keyboard():
    keyboard = [
        ["➕ مدیریت پلن‌ها", "📊 آمار ربات"],
        ["⚙️ تنظیمات", "🎁 مدیریت کد هدیه"],
        ["📩 ارسال پیام", "💾 پشتیبان‌گیری"],
        ["🛑 خاموش کردن ربات", "↩️ خروج از پنل"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def back_to_admin_keyboard():
    return ReplyKeyboardMarkup([["بازگشت به منوی ادمین"]], resize_keyboard=True)

# --- USER HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.get_or_create_user(user_id)
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_or_create_user(update.effective_user.id)
    keyboard = [[InlineKeyboardButton("💳 شارژ حساب", callback_data="start_charge")]]
    await update.message.reply_text(f"💰 موجودی فعلی شما: **{user['balance']:.0f}** تومان", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"جهت ارتباط با پشتیبانی به آیدی زیر پیام ارسال کنید:\n@{SUPPORT_USERNAME}")

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
    
    msg = await update.message.reply_text("در حال دریافت اطلاعات سرویس‌های شما... ⏳")
    all_services_message = "📋 سرویس‌های فعال شما:\n\n"
    has_service = False
    for service in services:
        info = hiddify_api.get_user_info(service['sub_uuid'])
        if info:
            has_service = True
            try:
                expiry_date_obj = datetime.strptime(info.get('expiry_date', '1970-01-01'), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                expiry_date_obj = datetime.now().date() - timedelta(days=1)

            is_expired = expiry_date_obj < datetime.now().date()
            status = "🔴 منقضی شده" if is_expired else "🟢 فعال"
            
            # Find the plan associated with this service for renewal info
            renewal_plan = db.get_plan(service['plan_id'])
            
            all_services_message += (
                f"🔗 لینک: `{service['sub_link']}`\n"
                f"🗓️ تاریخ انقضا: {info.get('expiry_date', 'N/A')}\n"
                f"📊 حجم مصرفی: {info.get('current_usage_GB', 0):.2f} / {info.get('usage_limit_GB', 0):.0f} گیگ\n"
                f"🚦 وضعیت: {status}\n")
            if renewal_plan:
                 all_services_message += f"🔄 هزینه تمدید: {renewal_plan['price']:.0f} تومان\n"

            all_services_message += "---\n"

    if has_service:
        await msg.edit_text(all_services_message, parse_mode=ParseMode.MARKDOWN)
    else:
        await msg.edit_text("خطا در دریافت اطلاعات سرویس‌ها. لطفا بعدا تلاش کنید.")

# --- Conversation Handlers: Gift Code, Charge Wallet ---
async def gift_code_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 لطفا کد هدیه خود را وارد کنید:", reply_markup=ReplyKeyboardMarkup([["لغو"]], resize_keyboard=True))
    return REDEEM_GIFT
async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.upper()
    user_id = update.effective_user.id
    amount = db.use_gift_code(code, user_id)
    if amount:
        await update.message.reply_text(f"✅ تبریک! مبلغ {amount:.0f} تومان به کیف پول شما اضافه شد.", reply_markup=get_main_menu_keyboard(user_id))
    else:
        await update.message.reply_text("❌ کد هدیه نامعتبر یا استفاده شده است.", reply_markup=get_main_menu_keyboard(user_id))
    return ConversationHandler.END
async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.message.reply_text("لطفاً مبلغی که قصد واریز آن را دارید به تومان وارد کنید (فقط عدد):", reply_markup=ReplyKeyboardMarkup([["لغو"]], resize_keyboard=True))
    return CHARGE_AMOUNT
async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount <= 1000: raise ValueError
        context.user_data['charge_amount'] = amount
        card_number, card_holder = db.get_setting('card_number'), db.get_setting('card_holder')
        await update.message.reply_text(f"لطفاً مبلغ **{amount:,} تومان** را به شماره کارت زیر واریز نمایید:\n\n`{card_number}`\nبه نام: {card_holder}\n\nسپس از رسید واریزی خود عکس گرفته و آن را در همین صفحه ارسال کنید.", parse_mode=ParseMode.MARKDOWN)
        return CHARGE_RECEIPT
    except ValueError:
        await update.message.reply_text("لطفا یک عدد صحیح و بیشتر از 1000 تومان وارد کنید."); return CHARGE_AMOUNT
async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, amount = update.effective_user, context.user_data['charge_amount']
    receipt_photo = update.message.photo[-1]
    caption = (f"درخواست شارژ جدید 🔔\n\nکاربر: {user.full_name} (@{user.username})\nآیدی عددی: `{user.id}`\nمبلغ درخواستی: **{amount:,} تومان**")
    keyboard = [[InlineKeyboardButton("✅ تایید شارژ", callback_data=f"confirm_charge_{user.id}_{amount}"), InlineKeyboardButton("❌ رد درخواست", callback_data=f"reject_charge_{user.id}")]]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=receipt_photo.file_id, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_text("✅ رسید شما برای ادمین ارسال شد. لطفاً تا زمان بررسی و تایید منتظر بمانید.", reply_markup=get_main_menu_keyboard(user.id))
    context.user_data.clear(); return ConversationHandler.END


# --- ADMIN CONVERSATION & FUNCTIONS ---
async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👑 به پنل ادمین خوش آمدید.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU
async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("شما از پنل ادمین خارج شدید.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END
async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("به منوی اصلی ادمین بازگشتید.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

# Admin - Stats
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_stats()
    message = (f"📊 **آمار کلی ربات**\n\n👥 تعداد کل کاربران: {stats['user_count']} نفر\n"
               f"🛒 تعداد کل فروش‌ها: {stats['sales_count']} عدد\n"
               f"💳 درآمد کل: {stats['total_revenue']:.0f} تومان")
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

# Admin - Plan Management
async def plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["➕ افزودن پلن جدید", "📋 لیست پلن‌ها"], ["بازگشت به منوی ادمین"]]
    await update.message.reply_text("بخش مدیریت پلن‌ها", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return PLAN_MENU
async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا نام پلن را وارد کنید (مثلا: پلن ۱ ماهه):", reply_markup=ReplyKeyboardMarkup([["لغو"]], resize_keyboard=True)); return PLAN_NAME
async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_name'] = update.message.text; await update.message.reply_text("نام ثبت شد. قیمت را به تومان وارد کنید:"); return PLAN_PRICE
async def plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: context.user_data['plan_price'] = float(update.message.text); await update.message.reply_text("قیمت ثبت شد. تعداد روزهای اعتبار را وارد کنید:"); return PLAN_DAYS
    except ValueError: await update.message.reply_text("لطفا قیمت را به صورت عدد وارد کنید."); return PLAN_PRICE
async def plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: context.user_data['plan_days'] = int(update.message.text); await update.message.reply_text("تعداد روز ثبت شد. حجم سرویس به گیگابایت را وارد کنید:"); return PLAN_GB
    except ValueError: await update.message.reply_text("لطفا تعداد روز را به صورت عدد وارد کنید."); return PLAN_DAYS
async def plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_gb'] = int(update.message.text)
        db.add_plan(context.user_data['plan_name'], context.user_data['plan_price'], context.user_data['plan_days'], context.user_data['plan_gb'])
        await update.message.reply_text("✅ پلن جدید اضافه شد!", reply_markup=get_admin_menu_keyboard())
        context.user_data.clear(); return ADMIN_MENU
    except ValueError: await update.message.reply_text("لطفا حجم را به صورت عدد وارد کنید."); return PLAN_GB
async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans: await update.message.reply_text("هیچ پلنی تعریف نشده."); return
    for p in plans:
        text = f"🔹 **{p['name']}** (ID: `{p['plan_id']}`)\n   - قیمت: {p['price']:.0f} تومان\n   - مشخصات: {p['days']} روزه / {p['gb']} گیگ"
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_plan_{p['plan_id']}")]]) , parse_mode=ParseMode.MARKDOWN)

# Admin - Settings
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["ویرایش شماره کارت", "ویرایش نام صاحب حساب"], ["بازگشت به منوی ادمین"]]
    await update.message.reply_text("بخش تنظیمات", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)); return SETTINGS_MENU
async def edit_card_number_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"شماره کارت فعلی: {db.get_setting('card_number')}\nشماره کارت جدید را وارد کنید:"); return SET_CARD_NUMBER
async def set_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting('card_number', update.message.text); await update.message.reply_text("✅ شماره کارت به‌روز شد.", reply_markup=get_admin_menu_keyboard()); return ADMIN_MENU
async def edit_card_holder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"نام صاحب حساب فعلی: {db.get_setting('card_holder')}\nنام جدید را وارد کنید:"); return SET_CARD_HOLDER
async def set_card_holder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting('card_holder', update.message.text); await update.message.reply_text("✅ نام صاحب حساب به‌روز شد.", reply_markup=get_admin_menu_keyboard()); return ADMIN_MENU

# ... (سایر توابع ادمین مانند ارسال پیام، بکاپ و کد هدیه)

async def shutdown_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات در حال خاموش شدن است...")
    asyncio.create_task(context.application.shutdown())

async def generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ADMIN_MENU

# --- MAIN FUNCTION ---
def main():
    db.init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    admin_filter = filters.User(user_id=ADMIN_ID)

    # User-side conversations
    gift_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🎁 کد هدیه$') & ~admin_filter, gift_code_entry)],
        states={REDEEM_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_gift_code)]},
        fallbacks=[MessageHandler(filters.Regex('^لغو$'), start), CommandHandler('start', start)]
    )
    charge_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(charge_start, pattern='^start_charge$')],
        states={
            CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_amount_received)],
            CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_receipt_received)],
        },
        fallbacks=[MessageHandler(filters.Regex('^لغو$'), start), CommandHandler('start', start)]
    )

    # Admin Conversation Handler
    add_plan_sub_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ افزودن پلن جدید$') & admin_filter, add_plan_start)],
        states={
            PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_name_received)],
            PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_price_received)],
            PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_days_received)],
            PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_gb_received)],
        },
        fallbacks=[MessageHandler(filters.Regex('^لغو$'), back_to_admin_menu)],
        map_to_parent={ADMIN_MENU: ADMIN_MENU}
    )
    settings_sub_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^⚙️ تنظیمات$') & admin_filter, settings_menu)],
        states={
            SETTINGS_MENU: [
                MessageHandler(filters.Regex('^ویرایش شماره کارت$'), edit_card_number_start),
                MessageHandler(filters.Regex('^ویرایش نام صاحب حساب$'), edit_card_holder_start),
            ],
            SET_CARD_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_card_number)],
            SET_CARD_HOLDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_card_holder)],
        },
        fallbacks=[MessageHandler(filters.Regex('^بازگشت به منوی ادمین$'), back_to_admin_menu)],
        map_to_parent={ADMIN_MENU: ADMIN_MENU}
    )
    
    admin_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^👑 ورود به پنل ادمین$') & admin_filter, admin_entry)],
        states={
            ADMIN_MENU: [
                add_plan_sub_handler,
                settings_sub_handler,
                MessageHandler(filters.Regex('^📊 آمار ربات$') & admin_filter, show_stats),
                MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$') & admin_filter, shutdown_bot),
                MessageHandler(filters.Regex('^➕ مدیریت پلن‌ها$') & admin_filter, plan_management_menu),
            ],
            PLAN_MENU: [
                add_plan_sub_handler, # Allow adding from this menu
                MessageHandler(filters.Regex('^📋 لیست پلن‌ها$') & admin_filter, list_plans_admin),
                MessageHandler(filters.Regex('^بازگشت به منوی ادمین$') & admin_filter, back_to_admin_menu),
            ]
        },
        fallbacks=[MessageHandler(filters.Regex('^↩️ خروج از پنل$') & admin_filter, exit_admin_panel)]
    )

    # Register handlers
    application.add_handler(admin_conv_handler)
    application.add_handler(gift_handler)
    application.add_handler(charge_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # General message handlers for user menu
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$') & ~admin_filter, buy_service_list))
    application.add_handler(MessageHandler(filters.Regex('^📋 سرویس‌های من$') & ~admin_filter, list_my_services))
    application.add_handler(MessageHandler(filters.Regex('^💰 موجودی و شارژ$') & ~admin_filter, show_balance))
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$') & ~admin_filter, show_support))
    application.add_handler(MessageHandler(filters.Regex('^ راهنمای اتصال 📚$') & ~admin_filter, show_guide))
    
    print("Advanced Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()