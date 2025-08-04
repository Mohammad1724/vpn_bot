# main.py (نسخه دیباگ)

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

# (بقیه کدها و کیبوردها دست نخورده باقی می‌مانند)
# ...
# Enable logging, get_user_keyboard, get_admin_keyboard, etc.
# ...

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_user_keyboard():
    keyboard = [
        [InlineKeyboardButton("خرید سرویس 🛍️", callback_data='buy_service')],
        [InlineKeyboardButton("سرویس های من 👤", callback_data='my_services')],
        [InlineKeyboardButton("پشتیبانی 📞", callback_data='support'), InlineKeyboardButton("راهنما 💡", callback_data='help')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("خرید سرویس 🛍️", callback_data='buy_service')],
        [InlineKeyboardButton("سرویس های من 👤", callback_data='my_services')],
        [InlineKeyboardButton("⚙️ پنل مدیریت ⚙️", callback_data='admin_panel')],
        [InlineKeyboardButton("پشتیبانی 📞", callback_data='support'), InlineKeyboardButton("راهنما 💡", callback_data='help')],
    ]
    return InlineKeyboardMarkup(keyboard)

# ... (سایر کیبوردها و توابع)
def get_admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 وضعیت پنل", callback_data='admin_panel_status')],
        [InlineKeyboardButton("➕ ساخت کاربر جدید", callback_data='admin_create_user')],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data='admin_list_users')],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)


# ======================================================================
#  تابع start با قابلیت دیباگ (تنها بخش تغییر یافته)
# ======================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    start_text = f"سلام {user.first_name} عزیز 👋\nبه ربات فروش VPN خوش آمدید."

    # --- بخش دیباگ ---
    # این پیام فقط به ادمین ارسال می‌شود تا مقادیر را ببیند
    debug_message = (
        f"--- DEBUG INFO ---\n"
        f"User ID from Telegram: {user.id} (Type: {type(user.id)})\n"
        f"Admin ID from Config: {config.ADMIN_ID} (Type: {type(config.ADMIN_ID)})\n"
        f"Comparison Result (user.id == config.ADMIN_ID): {user.id == config.ADMIN_ID}"
    )
    # ارسال پیام دیباگ به چت ادمین
    await context.bot.send_message(chat_id=config.ADMIN_ID, text=debug_message)
    # --- پایان بخش دیباگ ---

    # چک می‌کنیم که آیا کاربر، ادمین است یا خیر
    if user.id == config.ADMIN_ID:
        await update.message.reply_text(start_text, reply_markup=get_admin_keyboard())
    else:
        await update.message.reply_text(start_text, reply_markup=get_user_keyboard())

# ======================================================================

# (بقیه کد button_callback_handler و main دست نخورده باقی می‌ماند)
async def panel_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text("❌ اتصال به پنل ناموفق بود.")


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
        await query.edit_message_text(text="در حال حاضر سرویسی برای فروش وجود ندارد. به زودی...")
    elif data == 'my_services':
        await query.edit_message_text(text="شما هنوز سرویسی خریداری نکرده‌اید.")
    elif data == 'support':
        await query.edit_message_text(text="برای پشتیبانی با ایدی @YourSupportID در تماس باشید.")
    elif data == 'help':
        await query.edit_message_text(text="این ربات برای فروش کانفیگ‌های v2ray طراحی شده است.")
    elif data == 'admin_panel':
        if user_id == config.ADMIN_ID:
            await query.edit_message_text(text="⚙️ به پنل مدیریت خوش آمدید.", reply_markup=get_admin_panel_keyboard())
        else:
            await query.answer("شما اجازه دسترسی به این بخش را ندارید.", show_alert=True)
    elif data == 'admin_panel_status':
        if user_id == config.ADMIN_ID:
            await query.message.reply_text("⏳ در حال بررسی وضعیت اتصال به پنل Hiddify...")
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
                await query.message.reply_text(message, parse_mode='Markdown')
            else:
                await query.message.reply_text("❌ اتصال به پنل ناموفق بود.")
        else:
            await query.answer("شما اجازه دسترسی به این بخش را ندارید.", show_alert=True)
    elif data == 'admin_create_user':
        await query.edit_message_text(text="این قابلیت (ساخت کاربر) در مرحله بعد اضافه خواهد شد.")
    elif data == 'admin_list_users':
        await query.edit_message_text(text="این قابلیت (لیست کاربران) در مراحل بعد اضافه خواهد شد.")
    else:
        await query.edit_message_text(text="دستور شناسایی نشد.")


def main() -> None:
    application = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("panel_status", panel_status))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    print("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
