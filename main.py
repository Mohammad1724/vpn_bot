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
import json
import uuid

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
except (TypeError, ValueError):
    exit("خطا: TOKEN, ADMIN_ID, CARD_NUMBER, CARD_HOLDER باید در فایل .env تنظیم شوند.")

DB_FILE = "bot_database.db"
PLANS_CONFIG_DIR = "plan_configs"
SERVICE_NAME = "vpn_bot.service"

bot = telebot.TeleBot(TOKEN)
user_states = {}

# --- مدیریت پایگاه داده ---
def db_connect():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()

def init_db():
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
            plan_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            duration_days INTEGER NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS services (
            service_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_id TEXT,
            config TEXT NOT NULL,
            purchase_date DATE,
            expiry_date DATE,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (plan_id) REFERENCES plans (plan_id)
        )
    ''')
    conn.commit()
    conn.close()
    os.makedirs(PLANS_CONFIG_DIR, exist_ok=True)
    logger.info("پایگاه داده و پوشه‌ها با موفقیت مقداردهی اولیه شدند.")

# --- توابع کمکی ---
def add_or_update_user(user_id, first_name, username):
    conn, c = db_connect()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)", (user_id, first_name, username))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn, c = db_connect()
    c.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result['wallet_balance'] if result else 0

def update_user_balance(user_id, amount, top_up=True):
    conn, c = db_connect()
    if top_up:
        c.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?", (amount, user_id))
    else: # Deduct for purchase
        c.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_a_config_for_plan(plan_id):
    config_filepath = os.path.join(PLANS_CONFIG_DIR, f"{plan_id}.txt")
    if not os.path.exists(config_filepath): return None
    with open(config_filepath, 'r', encoding='utf-8') as f:
        configs = [line.strip() for line in f if line.strip()]
    if not configs: return None
    user_config = configs.pop(0)
    with open(config_filepath, 'w', encoding='utf-8') as f:
        f.writelines([c + '\n' for c in configs])
    return user_config

# --- کیبوردها ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ مدیریت پلن‌ها"), KeyboardButton("📊 آمار"))
    markup.row(KeyboardButton("📥 بکاپ"), KeyboardButton("📤 ریستور"))
    markup.row(KeyboardButton("🔄 ریستارت ربات"))
    return markup

def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🛍 خرید سرویس"), KeyboardButton("🔄 سرویس‌های من"))
    markup.row(KeyboardButton("💰 کیف پول"))
    return markup

# --- مدیریت پنل کاربر ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    add_or_update_user(user.id, user.first_name, user.username)
    if user.id == ADMIN_ID:
        bot.send_message(user.id, "سلام ادمین عزیز!", reply_markup=get_admin_keyboard())
    else:
        balance = get_user_balance(user.id)
        bot.send_message(user.id, f"سلام {user.first_name}!\n💰 موجودی: {balance:,} تومان", parse_mode="Markdown", reply_markup=get_user_keyboard())

# ... (ادامه کد در بلاک بعدی)
# ... (ادامه main.py)

# --- مدیریت پنل ادمین ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def handle_admin_panel(message):
    # ... (پیاده‌سازی کامل پنل ادمین)
    pass

# --- شروع به کار ربات ---
if __name__ == "__main__":
    init_db()
    logger.info("ربات در حال شروع به کار (Polling)...")
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        logger.error(f"خطای مرگبار در حلقه اصلی ربات: {e}")