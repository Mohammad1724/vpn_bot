# main.py

import os
import sqlite3
import logging
import datetime
import shutil
import zipfile
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# --- تنظیمات اولیه ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
dotenv_path = '.env'
load_dotenv(dotenv_path, encoding='utf-8')

try:
    TOKEN = os.getenv("TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
    CARD_NUMBER = os.getenv("CARD_NUMBER")
    CARD_HOLDER = os.getenv("CARD_HOLDER")
except (TypeError, ValueError): exit("خطا: TOKEN, ADMIN_ID, CARD_NUMBER, CARD_HOLDER باید در فایل .env تنظیم شوند.")

DB_FILE = "bot_database.db"
PLANS_DIR = "plan_configs"
SERVICE_NAME = "vpn_bot.service"

bot = telebot.TeleBot(TOKEN)
user_states = {}

# --- مدیریت پایگاه داده ---
def db_connect():
    """ایجاد اتصال به دیتابیس و برگرداندن اتصال و کرسر."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # برای دسترسی به ستون‌ها با نام
    return conn, conn.cursor()

def init_db():
    """ایجاد جداول اولیه در دیتابیس در صورت عدم وجود."""
    conn, c = db_connect()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            wallet_balance INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            duration_days INTEGER NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS services (
            service_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_id INTEGER,
            config TEXT NOT NULL,
            purchase_date DATE,
            expiry_date DATE,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (plan_id) REFERENCES plans (plan_id)
        )
    ''')
    conn.commit()
    conn.close()
    os.makedirs(PLANS_DIR, exist_ok=True)
    logger.info("پایگاه داده و پوشه‌ها با موفقیت مقداردهی اولیه شدند.")

init_db() # اجرای اولیه برای ساخت جداول

# --- توابع کمکی کاربر ---
def add_or_update_user(user_id, first_name, username):
    conn, c = db_connect()
    c.execute("INSERT OR REPLACE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
              (user_id, first_name, username))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn, c = db_connect()
    c.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result['wallet_balance'] if result else 0

def update_user_balance(user_id, amount):
    conn, c = db_connect()
    c.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- (کدهای دیگر در ادامه) ---
# ... (ادامه کد main.py)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    add_or_update_user(user.id, user.first_name, user.username)
    
    if is_admin(message):
        bot.send_message(message.chat.id, "سلام ادمین عزیز!", reply_markup=get_admin_keyboard())
    else:
        balance = get_user_balance(user.id)
        welcome_text = (f"سلام {user.first_name} عزیز!\n"
                        f"💰 موجودی کیف پول شما: **{balance:,} تومان**")
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_user_keyboard())

# --- کیبوردها ---
def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🛍 خرید سرویس"), KeyboardButton("🔄 سرویس‌های من"))
    markup.row(KeyboardButton("💰 کیف پول"))
    return markup

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ مدیریت پلن‌ها"), KeyboardButton("📊 آمار"))
    markup.row(KeyboardButton("📥 بکاپ"), KeyboardButton("📤 ریستور"))
    markup.row(KeyboardButton("🔄 ریستارت ربات"))
    return markup

# --- مدیریت خرید و کیف پول کاربر ---
@bot.message_handler(func=lambda m: not is_admin(m))
def handle_user_panel(message):
    user_id = message.from_user.id
    text = message.text

    if text == "🛍 خرید سرویس":
        # ... (منطق نمایش پلن‌ها و خرید)
        pass
    elif text == "💰 کیف پول":
        balance = get_user_balance(user_id)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("افزایش موجودی", callback_data="charge_wallet"))
        bot.send_message(user_id, f"موجودی فعلی شما: **{balance:,} تومان**", reply_markup=markup, parse_mode="Markdown")
    elif text == "🔄 سرویس‌های من":
        show_my_services(user_id)

@bot.callback_query_handler(func=lambda call: call.data == 'charge_wallet')
def charge_wallet_callback(call):
    user_id = call.from_user.id
    msg = bot.send_message(user_id, "لطفاً مبلغ مورد نظر برای شارژ کیف پول را به تومان وارد کنید:")
    bot.register_next_step_handler(msg, process_charge_amount)

def process_charge_amount(message):
    try:
        amount = int(message.text)
        if amount <= 0: raise ValueError()
        
        # ذخیره مبلغ در وضعیت کاربر برای تایید بعدی
        user_states[message.from_user.id] = {"state": "awaiting_charge_receipt", "amount": amount}
        
        payment_info = (f"برای شارژ کیف پول به مبلغ **{amount:,} تومان**، لطفاً وجه را به کارت زیر واریز کرده و رسید را ارسال کنید:\n\n"
                        f"💳 شماره کارت:\n`{CARD_NUMBER}`\n"
                        f"👤 نام صاحب حساب: **{CARD_HOLDER}**")
        bot.send_message(message.chat.id, payment_info, parse_mode="Markdown")

    except ValueError:
        bot.send_message(message.chat.id, "لطفاً یک عدد صحیح و مثبت وارد کنید.")

def show_my_services(user_id):
    conn, c = db_connect()
    c.execute("""
        SELECT p.name, s.expiry_date, s.service_id FROM services s
        JOIN plans p ON s.plan_id = p.plan_id
        WHERE s.user_id = ? AND s.expiry_date >= date('now')
    """, (user_id,))
    active_services = c.fetchall()
    conn.close()

    if not active_services:
        bot.send_message(user_id, "شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return

    response = "🛎 **سرویس‌های فعال شما:**\n\n"
    markup = InlineKeyboardMarkup()
    for service in active_services:
        expiry_date = datetime.datetime.strptime(service['expiry_date'], '%Y-%m-%d').strftime('%d %B %Y')
        response += f"🔹 **{service['name']}**\n   -  تاریخ انقضا: {expiry_date}\n\n"
        markup.add(InlineKeyboardButton(f"تمدید سرویس {service['name']}", callback_data=f"renew_{service['service_id']}"))

    bot.send_message(user_id, response, reply_markup=markup, parse_mode="Markdown")


# --- بکاپ و ریستور ---
def backup_data(chat_id):
    bot.send_message(chat_id, "در حال ایجاد فایل بکاپ کامل...")
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        backup_filename_base = f'full_backup_{timestamp}'
        
        # کپی کردن فایل‌های مهم به یک پوشه موقت
        temp_backup_dir = 'temp_backup_dir'
        os.makedirs(temp_backup_dir, exist_ok=True)
        shutil.copy(DB_FILE, temp_backup_dir)
        if os.path.exists(PLANS_DIR):
            shutil.copytree(PLANS_DIR, os.path.join(temp_backup_dir, PLANS_DIR))

        # فشرده‌سازی پوشه موقت
        shutil.make_archive(backup_filename_base, 'zip', temp_backup_dir)
        
        with open(f'{backup_filename_base}.zip', 'rb') as backup_file:
            bot.send_document(chat_id, backup_file, caption="✅ بکاپ کامل با موفقیت ایجاد شد.")
            
    except Exception as e:
        logger.error(f"خطا در ایجاد بکاپ: {e}")
        bot.send_message(chat_id, f"❌ خطایی در هنگام ایجاد بکاپ رخ داد: {e}")
    finally:
        if 'backup_filename_base' in locals() and os.path.exists(f'{backup_filename_base}.zip'):
            os.remove(f'{backup_filename_base}.zip')
        if 'temp_backup_dir' in locals() and os.path.exists(temp_backup_dir):
            shutil.rmtree(temp_backup_dir)

# ... (و سایر توابع و کدهای ربات)