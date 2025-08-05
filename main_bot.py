# main_bot.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

import database as db
import hiddify_api
from config import BOT_TOKEN, ADMIN_ID

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# States for ConversationHandler (Admin Add Plan)
PLAN_NAME, PLAN_PRICE, PLAN_DAYS, PLAN_GB = range(4)

# --- Helper Functions ---
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.get_or_create_user(user_id)
    
    keyboard = [
        ["🛍️ خرید سرویس"],
        ["💰 موجودی و شارژ حساب", "📞 پشتیبانی"],
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["👑 پنل ادمین"])
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("لطفا یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=reply_markup)

# --- User Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("به ربات فروش VPN خوش آمدید!")
    await send_main_menu(update, context)

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id)
    await update.message.reply_text(f"💰 موجودی فعلی شما: {user['balance']:.0f} تومان\n\nبرای شارژ حساب، لطفا با پشتیبانی در تماس باشید.")

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("برای ارتباط با پشتیبانی، به آیدی زیر پیام دهید:\n@YOUR_SUPPORT_ID")

async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans:
        await update.message.reply_text("متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست.")
        return

    keyboard = []
    for plan in plans:
        text = f"{plan['name']} - {plan['days']} روزه {plan['gb']} گیگ - {plan['price']:.0f} تومان"
        keyboard.append([InlineKeyboardButton(text, callback_data=f"buy_plan_{plan['plan_id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("لطفا سرویس مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup)

# --- Callback Query Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data.startswith("buy_plan_"):
        plan_id = int(query.data.split("_")[2])
        plan = db.get_plan(plan_id)
        user = db.get_or_create_user(user_id)

        if not plan:
            await query.edit_message_text("خطا: این پلن دیگر موجود نیست.")
            return

        if user['balance'] < plan['price']:
            await query.edit_message_text(f"موجودی شما کافی نیست!\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان")
            return
        
        await query.edit_message_text("در حال ساخت سرویس شما... لطفا چند لحظه صبر کنید.")
        
        subscription_link = hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id)
        
        if subscription_link:
            db.update_balance(user_id, -plan['price'])
            message_text = (
                "✅ سرویس شما با موفقیت ساخته شد!\n\n"
                f"لینک اتصال شما:\n`{subscription_link}`\n\n"
                "با کلیک روی لینک، به صورت خودکار در برنامه‌های کلاینت کپی می‌شود."
            )
            await query.edit_message_text(message_text, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. لطفا به پشتیبانی اطلاع دهید.")
    
    elif query.data.startswith("delete_plan_"):
        if user_id != ADMIN_ID: return
        plan_id = int(query.data.split("_")[2])
        db.delete_plan(plan_id)
        await query.edit_message_text("پلن با موفقیت حذف شد.")
        await list_plans_admin(query, context) # Refresh list


# --- Admin Commands ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("شما ادمین نیستید.")
        return
    keyboard = [
        ["➕ افزودن پلن جدید"],
        ["📋 لیست پلن‌ها"],
        ["↩️ بازگشت به منوی اصلی"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👑 به پنل ادمین خوش آمدید.", reply_markup=reply_markup)

async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("لطفا نام پلن را وارد کنید (مثلا: پلن برنزی):")
    return PLAN_NAME

async def plan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plan_name'] = update.message.text
    await update.message.reply_text("نام پلن ثبت شد. حالا قیمت را به تومان وارد کنید (فقط عدد):")
    return PLAN_PRICE

async def plan_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_price'] = float(update.message.text)
        await update.message.reply_text("قیمت ثبت شد. حالا تعداد روزهای اعتبار را وارد کنید (مثلا: 30):")
        return PLAN_DAYS
    except ValueError:
        await update.message.reply_text("لطفا قیمت را به صورت عدد صحیح وارد کنید.")
        return PLAN_PRICE

async def plan_days_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_days'] = int(update.message.text)
        await update.message.reply_text("تعداد روز ثبت شد. حالا حجم سرویس به گیگابایت را وارد کنید (مثلا: 50):")
        return PLAN_GB
    except ValueError:
        await update.message.reply_text("لطفا تعداد روز را به صورت عدد صحیح وارد کنید.")
        return PLAN_DAYS

async def plan_gb_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['plan_gb'] = int(update.message.text)
        plan = context.user_data
        db.add_plan(plan['plan_name'], plan['plan_price'], plan['plan_days'], plan['plan_gb'])
        await update.message.reply_text("✅ پلن جدید با موفقیت به سیستم اضافه شد!")
        context.user_data.clear()
        await admin_panel(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("لطفا حجم را به صورت عدد صحیح وارد کنید.")
        return PLAN_GB
        
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    context.user_data.clear()
    await admin_panel(update, context)
    return ConversationHandler.END
    
async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    plans = db.list_plans()
    if not plans:
        await update.message.reply_text("هیچ پلنی تعریف نشده است.")
        return

    message = "📋 لیست پلن‌های موجود:\n\n"
    for plan in plans:
        message += f"🔹 **{plan['name']}**\n"
        message += f"   - قیمت: {plan['price']:.0f} تومان\n"
        message += f"   - مشخصات: {plan['days']} روزه / {plan['gb']} گیگ\n"
        message += f"   - ID: `{plan['plan_id']}`\n"
        # For inline deletion
        keyboard = [[InlineKeyboardButton("🗑️ حذف این پلن", callback_data=f"delete_plan_{plan['plan_id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        message = "" # Reset for next iteration


def main():
    # Initialize database
    db.init_db()

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for adding a plan
    add_plan_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^➕ افزودن پلن جدید$'), add_plan_start)],
        states={
            PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_name_received)],
            PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_price_received)],
            PLAN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_days_received)],
            PLAN_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_gb_received)],
        },
        fallbacks=[CommandHandler('cancel', cancel_conversation)],
    )

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_plan_conv_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Message Handlers for main menu
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), buy_service_list))
    application.add_handler(MessageHandler(filters.Regex('^💰 موجودی و شارژ حساب$'), show_balance))
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), show_support))
    application.add_handler(MessageHandler(filters.Regex('^👑 پنل ادمین$'), admin_panel))
    application.add_handler(MessageHandler(filters.Regex('^📋 لیست پلن‌ها$'), list_plans_admin))
    application.add_handler(MessageHandler(filters.Regex('^↩️ بازگشت به منوی اصلی$'), start))


    # Run the bot
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
