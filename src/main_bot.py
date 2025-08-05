# main_bot.py (نسخه اصلاح شده)

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

import database as db
import hiddify_api
from config import BOT_TOKEN, ADMIN_ID

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# States for ConversationHandler
PLAN_NAME, PLAN_PRICE, PLAN_DAYS, PLAN_GB = range(4)

# --- Helper Functions ---
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.get_or_create_user(user_id)
    
    keyboard = [
        ["🛍️ خرید سرویس"],
        ["💰 موجودی و شارژ حساب", "📞 پشتیبانی"],
    ]
    # فقط اگر کاربر ادمین باشد، دکمه پنل ادمین را به منوی اصلی اضافه کن
    if user_id == ADMIN_ID:
        keyboard.append(["👑 پنل ادمین"])
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("لطفا یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=reply_markup)

# --- User Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!")
    await send_main_menu(update, context)

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_or_create_user(update.effective_user.id)
    await update.message.reply_text(f"💰 موجودی فعلی شما: **{user['balance']:.0f}** تومان\n\nبرای شارژ حساب، به پشتیبانی پیام دهید.", parse_mode='Markdown')

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("جهت ارتباط با پشتیبانی به آیدی زیر پیام ارسال کنید:\n@YOUR_SUPPORT_USERNAME") # آیدی پشتیبانی خود را وارد کنید

async def buy_service_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans:
        await update.message.reply_text("متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست.")
        return
    keyboard = [[InlineKeyboardButton(f"{p['name']} - {p['days']} روزه {p['gb']} گیگ - {p['price']:.0f} تومان", callback_data=f"buy_{p['plan_id']}")] for p in plans]
    await update.message.reply_text("لطفا سرویس مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Callback Query Handler (برای دکمه‌های شیشه‌ای) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data.split('_')
    action = data[0]

    if action == "buy":
        plan = db.get_plan(int(data[1]))
        user = db.get_or_create_user(user_id)
        if not plan:
            await query.edit_message_text("❌ این پلن دیگر موجود نیست.")
            return
        if user['balance'] < plan['price']:
            await query.edit_message_text(f"موجودی شما کافی نیست!\nموجودی: {user['balance']:.0f} تومان\nقیمت پلن: {plan['price']:.0f} تومان")
            return
        
        await query.edit_message_text("در حال ساخت سرویس شما... لطفا چند لحظه صبر کنید. ⏳")
        link = hiddify_api.create_hiddify_user(plan['days'], plan['gb'], user_id)
        
        if link:
            db.update_balance(user_id, -plan['price'])
            await query.edit_message_text(f"✅ سرویس شما با موفقیت ساخته شد!\n\nلینک اتصال شما:\n`{link}`\n\nبا کلیک روی لینک، به صورت خودکار کپی می‌شود.", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ متاسفانه در ساخت سرویس مشکلی پیش آمد. لطفا به پشتیبانی اطلاع دهید.")
    
    elif action == "delete" and user_id == ADMIN_ID:
        db.delete_plan(int(data[1]))
        await query.edit_message_text("پلن با موفقیت حذف شد.")

# --- Admin Functions ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # این تابع فقط توسط ادمین قابل دسترسی است
    keyboard = [
        ["➕ افزودن پلن جدید", "📋 لیست پلن‌ها"],
        ["↩️ بازگشت به منوی اصلی"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👑 به پنل ادمین خوش آمدید. منوی شما تغییر کرد.", reply_markup=reply_markup)

async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفا نام پلن را وارد کنید (مثلا: پلن ۱ ماهه):", reply_markup=ReplyKeyboardMarkup([["لغو"]], resize_keyboard=True))
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
        await admin_panel(update, context) # بازگشت به منوی ادمین
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("لطفا حجم را به صورت عدد صحیح وارد کنید.")
        return PLAN_GB

async def list_plans_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plans = db.list_plans()
    if not plans:
        await update.message.reply_text("هیچ پلنی تعریف نشده است.")
        return
    await update.message.reply_text("لیست پلن‌ها:")
    for plan in plans:
        text = f"🔹 **{plan['name']}** (ID: `{plan['plan_id']}`)\n   - قیمت: {plan['price']:.0f} تومان\n   - مشخصات: {plan['days']} روزه / {plan['gb']} گیگ"
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ حذف این پلن", callback_data=f"delete_{plan['plan_id']}")]]) , parse_mode='Markdown')

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    context.user_data.clear()
    await admin_panel(update, context) # بازگشت به منوی ادمین
    return ConversationHandler.END

def main():
    db.init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    # --- تعریف فیلتر فقط برای ادمین ---
    admin_filter = filters.User(user_id=ADMIN_ID)

    # --- Conversation Handler برای افزودن پلن (فقط برای ادمین) ---
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

    # --- ثبت کنترل‌کننده‌ها (Handlers) ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_plan_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # --- کنترل‌کننده‌های عمومی برای همه کاربران ---
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$'), buy_service_list))
    application.add_handler(MessageHandler(filters.Regex('^💰 موجودی و شارژ حساب$'), show_balance))
    application.add_handler(MessageHandler(filters.Regex('^📞 پشتیبانی$'), show_support))

    # --- کنترل‌کننده‌های مخصوص ادمین ---
    application.add_handler(MessageHandler(filters.Regex('^👑 پنل ادمین$') & admin_filter, admin_panel))
    application.add_handler(MessageHandler(filters.Regex('^📋 لیست پلن‌ها$') & admin_filter, list_plans_admin))
    application.add_handler(MessageHandler(filters.Regex('^↩️ بازگشت به منوی اصلی$') & admin_filter, start))
    
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()