# main.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

# --- وارد کردن ماژول‌های پروژه ---
import config
import hiddify_api

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- کیبوردها ---
def get_start_keyboard():
    keyboard = [
        [InlineKeyboardButton("خرید سرویس 🛍️", callback_data='buy_service')],
        [InlineKeyboardButton("سرویس های من 👤", callback_data='my_services')],
        [InlineKeyboardButton("پشتیبانی 📞", callback_data='support'), InlineKeyboardButton("راهنما 💡", callback_data='help')],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- توابع اصلی ربات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    start_text = f"سلام {user.first_name} عزیز 👋\nبه ربات فروش VPN خوش آمدید."
    await update.message.reply_text(start_text, reply_markup=get_start_keyboard())

# --- تابع جدید برای تست وضعیت پنل ---
async def panel_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور ادمین برای بررسی وضعیت اتصال به پنل Hiddify."""
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("شما اجازه دسترسی به این دستور را ندارید.")
        return

    await update.message.reply_text("⏳ در حال بررسی وضعیت اتصال به پنل Hiddify...")
    
    panel_info = hiddify_api.get_panel_info()
    
    if panel_info:
        stats = panel_info.get('stats', {})
        message = (
            f"✅ **اتصال به پنل موفقیت‌آمیز بود.**\n\n"
            f"📊 **وضعیت پنل:**\n"
            f"▫️ کاربران آنلاین: `{stats.get('connected_users', 'N/A')}`\n"
            f"▫️ مجموع کاربران: `{stats.get('total_users', 'N/A')}`\n"
            f"▫️ مصرف امروز: `{stats.get('usage_today_GB', 'N/A')} GB`\n"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "❌ **اتصال به پنل ناموفق بود.**\n\n"
            "لطفاً موارد زیر را بررسی کنید:\n"
            "1. اطلاعات در فایل `config.py`.\n"
            "2. دسترسی سرور ربات به آدرس پنل.\n"
            "3. خطاهای نمایش داده شده در کنسول سرور ربات."
        )

# --- تابع برای مدیریت دکمه‌های شیشه‌ای ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # برای اینکه دکمه از حالت لودینگ خارج شود

    if query.data == 'buy_service':
        await query.edit_message_text(text="در حال حاضر سرویسی برای فروش وجود ندارد. به زودی...")
    elif query.data == 'my_services':
        await query.edit_message_text(text="شما هنوز سرویسی خریداری نکرده‌اید.")
    elif query.data == 'support':
        await query.edit_message_text(text="برای پشتیبانی با ایدی @YourSupportID در تماس باشید.")
    elif query.data == 'help':
        await query.edit_message_text(text="این ربات برای فروش کانفیگ‌های v2ray طراحی شده است.")
    else:
        await query.edit_message_text(text="دستور شناسایی نشد.")

def main() -> None:
    """Start the bot."""
    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # --- اضافه کردن هندلرها ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("panel_status", panel_status))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()