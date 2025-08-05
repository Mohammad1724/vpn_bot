# main_bot.py (نسخه نهایی با سیستم شارژ)

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

import database as db
import hiddify_api
from config import BOT_TOKEN, ADMIN_ID

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# States for Conversations
# Admin Add Plan states
PLAN_NAME, PLAN_PRICE, PLAN_DAYS, PLAN_GB = range(4)
# User Charge Wallet states
CHARGE_AMOUNT, CHARGE_RECEIPT = range(4, 6)

# --- Helper Functions ---
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.get_or_create_user(user_id)
    keyboard = [["🛍️ خرید سرویس"], ["💰 موجودی و شارژ حساب", "📞 پشتیبانی"]]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 پنل ادمین"])
    await update.message.reply_text("لطفا یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# --- User Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!")
    await send_main_menu(update, context)

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
    plans = db.list_plans()
    if not plans:
        await update.message.reply_text("متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست.")
        return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان", callback_data=f"buy_{p['plan_id']}")] for p in plans]
    await update.message.reply_text("لطفا سرویس مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Charge Wallet Conversation ---
async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً مبلغی که قصد واریز آن را دارید به تومان وارد کنید (فقط عدد):")
    return CHARGE_AMOUNT

async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount <= 0:
            raise ValueError
        context.user_data['charge_amount'] = amount
        card_number = "1234-5678-9012-3456" # <<<< شماره کارت خود را اینجا وارد کنید
        await update.message.reply_text(
            f"لطفاً مبلغ **{amount:,} تومان** را به شماره کارت زیر واریز نمایید:\n\n`{card_number}`\n\n"
            "سپس از رسید واریزی خود عکس گرفته و آن را در همین صفحه ارسال کنید.",
            parse_mode='Markdown'
        )
        return CHARGE_RECEIPT
    except ValueError:
        await update.message.reply_text("لطفا یک عدد صحیح و مثبت وارد کنید.")
        return CHARGE_AMOUNT

async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = context.user_data['charge_amount']
    receipt_photo = update.message.photo[-1]  # Get the highest resolution photo

    # Forward the receipt to the admin
    caption = (
        f"درخواست شارژ جدید 🔔\n\n"
        f"کاربر: {user.full_name} (@{user.username})\n"
        f"آیدی عددی: `{user.id}`\n"
        f"مبلغ درخواستی: **{amount:,} تومان**\n\n"
        "لطفا پس از بررسی، درخواست را تایید یا رد کنید."
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ تایید شارژ", callback_data=f"confirm_charge_{user.id}_{amount}"),
            InlineKeyboardButton("❌ رد درخواست", callback_data=f"reject_charge_{user.id}")
        ]
    ]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=receipt_photo.file_id,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    await update.message.reply_text("✅ رسید شما برای ادمین ارسال شد. لطفاً تا زمان بررسی و تایید توسط ادمین منتظر بمانید.")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_charge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات شارژ حساب لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END


# --- Callback Query Handler (دکمه‌های شیشه‌ای) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data.split('_')
    action = data[0]

    if action == "start" and data[1] == "charge":
        # این دکمه مکالمه شارژ را شروع می‌کند که توسط ConversationHandler مدیریت می‌شود
        # برای جلوگیری از تداخل، اینجا کاری انجام نمی‌دهیم.
        return
        
    if action == "buy":
        # ... (کد خرید بدون تغییر باقی می‌ماند) ...
        plan = db.get_plan(int(data[1]))
        user = db.get_or_create_user(user_id)
        if not plan: await query.edit_message_text("❌ این پلن دیگر موجود نیست."); return
        if user['balance'] < plan['price']: await query.edit_message_text(f"موجودی شما کافی نیست!\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان"); return
        await query.edit_message_text("در حال ساخت سرویس شما... لطفا چند لحظه صبر کنید. ⏳")
        link = hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id)
        if link:
            db.update_balance(user_id, -plan['price'])
            await query.edit_message_text(f"✅ سرویس شما با موفقیت ساخته شد!\n\nلینک اتصال شما:\n`{link}`\n\nبا کلیک روی لینک، به صورت خودکار کپی می‌شود.", parse_mode='Markdown')
        else: await query.edit_message_text("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. لطفا به پشتیبانی اطلاع دهید.")
    
    elif action == "delete" and user_id == ADMIN_ID:
        db.delete_plan(int(data[1]))
        await query.edit_message_text("پلن با موفقیت حذف شد.")

    elif action == "confirm" and user_id == ADMIN_ID:
        target_user_id = int(data[2])
        amount = int(data[3])
        db.update_balance(target_user_id, amount)
        await query.edit_message_text(f"✅ با موفقیت مبلغ {amount:,} تومان به حساب کاربری {target_user_id} اضافه شد.")
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"حساب شما با موفقیت به مبلغ **{amount:,} تومان** شارژ شد!",
            parse_mode='Markdown'
        )

    elif action == "reject" and user_id == ADMIN_ID:
        target_user_id = int(data[2])
        await query.edit_message_text(f"❌ درخواست شارژ کاربر {target_user_id} رد شد.")
        await context.bot.send_message(
            chat_id=target_user_id,
            text="متاسفانه درخواست شارژ حساب شما توسط ادمین رد شد. لطفا برای پیگیری با پشتیبانی در تماس باشید."
        )


# --- Admin Functions (بدون تغییر) ---
# ... (تمام توابع ادمین از admin_panel تا cancel_conversation اینجا قرار می‌گیرند) ...
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["➕ افزودن پلن جدید", "📋 لیست پلن‌ها"],["↩️ بازگشت به منوی اصلی"]]
    await update.message.reply_text("👑 به پنل ادمین خوش آمدید.", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا نام پلن را وارد کنید:", reply_markup=ReplyKeyboardMarkup([["لغو"]], resize_keyboard=True))
    return PLAN_NAME
async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_name'] = update.message.text
    await update.message.reply_text("نام ثبت شد. قیمت را به تومان وارد کنید:"); return PLAN_PRICE
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
        await update.message.reply_text("✅ پلن جدید اضافه شد!")
        context.user_data.clear(); await admin_panel(update, context); return ConversationHandler.END
    except ValueError: await update.message.reply_text("لطفا حجم را به صورت عدد وارد کنید."); return PLAN_GB
async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans: await update.message.reply_text("هیچ پلنی تعریف نشده."); return
    await update.message.reply_text("لیست پلن‌ها:")
    for p in plans:
        text = f"🔹 **{p['name']}** (ID: `{p['plan_id']}`)\n   - قیمت: {p['price']:.0f} تومان\n   - مشخصات: {p['days']} روزه / {p['gb']} گیگ"
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_{p['plan_id']}")]]) , parse_mode='Markdown')
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد."); context.user_data.clear(); await admin_panel(update, context); return ConversationHandler.END


def main():
    db.init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    admin_filter = filters.User(user_id=ADMIN_ID)
    
    # Conversation handler برای شارژ حساب
    charge_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(charge_start, pattern='^start_charge$')],
        states={
            CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_amount_received)],
            CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_receipt_received)],
        },
        fallbacks=[CommandHandler('cancel', cancel_charge)],
    )

    # Conversation handler برای افزودن پلن (فقط ادمین)
    add_plan_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ افزودن پلن جدید$') & admin_filter, add_plan_start)],
        states={
            PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, plan_name_received)],
            PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, plan_price_received)],
            PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, plan_days_received)],
            PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, plan_gb_received)],
        },
        fallbacks=[MessageHandler(filters.Regex('^لغو$') & admin_filter, cancel_conversation)],
    )

    # ثبت کنترل‌کننده‌ها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(charge_conv_handler)
    application.add_handler(add_plan_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # کنترل‌کننده‌های منوی اصلی
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), buy_service_list))
    application.add_handler(MessageHandler(filters.Regex('^💰 موجودی و شارژ حساب$'), show_balance))
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), show_support))
    application.add_handler(MessageHandler(filters.Regex('^👑 پنل ادمین$') & admin_filter, admin_panel))
    application.add_handler(MessageHandler(filters.Regex('^📋 لیست پلن‌ها$') & admin_filter, list_plans_admin))
    application.add_handler(MessageHandler(filters.Regex('^↩️ بازگشت به منوی اصلی$') & admin_filter, start))
    
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
