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
    # (کد ساخت جداول بدون تغییر)
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
    else:
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
    c.execute("SELECT p.name, s.expiry_date, s.service_id FROM services s JOIN plans p ON s.plan_id = p.plan_id WHERE s.user_id = ? AND s.expiry_date >= date('now')", (user_id,))
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

@bot.message_handler(content_types=['photo', 'document'], func=lambda m: m.from_user.id != ADMIN_ID)
def handle_receipt(message):
    user_id = message.from_user.id
    state_info = user_states.get(user_id)
    if not state_info or state_info.get("state") != "awaiting_charge_receipt":
        bot.reply_to(message, "لطفاً ابتدا از طریق دکمه «کیف پول»، درخواست شارژ را ثبت کنید.")
        return

    requested_amount = state_info.get("amount", "نامشخص")
    user_states.pop(user_id, None)

    msg_to_admin = (f" رسید شارژ کیف پول از:\n"
                    f"👤 کاربر: {message.from_user.first_name}\n"
                    f"🆔 آیدی: `{user_id}`\n"
                    f"💰 **مبلغ درخواستی: {requested_amount:,} تومان**\n\n"
                    f"لطفاً با رسید تطبیق داده و در صورت صحت، تایید کنید.")
    
    markup = InlineKeyboardMarkup()
    callback_data = f"approve_charge_{user_id}_{requested_amount}"
    markup.add(InlineKeyboardButton("✅ تایید و شارژ کیف پول", callback_data=callback_data))
    
    bot.forward_message(ADMIN_ID, user_id, message.message_id)
    bot.send_message(ADMIN_ID, msg_to_admin, reply_markup=markup, parse_mode="Markdown")
    bot.reply_to(message, "✅ رسید شما برای ادمین ارسال شد. پس از تایید، کیف پول شما شارژ خواهد شد.")

# --- مدیریت پنل ادمین ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and not user_states.get(m.chat.id))
def handle_admin_panel(message):
    text = message.text
    chat_id = message.chat.id
    if text == "➕ مدیریت پلن‌ها":
        show_plan_management_panel(chat_id)
    elif text == "🔄 ریستارت ربات":
        bot.send_message(chat_id, "در حال ری‌استارت کردن سرویس ربات...")
        os.system(f"systemctl restart {SERVICE_NAME}")
    elif text == "📥 بکاپ":
        backup_data(chat_id)
    elif text == "📤 ریستور":
        msg = bot.send_message(chat_id, "فایل بکاپ (.zip) را ارسال کنید.")
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

def backup_data(chat_id):
    # (کد بکاپ بدون تغییر)
    pass
def restore_data(message):
    bot.reply_to(message, "قابلیت ریستور در حال توسعه است.")

# --- مدیریت Callback ها ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data

    # Callbacks ادمین
    if user_id == ADMIN_ID:
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        
        if data == "add_plan":
            user_states[user_id] = {"state": "adding_plan_name"}
            bot.send_message(user_id, "🔹 مرحله ۱/۴: نام پلن جدید را وارد کنید:")
        
        elif data.startswith("edit_plan_"):
            plan_id = data.split('_')[2]
            user_states[user_id] = {"state": "editing_plan_start", "plan_id": plan_id}
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(InlineKeyboardButton("✏️ نام", callback_data=f"edit_name_{plan_id}"), InlineKeyboardButton("💰 قیمت", callback_data=f"edit_price_{plan_id}"))
            markup.add(InlineKeyboardButton("⏳ زمان", callback_data=f"edit_duration_{plan_id}"), InlineKeyboardButton("➕ افزودن کانفیگ", callback_data=f"edit_add_configs_{plan_id}"))
            markup.add(InlineKeyboardButton("⬅️ بازگشت", callback_data="show_plan_panel"))
            bot.send_message(user_id, "کدام بخش از این پلن را می‌خواهید ویرایش کنید؟", reply_markup=markup)

        elif data.startswith(("edit_name_", "edit_price_", "edit_duration_", "edit_add_configs_")):
            parts = data.split('_')
            action, plan_id = parts[1], parts[2]
            user_states[user_id] = {"state": f"editing_{action}", "plan_id": plan_id}
            prompt = {"name": "نام جدید:", "price": "قیمت جدید (فقط عدد):", "duration": "زمان جدید (روز):", "add": "کانفیگ‌های جدید (هر کدام در یک خط):"}
            bot.send_message(user_id, prompt.get(action, "دستور نامشخص"))

        elif data.startswith("delete_plan_"):
            plan_id = data.split('_')[2]
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"confirm_delete_{plan_id}"), InlineKeyboardButton("❌ خیر", callback_data="show_plan_panel"))
            bot.send_message(user_id, "آیا از حذف این پلن مطمئن هستید؟", reply_markup=markup)

        elif data.startswith("confirm_delete_"):
            plan_id = data.split('_')[2]
            conn, c = db_connect()
            c.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
            conn.commit()
            conn.close()
            filepath = os.path.join(PLANS_CONFIG_DIR, f"{plan_id}.txt")
            if os.path.exists(filepath): os.remove(filepath)
            bot.answer_callback_query(call.id, "پلن حذف شد.")
            show_plan_management_panel(user_id)

        elif data == "show_plan_panel":
            show_plan_management_panel(user_id)
        
        elif data.startswith("approve_charge_"):
            parts = data.split('_')
            target_user_id, amount_to_add = int(parts[2]), int(parts[3])
            update_user_balance(target_user_id, amount_to_add, top_up=True)
            new_balance = get_user_balance(target_user_id)
            bot.edit_message_text(f"✅ مبلغ {amount_to_add:,} تومان به کیف پول کاربر {target_user_id} اضافه شد.", call.message.chat.id, call.message.message_id)
            bot.send_message(target_user_id, f"✅ کیف پول شما توسط ادمین به مبلغ {amount_to_add:,} تومان شارژ شد.\nموجودی جدید: {new_balance:,} تومان")
        
        return

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
                bot.send_message(user_id, f"✅ خرید **{plan['name']}** انجام شد.\nکانفیگ شما:")
                bot.send_message(user_id, f"`{config}`", parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "موجودی کانفیگ این پلن تمام شده.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "موجودی کیف پول شما کافی نیست.", show_alert=True)
    
    elif data == 'charge_wallet':
        msg = bot.send_message(user_id, "لطفاً مبلغ شارژ را به تومان وارد کنید:")
        bot.register_next_step_handler(msg, process_charge_amount)

def process_charge_amount(message):
    try:
        amount = int(message.text)
        if amount <= 0: raise ValueError()
        user_states[message.from_user.id] = {"state": "awaiting_charge_receipt", "amount": amount}
        payment_info = (f"برای شارژ به مبلغ **{amount:,} تومان**، وجه را به کارت زیر واریز و رسید را ارسال کنید:\n\n"
                        f"💳 `{CARD_NUMBER}`\n"
                        f"👤 **{CARD_HOLDER}**")
        bot.send_message(message.chat.id, payment_info, parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "لطفاً یک عدد صحیح و مثبت وارد کنید.")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(m.chat.id))
def handle_admin_state_messages(message):
    chat_id = message.chat.id
    state_info = user_states[chat_id]
    state = state_info.get("state")
    
    if state == "adding_plan_name":
        state_info["name"] = message.text
        state_info["state"] = "adding_plan_price"
        bot.send_message(chat_id, "🔹 مرحله ۲/۴: قیمت پلن (فقط عدد):")
    elif state == "adding_plan_price":
        try:
            state_info["price"] = int(message.text)
            state_info["state"] = "adding_plan_duration"
            bot.send_message(chat_id, "🔹 مرحله ۳/۴: مدت زمان پلن (روز):")
        except ValueError:
            bot.send_message(chat_id, "خطا: لطفاً قیمت را به صورت عدد وارد کنید.")
    elif state == "adding_plan_duration":
        try:
            state_info["duration"] = int(message.text)
            state_info["state"] = "adding_plan_configs"
            bot.send_message(chat_id, "🔹 مرحله ۴/۴: کانفیگ‌های این پلن (هر کدام در یک خط):")
        except ValueError:
            bot.send_message(chat_id, "خطا: لطفاً مدت زمان را به صورت عدد وارد کنید.")
    elif state == "adding_plan_configs":
        plan_id = str(uuid.uuid4())
        conn, c = db_connect()
        c.execute("INSERT INTO plans (plan_id, name, price, duration_days) VALUES (?, ?, ?, ?)",
                  (plan_id, state_info['name'], state_info['price'], state_info['duration']))
        conn.commit()
        conn.close()
        configs = message.text.strip().split('\n')
        filepath = os.path.join(PLANS_CONFIG_DIR, f"{plan_id}.txt")
        with open(filepath, 'w', encoding='utf-8') as f: f.writelines([c + '\n' for c in configs])
        user_states.pop(chat_id, None)
        bot.send_message(chat_id, "✅ پلن جدید با موفقیت ساخته شد.")
        show_plan_management_panel(chat_id)

    # --- حالات ویرایش ---
    elif state == "editing_name":
        conn, c = db_connect()
        c.execute("UPDATE plans SET name = ? WHERE plan_id = ?", (message.text, state_info['plan_id']))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, "✅ نام پلن ویرایش شد.")
        user_states.pop(chat_id, None)
        show_plan_management_panel(chat_id)
    elif state == "editing_price":
        try:
            conn, c = db_connect()
            c.execute("UPDATE plans SET price = ? WHERE plan_id = ?", (int(message.text), state_info['plan_id']))
            conn.commit()
            conn.close()
            bot.send_message(chat_id, "✅ قیمت پلن ویرایش شد.")
            user_states.pop(chat_id, None)
            show_plan_management_panel(chat_id)
        except ValueError: bot.send_message(chat_id, "خطا: قیمت باید عدد باشد.")
    elif state == "editing_duration":
        try:
            conn, c = db_connect()
            c.execute("UPDATE plans SET duration_days = ? WHERE plan_id = ?", (int(message.text), state_info['plan_id']))
            conn.commit()
            conn.close()
            bot.send_message(chat_id, "✅ زمان پلن ویرایش شد.")
            user_states.pop(chat_id, None)
            show_plan_management_panel(chat_id)
        except ValueError: bot.send_message(chat_id, "خطا: زمان باید عدد باشد.")
    elif state == "editing_add_configs":
        configs = message.text.strip().split('\n')
        filepath = os.path.join(PLANS_CONFIG_DIR, f"{state_info['plan_id']}.txt")
        with open(filepath, 'a', encoding='utf-8') as f:
            for config in configs: f.write(config + '\n')
        bot.send_message(chat_id, f"✅ {len(configs)} کانفیگ جدید به پلن اضافه شد.")
        user_states.pop(chat_id, None)
        show_plan_management_panel(chat_id)


# --- شروع به کار ربات ---
if __name__ == "__main__":
    init_db()
    logger.info("ربات در حال شروع به کار (Polling)...")
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        logger.error(f"خطای مرگبار در حلقه اصلی ربات: {e}")