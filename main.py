# main.py

import os
import sqlite3
import logging
import datetime
import shutil
import zipfile
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, abort
from zarinpal.zarinpal import ZarinPal  # <--- تغییر در import
from dotenv import load_dotenv

# --- تنظیمات لاگ‌گیری ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- بارگذاری متغیرها ---
load_dotenv()
try:
    TOKEN = os.getenv("TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
    MERCHANT_ID = os.getenv("MERCHANT_ID")
    SERVER_URL = os.getenv("SERVER_URL")
    CONFIG_PRICE = int(os.getenv("CONFIG_PRICE"))
    if not all([TOKEN, ADMIN_ID, MERCHANT_ID, SERVER_URL, CONFIG_PRICE]):
        raise ValueError("یکی از متغیرهای محیطی مقداردهی نشده است.")
except (TypeError, ValueError) as e:
    logger.error(f"خطا در خواندن متغیرهای محیطی: {e}")
    exit("خطا: لطفاً فایل .env را با مقادیر صحیح پر کنید.")

# --- تنظیمات و ثابت‌ها ---
CONFIGS_FILE = "configs.txt"
USED_CONFIGS_FILE = "used_configs.txt"
DB_FILE = "payments.db"
WEBHOOK_PATH = f'/webhook/{TOKEN}'
WEBHOOK_URL = f'{SERVER_URL.strip("/")}{WEBHOOK_PATH}'
CALLBACK_URL = f'{SERVER_URL.strip("/")}/verify_payment'

# --- ساخت نمونه‌ها ---
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
# <--- تغییر در ساخت نمونه زرین‌پال
zarinpal = ZarinPal(MERCHANT_ID)

# --- (کدهای دیگر مانند init_db, کیبوردها و توابع کمکی بدون تغییر باقی می‌مانند) ---
def init_db():
    for file in [CONFIGS_FILE, USED_CONFIGS_FILE]:
        if not os.path.exists(file): open(file, 'w').close()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            authority TEXT NOT NULL UNIQUE, amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending', ref_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("پایگاه داده با موفقیت مقداردهی اولیه شد.")

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ افزودن کانفیگ"), KeyboardButton("📊 آمار"))
    markup.row(KeyboardButton("📥 بکاپ گرفتن"), KeyboardButton("📤 ریستور کردن"))
    markup.row(KeyboardButton("⚠️ ریست کامل ربات ⚠️"))
    return markup

def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton(f"💳 خرید کانفیگ ({CONFIG_PRICE:,} تومان)"))
    return markup

def is_admin(message): return message.from_user.id == ADMIN_ID

def get_a_config():
    try:
        with open(CONFIGS_FILE, 'r') as f: configs = [line.strip() for line in f if line.strip()]
        if not configs: return None
        user_config = configs.pop(0)
        with open(USED_CONFIGS_FILE, 'a') as f: f.write(user_config + '\n')
        with open(CONFIGS_FILE, 'w') as f: f.writelines([c + '\n' for c in configs])
        return user_config
    except FileNotFoundError: return None


# --- روت‌های Flask ---
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else: abort(403)

# <--- بخش تایید پرداخت با منطق جدید ---
@app.route('/verify_payment')
def verify_payment():
    authority = request.args.get('Authority')
    status = request.args.get('Status')
    if not authority or not status: return "<h1>اطلاعات پرداخت ناقص است.</h1>", 400
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, amount, status FROM payments WHERE authority = ?", (authority,))
    payment_record = cursor.fetchone()
    if not payment_record:
        conn.close()
        return "<h1>تراکنش نامعتبر است.</h1>", 404
    user_id, amount, db_status = payment_record
    if db_status == 'completed':
        conn.close()
        bot.send_message(user_id, "شما قبلاً برای این تراکنش کانفیگ خود را دریافت کرده‌اید.")
        return "<h1>این تراکنش قبلاً با موفقیت تایید شده است.</h1>"
    
    if status == 'OK':
        # <--- تغییر در متد و بررسی خروجی
        result = zarinpal.payment_verification(amount, authority)
        if result['status'] == 100 or result['status'] == 101: # 101 یعنی تراکنش قبلا وریفای شده
            config = get_a_config()
            ref_id = result['ref_id']
            if config:
                cursor.execute("UPDATE payments SET status = 'completed', ref_id = ? WHERE authority = ?", (str(ref_id), authority))
                conn.commit()
                bot.send_message(user_id, f"✅ پرداخت شما با موفقیت تایید شد.\nکد رهگیری: `{ref_id}`")
                bot.send_message(user_id, "کانفیگ شما آماده است:")
                bot.send_message(user_id, f"`{config}`", parse_mode="Markdown")
                return "<h1>پرداخت با موفقیت انجام شد. لطفاً به ربات تلگرام بازگردید.</h1>"
            else:
                bot.send_message(user_id, "پرداخت شما موفق بود اما کانفیگی موجود نیست. لطفاً به ادمین اطلاع دهید.")
                return "<h1>پرداخت موفق بود، اما کانفیگی موجود نیست.</h1>"
        else:
            bot.send_message(user_id, f"❌ تایید پرداخت ناموفق بود. کد خطا: {result['status']}")
            return "<h1>تایید پرداخت ناموفق بود.</h1>"
    else:
        bot.send_message(user_id, "❌ شما پرداخت را لغو کردید.")
        return "<h1>پرداخت توسط شما لغو شد.</h1>"
    conn.close()

# --- دستورات تلگرام (بخش مدیریت کاربر) ---
@bot.message_handler(func=lambda message: not is_admin(message))
def handle_user_messages(message):
    if message.text.startswith("💳 خرید کانفیگ"):
        # <--- تغییر در متد و بررسی خروجی
        result = zarinpal.payment_request(
            amount=CONFIG_PRICE,
            description=f"خرید سرویس VPN برای کاربر {message.from_user.id}",
            callback_url=CALLBACK_URL
        )
        if result['status'] == 100 and result['url']:
            authority = result['authority']
            link = result['url']
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO payments (user_id, authority, amount) VALUES (?, ?, ?)",
                           (message.from_user.id, authority, CONFIG_PRICE))
            conn.commit()
            conn.close()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🚀 پرداخت و دریافت کانفیگ 🚀", url=link))
            bot.send_message(message.chat.id, "برای تکمیل خرید روی دکمه زیر کلیک کنید:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "خطایی در اتصال به درگاه پرداخت رخ داد. لطفاً بعداً تلاش کنید.")

# --- (بخش مدیریت ادمین و سایر توابع بدون تغییر باقی می‌مانند) ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_admin(message):
        bot.send_message(message.chat.id, "سلام ادمین عزیز!", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.chat.id, "سلام! برای خرید کانفیگ از دکمه زیر استفاده کنید.", reply_markup=get_user_keyboard())

@bot.message_handler(func=is_admin)
def handle_admin_messages(message):
    if message.text == "➕ افزودن کانفیگ":
        msg = bot.reply_to(message, "کانفیگ‌ها را ارسال کنید.")
        bot.register_next_step_handler(msg, save_new_configs)
    elif message.text == "📊 آمار":
        try:
            with open(CONFIGS_FILE, 'r') as f: available = len([l for l in f if l.strip()])
        except FileNotFoundError: available = 0
        try:
            with open(USED_CONFIGS_FILE, 'r') as f: used = len([l for l in f if l.strip()])
        except FileNotFoundError: used = 0
        bot.send_message(message.chat.id, f"🟢 موجود: {available}\n🔴 فروخته شده: {used}")
    elif message.text == "📥 بکاپ گرفتن": backup_data(message.chat.id)
    elif message.text == "📤 ریستور کردن":
        msg = bot.send_message(message.chat.id, "فایل بکاپ (.zip) را ارسال کنید.")
        bot.register_next_step_handler(msg, restore_data_step1)
    elif message.text == "⚠️ ریست کامل ربات ⚠️": ask_for_reset_confirmation(message)

def save_new_configs(message):
    # ... (بدون تغییر)
    new_configs = [line.strip() for line in message.text.split('\n') if line.strip()]
    if not new_configs:
        bot.send_message(message.chat.id, "هیچ کانفیگ معتبری ارسال نشد.")
        return
    with open(CONFIGS_FILE, 'a') as f:
        for config in new_configs: f.write(config + '\n')
    bot.send_message(message.chat.id, f"✅ {len(new_configs)} کانفیگ جدید اضافه شد.")

def backup_data(chat_id):
    # ... (بدون تغییر)
    bot.send_message(chat_id, "در حال ایجاد فایل بکاپ...")
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_zip_path = f'backup_{timestamp}.zip'
        with zipfile.ZipFile(backup_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in [DB_FILE, CONFIGS_FILE, USED_CONFIGS_FILE]:
                if os.path.exists(file): zipf.write(file, arcname=os.path.basename(file))
        with open(backup_zip_path, 'rb') as backup_file: bot.send_document(chat_id, backup_file)
    except Exception as e: bot.send_message(chat_id, f"❌ خطا: {e}")
    finally:
        if 'backup_zip_path' in locals() and os.path.exists(backup_zip_path): os.remove(backup_zip_path)

def restore_data_step1(message):
    # ... (بدون تغییر)
    try:
        if not message.document or message.document.mime_type not in ['application/zip', 'application/x-zip-compressed']:
            bot.reply_to(message, "❌ فایل نامعتبر است.", reply_markup=get_admin_keyboard())
            return
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open('received_backup.zip', 'wb') as f: f.write(downloaded_file)
        with zipfile.ZipFile('received_backup.zip', 'r') as zip_ref: zip_ref.extractall('.')
        bot.send_message(message.chat.id, "✅ داده‌ها بازیابی شدند. ربات را ری‌استارت کنید.", reply_markup=get_admin_keyboard())
    except Exception as e: bot.send_message(message.chat.id, f"❌ خطا: {e}", reply_markup=get_admin_keyboard())
    finally:
        if os.path.exists('received_backup.zip'): os.remove('received_backup.zip')

def ask_for_reset_confirmation(message):
    # ... (بدون تغییر)
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("✅ بله، مطمئنم!"), KeyboardButton("❌ خیر"))
    bot.send_message(message.chat.id, "🚨 **اخطار** 🚨\nآیا از پاک کردن تمام داده‌ها مطمئن هستید؟", reply_markup=markup, parse_mode="Markdown")
    bot.register_next_step_handler(message, confirm_full_reset)

def confirm_full_reset(message):
    # ... (بدون تغییر)
    if message.text.startswith("✅"):
        for f in [DB_FILE, CONFIGS_FILE, USED_CONFIGS_FILE]:
            if os.path.exists(f): os.remove(f)
        init_db()
        bot.send_message(message.chat.id, "✅ ربات ریست شد.", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.chat.id, "عملیات لغو شد.", reply_markup=get_admin_keyboard())

if __name__ == "__main__":
    init_db()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to: {WEBHOOK_URL}")