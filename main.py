# main.py

import os
import logging
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv, set_key

# --- تنظیمات اولیه ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
dotenv_path = '.env'
load_dotenv(dotenv_path)

try:
    TOKEN = os.getenv("TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except (TypeError, ValueError) as e:
    logger.error(f"خطا در خواندن TOKEN یا ADMIN_ID از فایل .env: {e}")
    exit("خطا: لطفاً فایل .env را با مقادیر صحیح پر کنید.")

CONFIGS_FILE = "configs.txt"
USED_CONFIGS_FILE = "used_configs.txt"
SERVICE_NAME = "vpn_bot.service"

bot = telebot.TeleBot(TOKEN)
user_states = {} # برای ذخیره وضعیت کاربر در فرآیندهای چندمرحله‌ای

# --- کیبوردها ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ افزودن کانفیگ"), KeyboardButton("📊 آمار"))
    markup.row(KeyboardButton("⚙️ تنظیمات پرداخت"), KeyboardButton("🔄 ریستارت ربات"))
    markup.row(KeyboardButton("🗑 حذف کامل ربات"))
    return markup

def get_settings_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.row(KeyboardButton("✏️ تغییر قیمت"), KeyboardButton("✏️ تغییر شماره کارت"))
    markup.row(KeyboardButton("✏️ تغییر نام صاحب حساب"))
    markup.row(KeyboardButton("⬅️ بازگشت به منوی اصلی"))
    return markup

def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("💳 خرید کانفیگ"))
    return markup

# --- توابع کمکی ---
def is_admin(message):
    return message.from_user.id == ADMIN_ID

def update_env_file(key, value):
    set_key(dotenv_path, key, value)
    logger.info(f"فایل .env به‌روز شد: {key}={value}")

def get_a_config():
    try:
        with open(CONFIGS_FILE, 'r') as f: configs = [l.strip() for l in f if l.strip()]
        if not configs: return None
        user_config = configs.pop(0)
        with open(USED_CONFIGS_FILE, 'a') as f: f.write(user_config + '\n')
        with open(CONFIGS_FILE, 'w') as f: f.writelines([c + '\n' for c in configs])
        return user_config
    except FileNotFoundError:
        open(CONFIGS_FILE, 'w').close()
        return None

# --- دستورات اصلی ربات ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_admin(message):
        bot.send_message(message.chat.id, "سلام ادمین عزیز! به پنل مدیریت پیشرفته خوش آمدید.", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.chat.id, "سلام! برای خرید کانفیگ VPN از دکمه زیر استفاده کنید.", reply_markup=get_user_keyboard())

# --- مدیریت پیام‌های کاربر ---
@bot.message_handler(func=lambda m: not is_admin(m))
def handle_user_messages(message):
    if message.text == "💳 خرید کانفیگ":
        price = os.getenv("CONFIG_PRICE", "N/A")
        card_number = os.getenv("CARD_NUMBER", "N/A")
        card_holder = os.getenv("CARD_HOLDER", "N/A")
        payment_info = (
            f"✅ **برای خرید، لطفاً مبلغ {price} تومان به کارت زیر واریز کنید:**\n\n"
            f"💳 شماره کارت:\n`{card_number}`\n"
            f"👤 نام صاحب حساب: **{card_holder}**\n\n"
            f"پس از واریز، لطفاً از رسید پرداخت یک **اسکرین‌شات** گرفته و ارسال کنید."
        )
        bot.send_message(message.chat.id, payment_info, parse_mode="Markdown")
    
    elif message.content_type in ['photo', 'document']:
        user = message.from_user
        caption = (f" رسید جدید از:\n"
                   f"👤 نام: {user.first_name}\n"
                   f"🆔 یوزرنیم: @{user.username}\n"
                   f"🔢 آیدی: `{user.id}`\n\n"
                   f"برای تایید، روی دکمه زیر کلیک کنید.")
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("✅ تایید و ارسال کانفیگ", callback_data=f"approve_{user.id}"))
        bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
        bot.send_message(ADMIN_ID, caption, reply_markup=markup, parse_mode="Markdown")
        bot.reply_to(message, "✅ رسید شما برای ادمین ارسال شد. لطفاً منتظر بمانید.")

# --- مدیریت دکمه تایید ادمین ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_payment(call):
    if not call.from_user.id == ADMIN_ID: return
    try:
        user_id = int(call.data.split('_')[1])
        config = get_a_config()
        if config:
            bot.send_message(user_id, "✅ پرداخت شما تایید شد! کانفیگ شما:")
            bot.send_message(user_id, f"`{config}`", parse_mode="Markdown")
            bot.edit_message_text("✅ کانفیگ برای کاربر ارسال شد.", call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "خطا: هیچ کانفیگی موجود نیست!", show_alert=True)
    except Exception as e:
        logger.error(f"خطا در تایید پرداخت: {e}")

# --- مدیریت پیام‌های ادمین ---
@bot.message_handler(func=is_admin)
def handle_admin_messages(message):
    chat_id = message.chat.id
    user_states.pop(chat_id, None) # پاک کردن وضعیت قبلی

    if message.text == "➕ افزودن کانفیگ":
        msg = bot.send_message(chat_id, "کانفیگ‌ها را ارسال کنید (هر کدام در یک خط).")
        bot.register_next_step_handler(msg, save_new_configs)
    
    elif message.text == "📊 آمار":
        try:
            with open(CONFIGS_FILE, 'r') as f: available = len([l for l in f if l.strip()])
        except FileNotFoundError: available = 0
        try:
            with open(USED_CONFIGS_FILE, 'r') as f: used = len([l for l in f if l.strip()])
        except FileNotFoundError: used = 0
        bot.send_message(chat_id, f"🟢 موجود: {available}\n🔴 فروخته شده: {used}")
    
    elif message.text == "⚙️ تنظیمات پرداخت":
        current_price = os.getenv('CONFIG_PRICE')
        current_card = os.getenv('CARD_NUMBER')
        current_holder = os.getenv('CARD_HOLDER')
        settings_text = (f"**تنظیمات فعلی پرداخت:**\n\n"
                         f"▫️ قیمت: {current_price} تومان\n"
                         f"▫️ شماره کارت: {current_card}\n"
                         f"▫️ نام صاحب حساب: {current_holder}")
        bot.send_message(chat_id, settings_text, reply_markup=get_settings_keyboard(), parse_mode="Markdown")
    
    elif message.text == "🔄 ریستارت ربات":
        bot.send_message(chat_id, "در حال ری‌استارت کردن سرویس ربات...")
        result = os.system(f"systemctl restart {SERVICE_NAME}")
        if result == 0:
            bot.send_message(chat_id, "✅ سرویس ربات با موفقیت ری‌استارت شد.")
        else:
            bot.send_message(chat_id, "❌ خطایی در ری‌استارت کردن سرویس رخ داد. لاگ‌ها را بررسی کنید.")

    elif message.text == "🗑 حذف کامل ربات":
        msg = bot.send_message(chat_id, "🚨 **اخطار!** 🚨\nاین عمل غیرقابل بازگشت است و تمام فایل‌های ربات و سرویس آن را از سرور حذف می‌کند. برای تایید، عبارت `DELETE` را ارسال کنید.", parse_mode="Markdown")
        bot.register_next_step_handler(msg, confirm_full_delete)

    elif message.text == "⬅️ بازگشت به منوی اصلی":
        bot.send_message(chat_id, "به منوی اصلی بازگشتید.", reply_markup=get_admin_keyboard())

    # مدیریت دکمه‌های تنظیمات
    elif message.text.startswith("✏️"):
        if "قیمت" in message.text:
            user_states[chat_id] = "setting_price"
            bot.send_message(chat_id, "لطفاً قیمت جدید را وارد کنید (مثلا: 60,000):")
        elif "شماره کارت" in message.text:
            user_states[chat_id] = "setting_card_number"
            bot.send_message(chat_id, "لطفاً شماره کارت جدید را وارد کنید:")
        elif "نام صاحب حساب" in message.text:
            user_states[chat_id] = "setting_card_holder"
            bot.send_message(chat_id, "لطفاً نام جدید صاحب حساب را وارد کنید:")

# --- مدیریت فرآیندهای چندمرحله‌ای ادمین ---
@bot.message_handler(func=lambda message: is_admin(message) and user_states.get(message.chat.id))
def handle_admin_states(message):
    chat_id = message.chat.id
    state = user_states.pop(chat_id)
    
    if state == "setting_price":
        update_env_file("CONFIG_PRICE", message.text)
        bot.send_message(chat_id, f"✅ قیمت با موفقیت به '{message.text}' تغییر یافت.", reply_markup=get_admin_keyboard())
    elif state == "setting_card_number":
        update_env_file("CARD_NUMBER", message.text)
        bot.send_message(chat_id, f"✅ شماره کارت با موفقیت تغییر یافت.", reply_markup=get_admin_keyboard())
    elif state == "setting_card_holder":
        update_env_file("CARD_HOLDER", message.text)
        bot.send_message(chat_id, f"✅ نام صاحب حساب با موفقیت تغییر یافت.", reply_markup=get_admin_keyboard())

def save_new_configs(message):
    new_configs = [line.strip() for line in message.text.split('\n') if line.strip()]
    if new_configs:
        with open(CONFIGS_FILE, 'a') as f:
            for config in new_configs: f.write(config + '\n')
        bot.send_message(message.chat.id, f"✅ تعداد {len(new_configs)} کانفیگ جدید اضافه شد.")
    else: bot.send_message(message.chat.id, "هیچ کانفیگ معتبری ارسال نشد.")

def confirm_full_delete(message):
    if message.text == "DELETE":
        bot.send_message(message.chat.id, "در حال حذف کامل ربات از سرور...")
        # اجرای یک اسکریپت جداگانه برای حذف، چون خود ربات نمی‌تواند خودش را حذف کند
        os.system("bash uninstall.sh &")
    else:
        bot.send_message(message.chat.id, "عملیات حذف لغو شد.", reply_markup=get_admin_keyboard())

# --- شروع به کار ربات ---
if __name__ == "__main__":
    logger.info("ربات در حال اجرا است (نسخه با پنل مدیریت کامل)...")
    bot.polling(none_stop=True)