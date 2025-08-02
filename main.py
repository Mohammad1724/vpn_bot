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
from zarinpal_requests import ZarinPal
from dotenv import load_dotenv

# --- تنظیمات لاگ‌گیری برای دیباگ بهتر ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- بارگذاری متغیرها از فایل .env ---
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
    logger.error(f"خطا در خواندن متغیرهای محیطی از فایل .env: {e}")
    exit("خطا: لطفاً فایل .env را با مقادیر صحیح پر کنید.")

# --- تنظیمات و ثابت‌ها ---
CONFIGS_FILE = "configs.txt"
USED_CONFIGS_FILE = "used_configs.txt"
DB_FILE = "payments.db"
WEBHOOK_PATH = f'/webhook/{TOKEN}'
WEBHOOK_URL = f'{SERVER_URL.strip("/")}{WEBHOOK_PATH}'
CALLBACK_URL = f'{SERVER_URL.strip("/")}/verify_payment'

# --- ساخت نمونه‌ها (Instances) ---
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
zarinpal = ZarinPal(MERCHANT_ID, is_sandbox=False) # برای درگاه واقعی is_sandbox=False باشد

# --- مدیریت پایگاه داده و فایل‌ها ---
def init_db():
    """پایگاه داده و فایل‌های کانفیگ را در صورت عدم وجود، ایجاد می‌کند."""
    for file in [CONFIGS_FILE, USED_CONFIGS_FILE]:
        if not os.path.exists(file):
            open(file, 'w').close()
            logger.info(f"فایل '{file}' ایجاد شد.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            authority TEXT NOT NULL UNIQUE,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            ref_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("پایگاه داده با موفقیت مقداردهی اولیه شد.")

# --- کیبوردهای تلگرام ---
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

# --- توابع کمکی ---
def is_admin(message):
    return message.from_user.id == ADMIN_ID

def get_a_config():
    """یک کانفیگ از فایل خوانده، آن را به فایل استفاده شده‌ها منتقل و سپس برمی‌گرداند."""
    try:
        with open(CONFIGS_FILE, 'r') as f:
            configs = [line.strip() for line in f if line.strip()]
        
        if not configs:
            logger.warning("درخواست کانفیگ داده شد، اما هیچ کانفیگی در configs.txt موجود نیست.")
            return None
        
        user_config = configs.pop(0)
        
        with open(USED_CONFIGS_FILE, 'a') as f:
            f.write(user_config + '\n')
        
        with open(CONFIGS_FILE, 'w') as f:
            f.writelines([c + '\n' for c in configs])
            
        logger.info(f"یک کانفیگ با موفقیت تخصیص داده شد.")
        return user_config
    except FileNotFoundError:
        logger.error(f"فایل {CONFIGS_FILE} پیدا نشد، هرچند باید خودکار ساخته می‌شد.")
        return None

# --- روت‌های Flask برای Webhook و درگاه پرداخت ---
@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        abort(403)

@app.route('/verify_payment')
def verify_payment():
    authority = request.args.get('Authority')
    status = request.args.get('Status')

    if not authority or not status:
        return "<h1>اطلاعات پرداخت ناقص است.</h1>", 400

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
        is_ok, ref_id = zarinpal.verify(amount, authority)
        if is_ok:
            config = get_a_config()
            if config:
                cursor.execute("UPDATE payments SET status = 'completed', ref_id = ? WHERE authority = ?", (str(ref_id), authority))
                conn.commit()
                bot.send_message(user_id, f"✅ پرداخت شما با موفقیت تایید شد.\nکد رهگیری: `{ref_id}`")
                bot.send_message(user_id, "کانفیگ شما آماده است. برای کپی روی آن کلیک کنید:")
                bot.send_message(user_id, f"`{config}`", parse_mode="Markdown")
                logger.info(f"پرداخت موفق برای کاربر {user_id} با کد رهگیری {ref_id}.")
                return "<h1>پرداخت با موفقیت انجام شد. لطفاً به ربات تلگرام بازگردید.</h1>"
            else:
                bot.send_message(user_id, "پرداخت شما موفق بود اما متاسفانه در حال حاضر کانفیگی موجود نیست. لطفاً این موضوع را فوراً به ادمین اطلاع دهید تا کانفیگ شما را دستی تحویل دهد.")
                logger.critical(f"پرداخت موفق برای کاربر {user_id} اما کانفیگی برای تحویل موجود نبود!")
                return "<h1>پرداخت موفق بود، اما کانفیگی موجود نیست. به ادمین اطلاع دهید.</h1>"
        else:
            cursor.execute("UPDATE payments SET status = 'failed' WHERE authority = ?", (authority,))
            conn.commit()
            bot.send_message(user_id, "❌ خطایی در تایید پرداخت شما رخ داد. اگر پولی از حساب شما کسر شده، طی ۷۲ ساعت آینده باز خواهد گشت.")
            return "<h1>تایید پرداخت ناموفق بود.</h1>"
    else:
        cursor.execute("UPDATE payments SET status = 'cancelled' WHERE authority = ?", (authority,))
        conn.commit()
        bot.send_message(user_id, "❌ شما پرداخت را لغو کردید.")
        return "<h1>پرداخت توسط شما لغو شد.</h1>"
    
    conn.close()

# --- دستورات و پیام‌های تلگرام ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_admin(message):
        bot.send_message(message.chat.id, "سلام ادمین عزیز! به پنل مدیریت خوش آمدید.", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.chat.id, "سلام! برای خرید کانفیگ VPN از دکمه زیر استفاده کنید.", reply_markup=get_user_keyboard())

# --- مدیریت پیام‌های ادمین ---
@bot.message_handler(func=is_admin)
def handle_admin_messages(message):
    if message.text == "➕ افزودن کانفیگ":
        msg = bot.reply_to(message, "لطفاً کانفیگ یا کانفیگ‌های جدید را ارسال کنید (هر کدام در یک خط جداگانه).")
        bot.register_next_step_handler(msg, save_new_configs)
    
    elif message.text == "📊 آمار":
        try:
            with open(CONFIGS_FILE, 'r') as f: available_count = len([line for line in f if line.strip()])
        except FileNotFoundError: available_count = 0
        try:
            with open(USED_CONFIGS_FILE, 'r') as f: used_count = len([line for line in f if line.strip()])
        except FileNotFoundError: used_count = 0
        bot.send_message(message.chat.id, f"📊 **آمار کانفیگ‌ها** 📊\n\n🟢 کانفیگ‌های موجود: {available_count}\n🔴 کانفیگ‌های فروخته شده: {used_count}", parse_mode="Markdown")
    
    elif message.text == "📥 بکاپ گرفتن":
        backup_data(message.chat.id)

    elif message.text == "📤 ریستور کردن":
        msg = bot.send_message(message.chat.id, "لطفاً فایل بکاپ (.zip) خود را برای بازیابی ارسال کنید.")
        bot.register_next_step_handler(msg, restore_data_step1)
        
    elif message.text == "⚠️ ریست کامل ربات ⚠️":
        ask_for_reset_confirmation(message)

def save_new_configs(message):
    new_configs = [line.strip() for line in message.text.split('\n') if line.strip()]
    if not new_configs:
        bot.send_message(message.chat.id, "هیچ کانفیگ معتبری ارسال نشد.")
        return
    with open(CONFIGS_FILE, 'a') as f:
        for config in new_configs: f.write(config + '\n')
    bot.send_message(message.chat.id, f"✅ تعداد {len(new_configs)} کانفیگ جدید با موفقیت اضافه شد.")
    logger.info(f"ادمین {len(new_configs)} کانفیگ جدید اضافه کرد.")

# --- توابع مدیریتی پیشرفته ---
def backup_data(chat_id):
    bot.send_message(chat_id, "در حال ایجاد فایل بکاپ... لطفاً کمی صبر کنید.")
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename_base = f'backup_{timestamp}'
        backup_zip_path = f'{backup_filename_base}.zip'
        
        with zipfile.ZipFile(backup_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in [DB_FILE, CONFIGS_FILE, USED_CONFIGS_FILE]:
                if os.path.exists(file):
                    zipf.write(file, arcname=os.path.basename(file))
        
        if os.path.exists(backup_zip_path):
            with open(backup_zip_path, 'rb') as backup_file:
                bot.send_document(chat_id, backup_file, caption=f"✅ بکاپ با موفقیت ایجاد شد.")
            logger.info(f"بکاپ با نام {backup_zip_path} ایجاد و برای ادمین ارسال شد.")
        else:
            raise FileNotFoundError("فایل بکاپ ایجاد نشد.")
            
    except Exception as e:
        logger.error(f"خطا در ایجاد بکاپ: {e}")
        bot.send_message(chat_id, f"❌ خطایی در هنگام ایجاد بکاپ رخ داد: {e}")
    finally:
        if 'backup_zip_path' in locals() and os.path.exists(backup_zip_path):
            os.remove(backup_zip_path)

def restore_data_step1(message):
    try:
        if not message.document or message.document.mime_type not in ['application/zip', 'application/x-zip-compressed']:
            bot.reply_to(message, "❌ فایل ارسالی معتبر نیست. لطفاً یک فایل بکاپ با فرمت .zip ارسال کنید.", reply_markup=get_admin_keyboard())
            return
            
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        backup_zip_path = 'received_backup.zip'
        with open(backup_zip_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        with zipfile.ZipFile(backup_zip_path, 'r') as zip_ref:
            zip_ref.extractall('.')
            
        bot.send_message(message.chat.id, "✅ داده‌ها با موفقیت بازیابی شدند.\nبرای اعمال کامل تغییرات، لطفاً ربات را روی سرور ری‌استارت کنید.", reply_markup=get_admin_keyboard())
        logger.warning(f"ربات از فایل بکاپ ارسالی توسط ادمین ریستور شد.")
        
    except Exception as e:
        logger.error(f"خطا در بازیابی داده‌ها: {e}")
        bot.send_message(message.chat.id, f"❌ خطایی در هنگام بازیابی داده‌ها رخ داد: {e}", reply_markup=get_admin_keyboard())
    finally:
        if os.path.exists('received_backup.zip'):
            os.remove('received_backup.zip')

def ask_for_reset_confirmation(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("✅ بله، مطمئنم! همه چیز را پاک کن"), KeyboardButton("❌ خیر، منصرف شدم"))
    bot.send_message(message.chat.id, 
                     "🚨 **اخطار بسیار مهم** 🚨\n\nآیا مطمئن هستید که می‌خواهید تمام داده‌های ربات را پاک کنید؟ این عمل **غیرقابل بازگشت** است و تمام سوابق پرداخت و کانفیگ‌ها را حذف می‌کند.",
                     reply_markup=markup, parse_mode="Markdown")
    bot.register_next_step_handler(message, confirm_full_reset)

def confirm_full_reset(message):
    if message.text.startswith("✅"):
        try:
            for f in [DB_FILE, CONFIGS_FILE, USED_CONFIGS_FILE]:
                if os.path.exists(f): os.remove(f)
            init_db()
            bot.send_message(message.chat.id, "✅ تمام داده‌های ربات با موفقیت پاک شد. ربات به تنظیمات اولیه بازگشت.", reply_markup=get_admin_keyboard())
            logger.critical("ادمین ربات را به طور کامل ریست کرد.")
        except Exception as e:
            logger.error(f"خطا در هنگام ریست کامل: {e}")
            bot.send_message(message.chat.id, f"❌ خطایی در هنگام پاک‌سازی داده‌ها رخ داد: {e}", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.chat.id, "عملیات ریست لغو شد.", reply_markup=get_admin_keyboard())

# --- مدیریت پیام‌های کاربر ---
@bot.message_handler(func=lambda message: not is_admin(message))
def handle_user_messages(message):
    if message.text.startswith("💳 خرید کانفیگ"):
        is_ok, authority, link = zarinpal.payment_request(
            amount=CONFIG_PRICE,
            callback_url=CALLBACK_URL,
            description=f"خرید سرویس VPN برای کاربر {message.from_user.id}"
        )
        if is_ok and link:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO payments (user_id, authority, amount) VALUES (?, ?, ?)",
                           (message.from_user.id, authority, CONFIG_PRICE))
            conn.commit()
            conn.close()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🚀 پرداخت و دریافت کانفیگ 🚀", url=link))
            bot.send_message(message.chat.id, "برای تکمیل خرید و دریافت فوری کانفیگ، روی دکمه زیر کلیک کنید:", reply_markup=markup)
            logger.info(f"لینک پرداخت برای کاربر {message.from_user.id} ایجاد شد.")
        else:
            bot.send_message(message.chat.id, "خطایی در اتصال به درگاه پرداخت رخ داد. لطفاً چند لحظه بعد دوباره تلاش کنید.")
            logger.error("خطا در ایجاد لینک پرداخت از سمت زرین‌پال.")

# --- اجرای برنامه ---
if __name__ == "__main__":
    logger.info("Initializing Database and config files...")
    init_db()
    logger.info("Setting webhook...")
    bot.remove_webhook()
    # در صورتی که وبهوک قبلاً با پارامترهای دیگری ست شده باشد، این خط آن را پاک می‌کند
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook is set to: {WEBHOOK_URL}")
    logger.info("Starting Flask server... Use Gunicorn in production.")
    # دستور پیشنهادی برای اجرا در سرور:
    # gunicorn --workers 4 --bind 0.0.0.0:8080 main:app --log-level info
