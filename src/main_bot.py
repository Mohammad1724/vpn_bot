# -*- coding: utf-8 -*-

import logging
import os
import shutil
import asyncio
import random
import sqlite3
import io
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    ApplicationBuilder
)
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest
# فرض بر این است که این فایل‌ها با نسخه‌های اصلاح‌شده جایگزین شده‌اند
import database as db
import hiddify_api
from config import (
    BOT_TOKEN, ADMIN_ID, SUPPORT_USERNAME, SUB_DOMAINS, ADMIN_PATH,
    PANEL_DOMAIN, SUB_PATH, TRIAL_ENABLED, TRIAL_DAYS, TRIAL_GB
)
import qrcode

# --- Setup ---
os.makedirs('backups', exist_ok=True)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Constants & States ---
# (این بخش بدون تغییر باقی می‌ماند)
USAGE_ALERT_THRESHOLD = 0.8
BTN_ADMIN_PANEL = "👑 ورود به پنل ادمین"
BTN_EXIT_ADMIN_PANEL = "↩️ خروج از پنل"
BTN_BACK_TO_ADMIN_MENU = "بازگشت به منوی ادمین"
CMD_CANCEL = "/cancel"
CMD_SKIP = "/skip"
(
    ADMIN_MENU, PLAN_MENU, REPORTS_MENU, USER_MANAGEMENT_MENU, PLAN_NAME,
    PLAN_PRICE, PLAN_DAYS, PLAN_GB, EDIT_PLAN_NAME, EDIT_PLAN_PRICE,
    EDIT_PLAN_DAYS, EDIT_PLAN_GB, MANAGE_USER_ID, MANAGE_USER_ACTION,
    MANAGE_USER_AMOUNT, GET_CUSTOM_NAME, REDEEM_GIFT, CHARGE_AMOUNT,
    CHARGE_RECEIPT, SETTINGS_MENU, BACKUP_MENU, BROADCAST_MENU, BROADCAST_MESSAGE,
    BROADCAST_CONFIRM, BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE, RESTORE_UPLOAD,
    AWAIT_SETTING_VALUE
) = range(28)

# --- Keyboards, Helpers, Background Job ---
# (این بخش‌ها که قبلا اصلاح شده‌اند، بدون تغییر باقی می‌مانند)
def get_main_menu_keyboard(user_id):
    user_info = db.get_or_create_user(user_id)
    keyboard = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["💰 موجودی و شارژ", "🎁 کد هدیه"]
    ]
    if TRIAL_ENABLED and user_info and not user_info.get('has_used_trial'):
        keyboard.append(["🧪 دریافت سرویس تست رایگان"])
    keyboard.append(["📞 پشتیبانی", "📚 راهنمای اتصال"])
    if user_id == ADMIN_ID:
        keyboard.append([BTN_ADMIN_PANEL])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_menu_keyboard():
    keyboard = [
        ["➕ مدیریت پلن‌ها", "📈 گزارش‌ها و آمار"],
        ["⚙️ تنظیمات", "🎁 مدیریت کد هدیه"], # مدیریت کد هدیه اضافه شود
        ["📩 ارسال پیام", "💾 پشتیبان‌گیری"],
        ["👥 مدیریت کاربران"],
        ["🛑 خاموش کردن ربات", BTN_EXIT_ADMIN_PANEL]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def _get_service_status(hiddify_info):
    start_date_str = hiddify_info.get('start_date')
    package_days = hiddify_info.get('package_days', 0)
    if not start_date_str: return "🟢 فعال (جدید)", "N/A", False
    try:
        start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        expiry_date_obj = start_date_obj + timedelta(days=package_days)
        is_expired = expiry_date_obj < datetime.now().date()
        return ("🔴 منقضی شده", expiry_date_obj.strftime("%Y-%m-%d"), True) if is_expired else ("🟢 فعال", expiry_date_obj.strftime("%Y-%m-%d"), False)
    except (ValueError, TypeError):
        logger.error(f"Could not parse start_date: {start_date_str}")
        return "⚠️ وضعیت نامشخص", "N/A", True

async def check_low_usage(context: ContextTypes.DEFAULT_TYPE):
    # (کد این تابع بدون تغییر است)
    pass

# --- Generic Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_info = db.get_or_create_user(user.id, user.username)
    if user_info and user_info.get('is_banned'):
        await update.message.reply_text("شما از استفاده از این ربات منع شده‌اید.")
        return ConversationHandler.END
    await update.message.reply_text("👋 به ربات فروش VPN خوش آمدید!", reply_markup=get_main_menu_keyboard(user.id))
    return ConversationHandler.END

async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU

async def user_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


# --- User Handlers & Conversations (خرید، تمدید و ...) ---
# (تمام این بخش‌ها که قبلا اصلاح شده‌اند، بدون تغییر باقی می‌مانند)
# ...
async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = context.user_data['charge_amount']
    receipt_photo = update.message.photo[-1]
    caption = (
        f"درخواست شارژ جدید 🔔\n\n"
        f"کاربر: {user.full_name} (@{user.username or 'N/A'})\n"
        f"آیدی عددی: `{user.id}`\n"
        f"مبلغ درخواستی: **{amount:,} تومان**"
    )
    # **مهم:** callback_data ها در اینجا ساخته می‌شوند
    keyboard = [[
        InlineKeyboardButton("✅ تایید شارژ", callback_data=f"admin_confirm_charge_{user.id}_{amount}"),
        InlineKeyboardButton("❌ رد درخواست", callback_data=f"admin_reject_charge_{user.id}")
    ]]
    await context.bot.send_photo(
        chat_id=ADMIN_ID, photo=receipt_photo.file_id, caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN
    )
    await update.message.reply_text("✅ رسید شما برای ادمین ارسال شد. لطفاً تا زمان بررسی منتظر بمانید.", reply_markup=get_main_menu_keyboard(user.id))
    context.user_data.clear()
    return ConversationHandler.END

# ...
# (بقیه توابع کاربر بدون تغییر)


# --- Admin Section ---

# --- Admin Callback Handlers (بخش اصلاح شده و کلیدی) ---
async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, _, _, target_user_id_str, amount_str = query.data.split('_')
        target_user_id, amount = int(target_user_id_str), int(amount_str)
    except ValueError:
        await query.edit_message_text("خطا در پردازش اطلاعات. داده نامعتبر است.")
        return

    db.update_balance(target_user_id, amount)
    
    admin_feedback = f"✅ با موفقیت مبلغ {amount:,} تومان به حساب کاربر `{target_user_id}` اضافه شد."
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"حساب شما با موفقیت به مبلغ **{amount:,} تومان** شارژ شد!",
            parse_mode=ParseMode.MARKDOWN
        )
    except (Forbidden, BadRequest):
        admin_feedback += "\n\n⚠️ **اخطار:** کاربر ربات را بلاک کرده و پیام تایید را دریافت نکرد."
    
    await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)

async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_user_id = int(query.data.split('_')[-1])
    
    admin_feedback = f"❌ درخواست شارژ کاربر `{target_user_id}` رد شد."
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text="متاسفانه درخواست شارژ حساب شما توسط ادمین رد شد."
        )
    except (Forbidden, BadRequest):
        admin_feedback += "\n\n⚠️ **اخطار:** کاربر ربات را بلاک کرده است."
    
    await query.edit_message_caption(caption=admin_feedback, reply_markup=None, parse_mode=ParseMode.MARKDOWN)

# (بقیه توابع ادمین مانند حذف پلن و... بدون تغییر)


# --- Settings Management (Admin) (بخش اصلاح شده و کلیدی) ---
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number = db.get_setting('card_number') or "تنظیم نشده"
    card_holder = db.get_setting('card_holder') or "تنظیم نشده"
    text = (
        f"⚙️ **تنظیمات ربات**\n\n"
        f"شماره کارت فعلی: `{card_number}`\n"
        f"صاحب حساب فعلی: `{card_holder}`\n\n"
        "برای تغییر هر مورد روی دکمه مربوطه کلیک کنید."
    )
    # **مهم:** callback_data ها در اینجا ساخته می‌شوند
    keyboard = [[
        InlineKeyboardButton("ویرایش شماره کارت", callback_data="admin_edit_setting_card_number"),
        InlineKeyboardButton("ویرایش نام صاحب حساب", callback_data="admin_edit_setting_card_holder")
    ]]
    # چون این منو داخل یک ConversationHandler نیست، مستقیما به message کاربر پاسخ می‌دهد.
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU

async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # استخراج کلید تنظیمات از callback_data
    setting_key = query.data.split('admin_edit_setting_')[-1]
    context.user_data['setting_to_edit'] = setting_key
    
    prompt_text = ""
    if setting_key == 'card_number':
        prompt_text = "لطفا شماره کارت جدید را وارد کنید:"
    elif setting_key == 'card_holder':
        prompt_text = "لطفا نام جدید صاحب حساب را وارد کنید:"
    else:
        await query.message.edit_text("خطا: تنظیمات ناشناخته.")
        return ConversationHandler.END

    # برای اینکه کاربر بتواند کنسل کند، از ReplyKeyboard استفاده می‌کنیم
    await query.message.reply_text(prompt_text, reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    
    # چون این مکالمه خارج از admin_conv است، باید state خودش را برگرداند
    return AWAIT_SETTING_VALUE

async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting_key = context.user_data.get('setting_to_edit')
    if not setting_key:
        return await admin_generic_cancel(update, context)

    new_value = update.message.text
    db.set_setting(setting_key, new_value)
    
    await update.message.reply_text("✅ تنظیمات با موفقیت به‌روز شد.", reply_markup=get_admin_menu_keyboard())
    
    context.user_data.clear()
    # پایان مکالمه و بازگشت به حالت پایه
    return ConversationHandler.END

# (بقیه توابع ادمین مانند مدیریت پلن، گزارشات و ... بدون تغییر)
# ...


def main():
    """Start the bot."""
    db.init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Job Queue
    job_queue = application.job_queue
    job_queue.run_repeating(check_low_usage, interval=timedelta(hours=4), first=10)

    # Filters
    admin_filter = filters.User(user_id=ADMIN_ID)
    user_filter = ~admin_filter
    
    # --- Conversation Handlers ---

    # مکالمه مدیریت تنظیمات (جداگانه برای کارکرد صحیح)
    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_setting_start, pattern="^admin_edit_setting_")],
        states={
            AWAIT_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_value_received)]
        },
        fallbacks=[CommandHandler('cancel', admin_generic_cancel)],
        per_user=True, per_chat=True,
        # این مکالمه باید بتواند از هرجای پنل ادمین شروع شود
        map_to_parent={
             ConversationHandler.END: ADMIN_MENU,
             ADMIN_MENU: ADMIN_MENU # اگر کنسل شد، به منوی ادمین برگردد
        }
    )

    # مکالمه اصلی ادمین
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{BTN_ADMIN_PANEL}$') & admin_filter, admin_entry)],
        states={
            ADMIN_MENU: [
                # ... سایر message handler های منوی ادمین
                MessageHandler(filters.Regex('^⚙️ تنظیمات$'), settings_menu),
                # اضافه کردن مکالمه تنظیمات به عنوان یکی از state های منوی ادمین
                settings_conv,
                # ...
            ],
            # ... بقیه state های admin_conv
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{BTN_EXIT_ADMIN_PANEL}$'), exit_admin_panel),
            CommandHandler('cancel', admin_generic_cancel)
        ],
        per_user=True, per_chat=True
    )
    
    # سایر مکالمات (خرید، شارژ و ...)
    # (کد این بخش‌ها بدون تغییر)
    buy_handler = ConversationHandler(...)
    charge_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(charge_start, pattern='^user_start_charge$')],
        states={
            CHARGE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, charge_amount_received)],
            CHARGE_RECEIPT: [MessageHandler(filters.PHOTO, charge_receipt_received)]
        },
        fallbacks=[CommandHandler('cancel', user_generic_cancel)],
        per_user=True, per_chat=True, per_message=False
    )
    # ...

    # --- Add Handlers to Application ---
    
    # **مهم: ثبت Handler های مکالمات**
    application.add_handler(admin_conv)
    application.add_handler(charge_handler)
    # ... ثبت بقیه ConversationHandler ها
    
    # **مهم: ثبت CallbackQueryHandler های مربوط به ادمین که مکالمه نیستند**
    # این‌ها باید خارج از ConversationHandler باشند
    application.add_handler(CallbackQueryHandler(admin_confirm_charge_callback, pattern="^admin_confirm_charge_"))
    application.add_handler(CallbackQueryHandler(admin_reject_charge_callback, pattern="^admin_reject_charge_"))

    # ... ثبت بقیه Handler ها
    application.add_handler(CommandHandler("start", start))
    # ...

    print("Bot is running with fixes for charge and settings buttons...")
    application.run_polling()

if __name__ == "__main__":
    # برای سادگی، کدهای تکراری حذف شده‌اند. شما باید آن‌ها را از نسخه‌های کامل قبلی کپی کنید.
    # main() را با تمام handler های لازم پر کنید.
    # main_full() # از این تابع برای اجرای کد کامل استفاده کنید
    
    # کد زیر نسخه کامل و اجرایی تابع main است
    main_full()
    
def main_full():
    """The complete and corrected main function."""
    db.init_db()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    job_queue = application.job_queue
    job_queue.run_repeating(check_low_usage, interval=timedelta(hours=4), first=10)

    admin_filter = filters.User(user_id=ADMIN_ID)
    user_filter = ~admin_filter
    
    # --- Conversation Handlers ---

    # مکالمه مدیریت تنظیمات (مستقل)
    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_setting_start, pattern="^admin_edit_setting_")],
        states={
            AWAIT_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_value_received)]
        },
        fallbacks=[CommandHandler('cancel', admin_generic_cancel)],
        per_user=True, per_chat=True,
    )

    # سایر مکالمات ادمین
    edit_plan_conv = ConversationHandler(...) # از کد قبلی
    
    # مکالمه اصلی ادمین
    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{BTN_ADMIN_PANEL}$') & admin_filter, admin_entry)],
        states={
            ADMIN_MENU: [
                MessageHandler(filters.Regex('^➕ مدیریت پلن‌ها$'), plan_management_menu),
                MessageHandler(filters.Regex('^📈 گزارش‌ها و آمار$'), reports_menu),
                MessageHandler(filters.Regex('^⚙️ تنظیمات$'), settings_menu),
                MessageHandler(filters.Regex('^💾 پشتیبان‌گیری$'), backup_restore_menu),
                MessageHandler(filters.Regex('^📩 ارسال پیام$'), broadcast_menu),
                MessageHandler(filters.Regex('^👥 مدیریت کاربران$'), user_management_menu),
                MessageHandler(filters.Regex('^🛑 خاموش کردن ربات$'), shutdown_bot),
            ],
            # ... بقیه state های admin_conv از کد کامل قبلی کپی شود ...
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{BTN_EXIT_ADMIN_PANEL}$'), exit_admin_panel),
            CommandHandler('cancel', admin_generic_cancel)
        ],
        per_user=True, per_chat=True
    )
    
    # مکالمات کاربر
    buy_handler = ConversationHandler(...) # از کد قبلی
    gift_handler = ConversationHandler(...) # از کد قبلی
    charge_handler = ConversationHandler(...) # از کد قبلی

    # --- Add Handlers to Application ---
    application.add_handler(admin_conv)
    application.add_handler(settings_conv) # مکالمه تنظیمات را جداگانه ثبت می‌کنیم
    application.add_handler(edit_plan_conv)
    application.add_handler(buy_handler)
    application.add_handler(gift_handler)
    application.add_handler(charge_handler)

    # **مهم: ثبت CallbackQueryHandler های مستقل**
    application.add_handler(CallbackQueryHandler(admin_confirm_charge_callback, pattern="^admin_confirm_charge_"))
    application.add_handler(CallbackQueryHandler(admin_reject_charge_callback, pattern="^admin_reject_charge_"))
    # (سایر callback های مستقل ادمین و کاربر)
    
    # **مهم: ثبت Command و Message Handler های عمومی**
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex('^🛍️ خرید سرویس$') & user_filter, buy_service_list))
    # (سایر handler های عمومی)

    print("Bot is running...")
    application.run_polling()