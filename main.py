# main.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

import config
import hiddify_api

# فعال‌سازی لاگ‌ها برای دیدن خطاها در کنسول
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- تعریف کیبوردها ---
def get_user_keyboard():
    keyboard = [
        [InlineKeyboardButton("خرید سرویس 🛍️", callback_data='buy_service')],
        [InlineKeyboardButton("سرویس های من 👤", callback_data='my_services')],
        [InlineKeyboardButton("پشتیبانی 📞", callback_data='support'), InlineKeyboardButton("راهنما 💡", callback_data='help')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("خرید سرویس 🛍️", callback_data='buy_service'), InlineKeyboardButton("سرویس های من 👤", callback_data='my_services')],
        [InlineKeyboardButton("⚙️ پنل مدیریت ⚙️", callback_data='admin_panel')],
        [InlineKeyboardButton("پشتیبانی 📞", callback_data='support'), InlineKeyboardButton("راهنما 💡", callback_data='help')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 وضعیت پنل", callback_data='admin_panel_status')],
        [InlineKeyboardButton("➕ ساخت کاربر جدید", callback_data='admin_create_user')],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- توابع اصلی ربات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    start_text = f"سلام {user.first_name} عزیز 👋\nبه ربات فروش VPN خوش آمدید."
    
    keyboard = get_admin_keyboard() if user.id == config.ADMIN_ID else get_user_keyboard()
    await update.message.reply_text(start_text, reply_markup=keyboard)

async def handle_panel_status_logic(message_or_query):
    """منطق نمایش وضعیت پنل برای جلوگیری از تکرار کد"""
    await message_or_query.reply_text("⏳ در حال بررسی وضعیت پنل...")
    stats_info = hiddify_api.get_panel_stats()
    
    if stats_info and 'stats' in stats_info:
        stats = stats_info['stats']
        message_text = (
            f"✅ **اتصال به پنل موفقیت‌آمیز بود.**\n\n"
            f"📊 **وضعیت پنل:**\n"
            f"▫️ کاربران آنلاین: `{stats.get('connected_users', 'N/A')}`\n"
            f"▫️ مجموع کاربران: `{stats.get('total_users', 'N/A')}`\n"
            f"▫️ مصرف امروز: `{stats.get('usage_today_GB', 'N/A')} GB`\n"
        )
        await message_or_query.reply_text(message_text, parse_mode='Markdown')
    else:
        await message_or_query.reply_text(
            "❌ **اتصال به پنل ناموفق بود.**\n"
            "لطفاً مطمئن شوید `HIDDIFY_API_KEY` در فایل کانفیگ صحیح است و لاگ‌های سرور را بررسی کنید."
        )

async def panel_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == config.ADMIN_ID:
        await handle_panel_status_logic(update.message)
    else:
        await update.message.reply_text("شما اجازه دسترسی به این دستور را ندارید.")

# --- مدیریت دکمه‌های شیشه‌ای ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == 'main_menu':
        start_text = f"سلام {query.from_user.first_name} عزیز 👋\nمنوی اصلی:"
        keyboard = get_admin_keyboard() if user_id == config.ADMIN_ID else get_user_keyboard()
        await query.edit_message_text(text=start_text, reply_markup=keyboard)
    elif data == 'buy_service':
        await query.edit_message_text(text="این قابلیت به زودی اضافه خواهد شد.")
    elif data == 'my_services':
        await query.edit_message_text(text="این قابلیت به زودی اضافه خواهد شد.")
    elif data == 'support':
        await query.edit_message_text(text="جهت پشتیبانی با @AdminID در تماس باشید.")
    elif data == 'help':
        await query.edit_message_text(text="راهنمای ربات در حال آماده‌سازی است.")
    elif data == 'admin_panel':
        if user_id == config.ADMIN_ID:
            await query.edit_message_text(text="⚙️ به پنل مدیریت خوش آمدید.", reply_markup=get_admin_panel_keyboard())
    elif data == 'admin_panel_status':
        if user_id == config.ADMIN_ID:
            await handle_panel_status_logic(query.message)
    elif data == 'admin_create_user':
        if user_id == config.ADMIN_ID:
            await query.edit_message_text(text="این قابلیت در مرحله بعد اضافه خواهد شد.")
    else:
        await query.edit_message_text(text="دستور شناسایی نشد.")

# --- تابع اصلی ---
def main() -> None:
    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("panel_status", panel_status_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()