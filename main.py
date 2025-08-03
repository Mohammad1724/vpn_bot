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
SERVICE_NAME = "vpn_bot.service" # برای دستور ریستارت

bot = telebot.TeleBot(TOKEN)
user_states = {} # برای ذخیره وضعیت‌های چندمرحله‌ای

# --- مدیریت پایگاه داده ---
def db_connect():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()

def init_db():
    conn, c = db_connect()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, wallet_balance INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            plan_id TEXT PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL, duration_days INTEGER NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS services (
            service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id TEXT,
            config TEXT NOT NULL, purchase_date DATE, expiry_date DATE,
            FOREIGN KEY (user_id) REFERENCES users (user_id), FOREIGN KEY (plan_id) REFERENCES plans (plan_id)
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
    c.execute("UPDATE users SET first_name = ?, username = ? WHERE user_id = ?", (first_name, username, user_id))
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

def create_service(user_id, plan_id, config):
    conn, c = db_connect()
    c.execute("SELECT duration_days FROM plans WHERE plan_id = ?", (plan_id,))
    plan_duration = c.fetchone()['duration_days']
    purchase_date = datetime.date.today()
    expiry_date = purchase_date + datetime.timedelta(days=plan_duration)
    c.execute("INSERT INTO services (user_id, plan_id, config, purchase_date, expiry_date) VALUES (?, ?, ?, ?, ?)",
              (user_id, plan_id, config, purchase_date, expiry_date))
    conn.commit()
    conn.close()

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
        bot.send_message(user.id, "سلام ادمین عزیز! به پنل مدیریت جامع خوش آمدید.", reply_markup=get_admin_keyboard())
    else:
        balance = get_user_balance(user.id)
        bot.send_message(user.id, f"سلام {user.first_name} عزیز!\n💰 موجودی کیف پول شما: **{balance:,} تومان**", parse_mode="Markdown", reply_markup=get_user_keyboard())

@bot.message_handler(func=lambda m: m.from_user.id != ADMIN_ID)
def handle_user_panel(message):
    user_id = message.from_user.id
    text = message.text

    if text == "🛍 خرید سرویس":
        show_plans_to_user(user_id)
    elif text == "💰 کیف پول":
        balance = get_user_balance(user_id)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("افزایش موجودی", callback_data="charge_wallet"))
        bot.send_message(user_id, f"موجودی فعلی شما: **{balance:,} تومان**", reply_markup=markup, parse_mode="Markdown")
    elif text == "🔄 سرویس‌های من":
        show_my_services(user_id)

def show_plans_to_user(chat_id):
    conn, c = db_connect()
    c.execute("SELECT * FROM plans ORDER BY price")
    plans = c.fetchall()
    conn.close()
    if not plans:
        bot.send_message(chat_id, "متاسفانه در حال حاضر هیچ پلنی برای فروش موجود نیست.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for plan in plans:
        button_text = f"{plan['name']} - {plan['price']:,} تومان ({plan['duration_days']} روز)"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"buy_{plan['plan_id']}"))
    bot.send_message(chat_id, "👇 لطفا یکی از پلن‌های زیر را انتخاب کنید:", reply_markup=markup)

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
    markup = InlineKeyboardMarkup(row_width=1)
    for service in active_services:
        response += f"🔹 **{service['name']}** (انقضا: {service['expiry_date']})\n"
        markup.add(InlineKeyboardButton(f"تمدید سرویس {service['name']}", callback_data=f"renew_{service['service_id']}"))
    bot.send_message(user_id, response, reply_markup=markup, parse_mode="Markdown")

# --- مدیریت Callback ها ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data

    # Callbacks کاربر
    if data.startswith("buy_"):
        plan_id = data.split('_')[1]
        conn, c = db_connect()
        c.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
        plan = c.fetchone()
        conn.close()
        
        balance = get_user_balance(user_id)
        if balance >= plan['price']:
            config = get_a_config_for_plan(plan_id)
            if config:
                update_user_balance(user_id, plan['price'], top_up=False)
                create_service(user_id, plan_id, config)
                bot.answer_callback_query(call.id, "خرید با موفقیت انجام شد.")
                bot.send_message(user_id, f"✅ خرید **{plan['name']}** با موفقیت از کیف پول شما انجام شد.\nکانفیگ شما:")
                bot.send_message(user_id, f"`{config}`", parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "موجودی کانفیگ این پلن تمام شده. لطفاً به ادمین اطلاع دهید.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"موجودی کیف پول شما کافی نیست. لطفاً ابتدا آن را شارژ کنید.", show_alert=True)
    
    elif data == 'charge_wallet':
        msg = bot.send_message(user_id, "لطفاً مبلغ مورد نظر برای شارژ کیف پول را به تومان وارد کنید:")
        bot.register_next_step_handler(msg, process_charge_amount)

    # Callbacks ادمین
    elif user_id == ADMIN_ID:
        if data.startswith("approve_charge_"):
            parts = data.split('_')
            target_user_id, amount = int(parts[2]), int(parts[3])
            update_user_balance(target_user_id, amount, top_up=True)
            new_balance = get_user_balance(target_user_id)
            bot.edit_message_text(f"✅ مبلغ {amount:,} تومان به کیف پول کاربر اضافه شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(target_user_id, f"✅ کیف پول شما به مبلغ {amount:,} تومان شارژ شد. موجودی جدید: {new_balance:,} تومان")
        # ... (سایر callbacks ادمین در پنل مدیریت)

# --- مدیریت رسید پرداخت ---
@bot.message_handler(content_types=['photo', 'document'], func=lambda m: m.from_user.id != ADMIN_ID)
def handle_receipt(message):
    user_id = message.from_user.id
    # فرض می‌کنیم کاربر در مرحله شارژ کیف پول است
    # برای سیستم پیچیده‌تر، باید وضعیت کاربر را دقیق‌تر بررسی کرد
    msg_to_admin = (f"رسید شارژ کیف پول از:\n"
                    f"👤 کاربر: {message.from_user.first_name}\n"
                    f"🆔 آیدی: `{user_id}`\n\n"
                    f"لطفا مبلغ را از رسید خوانده و برای تایید، روی دکمه مناسب کلیک کنید.")
    
    # ادمین باید مبلغ را دستی وارد کند
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ تایید شارژ", callback_data=f"confirm_charge_{user_id}"))
    bot.forward_message(ADMIN_ID, user_id, message.message_id)
    bot.send_message(ADMIN_ID, msg_to_admin, reply_markup=markup, parse_mode="Markdown")
    bot.reply_to(message, "✅ رسید شما برای ادمین ارسال شد. پس از تایید، کیف پول شما شارژ خواهد شد.")

# --- مدیریت پنل ادمین ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def handle_admin_panel(message):
    text = message.text
    chat_id = message.chat.id
    user_states.pop(chat_id, None)

    if text == "➕ مدیریت پلن‌ها":
        show_plan_management_panel(chat_id)
    elif text == "🔄 ریستارت ربات":
        bot.send_message(chat_id, "در حال ری‌استارت کردن سرویس ربات...")
        os.system(f"systemctl restart {SERVICE_NAME}")
    elif text == "📥 بکاپ":
        backup_data(chat_id)
    elif text == "📤 ریستور":
        msg = bot.send_message(chat_id, "فایل بکاپ (.zip) را ارسال کنید تا اطلاعات بازیابی شود.")
        bot.register_next_step_handler(msg, restore_data)
        
def show_plan_management_panel(chat_id):
    conn, c = db_connect()
    c.execute("SELECT * FROM plans ORDER BY price")
    plans = c.fetchall()
    conn.close()
    markup = InlineKeyboardMarkup(row_width=2)
    if plans:
        for plan in plans:
            markup.add(
                InlineKeyboardButton(f"✏️ {plan['name']}", callback_data=f"edit_plan_{plan['plan_id']}"),
                InlineKeyboardButton(f"🗑 حذف", callback_data=f"delete_plan_{plan['plan_id']}")
            )
    markup.add(InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="add_plan"))
    bot.send_message(chat_id, "⚙️ پنل مدیریت پلن‌ها:", reply_markup=markup)
    
# --- (سایر توابع مدیریت ادمین و callback ها) ---

# ... (ادامه پیاده‌سازی callback های ادمین برای افزودن، ویرایش، حذف پلن و تایید شارژ)

# --- شروع به کار ربات ---
if __name__ == "__main__":
    init_db()
    logger.info("ربات در حال شروع به کار (Polling)...")
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        logger.error(f"خطای مرگبار در حلقه اصلی ربات: {e}")