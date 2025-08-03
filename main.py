# main.py (نسخه نهایی، قطعی و پایدار با معماری اصلاح‌شده)

import os
import sqlite3
import logging
import datetime
import shutil
import zipfile
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv, set_key
import uuid

# --- تنظیمات اولیه ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
dotenv_path = '.env'
load_dotenv(dotenv_path, encoding='utf-8')

try:
    TOKEN = os.getenv("TOKEN")
    ADMIN_ID_STR = os.getenv("ADMIN_ID")
    CARD_NUMBER = os.getenv("CARD_NUMBER")
    CARD_HOLDER = os.getenv("CARD_HOLDER")
    if not all([TOKEN, ADMIN_ID_STR, CARD_NUMBER, CARD_HOLDER]):
        missing = [v for v, k in {"TOKEN": TOKEN, "ADMIN_ID": ADMIN_ID_STR, "CARD_NUMBER": CARD_NUMBER, "CARD_HOLDER": CARD_HOLDER}.items() if not k]
        raise ValueError(f"متغیرهای زیر در فایل .env خالی هستند: {', '.join(missing)}")
    ADMIN_ID = int(ADMIN_ID_STR)
except (ValueError, TypeError) as e:
    logger.error(f"خطا در متغیرهای محیطی: {e}")
    exit(f"خطا در متغیرهای محیطی: {e}")

DB_FILE = "bot_database.db"
PLANS_CONFIG_DIR = "plan_configs"
SERVICE_NAME = "vpn_bot.service"
bot = telebot.TeleBot(TOKEN)
user_states = {}

MAIN_MENU_COMMANDS = ["➕ مدیریت پلن‌ها", "📊 آمار", "⚙️ تنظیمات پرداخت", "🔄 ریستارت ربات"]
PROMPTS = {
    "adding_plan_name": "🔹 ۱/۴: نام پلن را وارد کنید:",
    "adding_plan_price": "🔹 ۲/۴: قیمت پلن (فقط عدد):",
    "adding_plan_duration": "🔹 ۳/۴: زمان پلن (روز):",
    "adding_plan_configs": "🔹 ۴/۴: کانفیگ‌ها (هر کدام در یک خط):",
    "editing_name": "نام جدید را وارد کنید:",
    "editing_price": "قیمت جدید را وارد کنید (فقط عدد):",
    "editing_duration": "زمان جدید را به روز وارد کنید (فقط عدد):",
    "editing_add_configs": "کانفیگ‌های جدید برای افزودن را وارد کنید (هر کدام در یک خط):",
    "editing_card_number": "شماره کارت جدید را وارد کنید:",
    "editing_card_holder": "نام جدید صاحب حساب را وارد کنید:"
}

# --- توابع دیتابیس و کمکی ---
def db_connect():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()

def init_db():
    conn, c = db_connect()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, wallet_balance INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS plans (plan_id TEXT PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL, duration_days INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS services (service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id TEXT, config TEXT NOT NULL, purchase_date DATE, expiry_date DATE, FOREIGN KEY (user_id) REFERENCES users (user_id), FOREIGN KEY (plan_id) REFERENCES plans (plan_id))')
    conn.commit()
    conn.close()
    os.makedirs(PLANS_CONFIG_DIR, exist_ok=True)

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
    c.execute("INSERT OR IGNORE INTO users (user_id, wallet_balance) VALUES (?, 0)", (user_id,))
    if top_up: c.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?", (amount, user_id))
    else: c.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_a_config_for_plan(plan_id):
    config_filepath = os.path.join(PLANS_CONFIG_DIR, f"{plan_id}.txt")
    if not os.path.exists(config_filepath): return None
    with open(config_filepath, 'r', encoding='utf-8') as f: configs = [line.strip() for line in f if line.strip()]
    if not configs: return None
    user_config = configs.pop(0)
    with open(config_filepath, 'w', encoding='utf-8') as f: f.writelines([c + '\n' for c in configs])
    return user_config

def create_service(user_id, plan_id, config):
    conn, c = db_connect()
    c.execute("SELECT duration_days FROM plans WHERE plan_id = ?", (plan_id,))
    plan_duration = c.fetchone()['duration_days']
    purchase_date = datetime.date.today()
    expiry_date = purchase_date + datetime.timedelta(days=plan_duration)
    c.execute("INSERT INTO services (user_id, plan_id, config, purchase_date, expiry_date) VALUES (?, ?, ?, ?, ?)", (user_id, plan_id, config, purchase_date, expiry_date))
    conn.commit()
    conn.close()
    
def update_env_file(key, value):
    set_key(dotenv_path, key, value, encoding='utf-8')
    os.environ[key] = value

# --- کیبوردها ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ مدیریت پلن‌ها"), KeyboardButton("📊 آمار"))
    markup.row(KeyboardButton("⚙️ تنظیمات پرداخت"), KeyboardButton("🔄 ریستارت ربات"))
    return markup

def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🛍 خرید سرویس"), KeyboardButton("🔄 سرویس‌های من"))
    markup.row(KeyboardButton("💰 کیف پول"))
    return markup
    
def get_back_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("⬅️ بازگشت"))
    return markup

# --- مدیریت دستورات ---
@bot.message_handler(commands=['start', 'cancel'])
def handle_start_cancel(message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    
    if user_id == ADMIN_ID:
        bot.send_message(user_id, "به منوی اصلی بازگشتید.", reply_markup=get_admin_keyboard())
    else:
        add_or_update_user(user_id, message.from_user.first_name, message.from_user.username)
        balance = get_user_balance(user_id)
        bot.send_message(user_id, f"سلام {message.from_user.first_name} عزیز!\n💰 موجودی: **{balance:,} تومان**", parse_mode="Markdown", reply_markup=get_user_keyboard())

# --- مدیریت کاربران عادی ---
@bot.message_handler(func=lambda m: m.from_user.id != ADMIN_ID)
def handle_user_messages(message):
    if message.content_type == 'text':
        state_info = user_states.get(message.from_user.id)
        if state_info and state_info.get('state') == 'awaiting_charge_amount':
            handle_user_charge_amount(message)
        else:
            handle_user_panel(message)
    elif message.content_type in ['photo', 'document']:
        handle_receipt(message)

def handle_user_panel(message):
    if message.text == "🛍 خرید سرویس": show_plans_to_user(message.from_user.id)
    elif message.text == "💰 کیف پول":
        balance = get_user_balance(message.from_user.id)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("افزایش موجودی", callback_data="charge_wallet"))
        bot.send_message(message.from_user.id, f"موجودی: **{balance:,} تومان**", reply_markup=markup, parse_mode="Markdown")
    elif message.text == "🔄 سرویس‌های من": show_my_services(message.from_user.id)

def handle_user_charge_amount(message):
    user_id = message.from_user.id
    try:
        amount = int(message.text)
        if amount <= 0: raise ValueError()
        user_states[user_id] = {"state": "awaiting_charge_receipt", "amount": amount}
        payment_info = (f"برای شارژ **{amount:,} تومان**، وجه را به کارت زیر واریز و رسید را ارسال کنید:\n\n💳 `{os.getenv('CARD_NUMBER')}`\n👤 **{os.getenv('CARD_HOLDER')}**")
        bot.send_message(user_id, payment_info, parse_mode="Markdown")
    except ValueError:
        bot.send_message(user_id, "لطفاً یک عدد صحیح و مثبت وارد کنید. دوباره تلاش کنید.")
        user_states[user_id] = {"state": "awaiting_charge_amount"}
        
def show_plans_to_user(chat_id):
    conn, c = db_connect()
    c.execute("SELECT * FROM plans ORDER BY price")
    plans = c.fetchall()
    conn.close()
    if not plans:
        bot.send_message(chat_id, "در حال حاضر هیچ پلنی موجود نیست.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for plan in plans: markup.add(InlineKeyboardButton(f"{plan['name']} - {plan['price']:,} تومان ({plan['duration_days']} روز)", callback_data=f"buy_{plan['plan_id']}"))
    bot.send_message(chat_id, "👇 لطفا یک پلن را انتخاب کنید:", reply_markup=markup)

def show_my_services(user_id):
    conn, c = db_connect()
    c.execute("SELECT p.name, s.expiry_date, s.service_id FROM services s JOIN plans p ON s.plan_id = p.plan_id WHERE s.user_id = ? AND s.expiry_date >= date('now')", (user_id,))
    active_services = c.fetchall()
    conn.close()
    if not active_services:
        bot.send_message(user_id, "شما سرویس فعالی ندارید.")
        return
    response, markup = "🛎 **سرویس‌های فعال شما:**\n\n", InlineKeyboardMarkup(row_width=1)
    for service in active_services:
        response += f"🔹 **{service['name']}** (انقضا: {service['expiry_date']})\n"
        markup.add(InlineKeyboardButton(f"تمدید سرویس {service['name']}", callback_data=f"renew_{service['service_id']}"))
    bot.send_message(user_id, response, reply_markup=markup, parse_mode="Markdown")

def handle_receipt(message):
    user = message.from_user
    add_or_update_user(user.id, user.first_name, user.username)
    state_info = user_states.get(user.id)
    if not state_info or state_info.get("state") != "awaiting_charge_receipt":
        bot.reply_to(message, "لطفاً ابتدا درخواست شارژ را ثبت کنید.")
        return
    try:
        requested_amount = int(state_info.get("amount", 0))
        if requested_amount <= 0: raise ValueError
    except (ValueError, TypeError):
        bot.reply_to(message, "خطا در ثبت مبلغ. لطفاً دوباره تلاش کنید.")
        user_states.pop(user.id, None)
        return
    user_states.pop(user.id, None)
    msg_to_admin = (f" رسید شارژ از:\n👤 کاربر: {message.from_user.first_name}\n🆔 آیدی: `{user.id}`\n💰 **مبلغ درخواستی: {requested_amount:,} تومان**\n\nلطفاً تایید کنید.")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ تایید و شارژ", callback_data=f"approve_charge_{user.id}_{requested_amount}"))
    bot.forward_message(ADMIN_ID, user.id, message.message_id)
    bot.send_message(ADMIN_ID, msg_to_admin, reply_markup=markup, parse_mode="Markdown")
    bot.reply_to(message, "✅ رسید شما ارسال شد. لطفاً منتظر بمانید.")

# --- مدیریت پنل ادمین (معماری جدید و پایدار) ---
@bot.message_handler(content_types=['text'], func=lambda m: m.from_user.id == ADMIN_ID and m.text in MAIN_MENU_COMMANDS)
def handle_admin_panel(message):
    chat_id = message.chat.id
    user_states.pop(chat_id, None) # لغو خودکار عملیات قبلی
    
    if message.text == "➕ مدیریت پلن‌ها": show_plan_management_panel(chat_id)
    elif message.text == "⚙️ تنظیمات پرداخت": show_payment_settings_panel(chat_id)
    elif message.text == "🔄 ریستارت ربات":
        bot.send_message(chat_id, "در حال ری‌استارت...")
        os.system(f"systemctl restart {SERVICE_NAME}")

def show_plan_management_panel(chat_id):
    conn, c = db_connect()
    c.execute("SELECT * FROM plans ORDER BY price")
    plans = c.fetchall()
    conn.close()
    markup = InlineKeyboardMarkup(row_width=2)
    if plans:
        for plan in plans: markup.add(InlineKeyboardButton(f"✏️ {plan['name']}", callback_data=f"edit_plan_{plan['plan_id']}"), InlineKeyboardButton(f"🗑 حذف", callback_data=f"delete_plan_{plan['plan_id']}"))
    markup.add(InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="add_plan"))
    bot.send_message(chat_id, "⚙️ پنل مدیریت پلن‌ها:", reply_markup=markup)

def show_payment_settings_panel(chat_id):
    card_number = os.getenv("CARD_NUMBER")
    card_holder = os.getenv("CARD_HOLDER")
    text = f"**تنظیمات فعلی پرداخت:**\n\n💳 شماره کارت: `{card_number}`\n👤 نام صاحب حساب: **{card_holder}**"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✏️ ویرایش شماره کارت", callback_data="edit_card_number"), InlineKeyboardButton("✏️ ویرایش نام صاحب حساب", callback_data="edit_card_holder"))
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    if user_id == ADMIN_ID:
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        if data == "add_plan":
            user_states[user_id] = {"data": {}, "history": ["adding_plan_name"]}
            bot.send_message(user_id, PROMPTS["adding_plan_name"], reply_markup=get_back_keyboard())
        elif data.startswith("edit_plan_"):
            plan_id = data.split('_')[2]
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(InlineKeyboardButton("✏️ نام", callback_data=f"edit_name_{plan_id}"), InlineKeyboardButton("💰 قیمت", callback_data=f"edit_price_{plan_id}"))
            markup.add(InlineKeyboardButton("⏳ زمان", callback_data=f"edit_duration_{plan_id}"), InlineKeyboardButton("➕ افزودن کانفیگ", callback_data=f"edit_add_configs_{plan_id}"))
            markup.add(InlineKeyboardButton("⬅️ بازگشت", callback_data="show_plan_panel"))
            bot.send_message(user_id, "کدام بخش را ویرایش می‌کنید؟", reply_markup=markup)
        elif data.startswith(("edit_name_", "edit_price_", "edit_duration_", "edit_add_configs_")):
            parts = data.split('_')
            action, plan_id = parts[1], parts[2]
            state_key = f"editing_{action}"
            user_states[user_id] = {"data": {"plan_id": plan_id}, "history": [state_key]}
            bot.send_message(user_id, f"{PROMPTS[state_key]}\n(برای لغو /cancel را ارسال کنید)", reply_markup=get_back_keyboard())
        elif data.startswith("delete_plan_"):
            plan_id = data.split('_')[2]
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("✅ بله", callback_data=f"confirm_delete_{plan_id}"), InlineKeyboardButton("❌ خیر", callback_data="show_plan_panel"))
            bot.send_message(user_id, "آیا از حذف مطمئن هستید؟", reply_markup=markup)
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
        elif data == "show_plan_panel": show_plan_management_panel(user_id)
        elif data.startswith("approve_charge_"):
            try:
                bot.answer_callback_query(call.id, "در حال پردازش...")
                parts = data.split('_')
                target_user_id, amount_to_add = int(parts[2]), int(parts[3])
                if amount_to_add <= 0: raise ValueError("مبلغ نامعتبر")
                update_user_balance(target_user_id, amount_to_add, top_up=True)
                new_balance = get_user_balance(target_user_id)
                bot.edit_message_text(f"✅ مبلغ {amount_to_add:,} تومان به کاربر {target_user_id} اضافه شد.", call.message.chat.id, call.message.message_id)
                bot.send_message(target_user_id, f"✅ کیف پول شما {amount_to_add:,} تومان شارژ شد.\nموجودی جدید: {new_balance:,} تومان")
            except Exception as e:
                logger.error(f"خطا در تایید شارژ: {e}")
                bot.edit_message_text("خطا در پردازش اطلاعات.", call.message.chat.id, call.message.message_id)
        elif data == "edit_card_number":
            state_key = "editing_card_number"
            user_states[user_id] = {"data": {}, "history": [state_key]}
            bot.send_message(user_id, f"{PROMPTS[state_key]}\n(برای لغو /cancel را ارسال کنید)", reply_markup=get_back_keyboard())
        elif data == "edit_card_holder":
            state_key = "editing_card_holder"
            user_states[user_id] = {"data": {}, "history": [state_key]}
            bot.send_message(user_id, f"{PROMPTS[state_key]}\n(برای لغو /cancel را ارسال کنید)", reply_markup=get_back_keyboard())
        return
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
                bot.answer_callback_query(call.id, "خرید انجام شد.")
                bot.send_message(user_id, f"✅ خرید **{plan['name']}** انجام شد.\nکانفیگ:\n`{config}`", parse_mode="Markdown")
            else: bot.answer_callback_query(call.id, "موجودی کانفیگ تمام شده.", show_alert=True)
        else: bot.answer_callback_query(call.id, "موجودی کافی نیست.", show_alert=True)
    elif data == 'charge_wallet':
        bot.answer_callback_query(call.id)
        user_states[user_id] = {"state": "awaiting_charge_amount"}
        bot.send_message(user_id, "لطفاً مبلغ شارژ را به تومان وارد کنید (فقط عدد):")

@bot.message_handler(content_types=['text'], func=lambda m: m.from_user.id == ADMIN_ID and user_states.get(m.chat.id))
def handle_admin_state_messages(message):
    chat_id = message.chat.id
    if message.text == "⬅️ بازگشت":
        go_back(message)
        return
    
    state_info = user_states[chat_id]
    current_state = state_info["history"][-1]
    
    try:
        if current_state == "adding_plan_name":
            state_info["data"]["name"] = message.text
            next_state = "adding_plan_price"
            state_info["history"].append(next_state)
            bot.send_message(chat_id, PROMPTS[next_state], reply_markup=get_back_keyboard())
        elif current_state == "adding_plan_price":
            state_info["data"]["price"] = int(message.text)
            next_state = "adding_plan_duration"
            state_info["history"].append(next_state)
            bot.send_message(chat_id, PROMPTS[next_state], reply_markup=get_back_keyboard())
        elif current_state == "adding_plan_duration":
            state_info["data"]["duration"] = int(message.text)
            next_state = "adding_plan_configs"
            state_info["history"].append(next_state)
            bot.send_message(chat_id, PROMPTS[next_state], reply_markup=get_back_keyboard())
        elif current_state == "adding_plan_configs":
            plan_id = str(uuid.uuid4())
            data = state_info['data']
            conn, c = db_connect()
            c.execute("INSERT INTO plans (plan_id, name, price, duration_days) VALUES (?, ?, ?, ?)", (plan_id, data['name'], data['price'], data['duration']))
            conn.commit()
            conn.close()
            configs = message.text.strip().split('\n')
            filepath = os.path.join(PLANS_CONFIG_DIR, f"{plan_id}.txt")
            with open(filepath, 'w', encoding='utf-8') as f:
                for config_line in configs: f.write(config_line + '\n')
            user_states.pop(chat_id, None)
            bot.send_message(chat_id, f"✅ پلن جدید '{data['name']}' ساخته شد.", reply_markup=get_admin_keyboard())
        
        elif current_state == "editing_name":
            conn, c = db_connect()
            c.execute("UPDATE plans SET name = ? WHERE plan_id = ?", (message.text, state_info['data']['plan_id']))
            conn.commit()
            conn.close()
            user_states.pop(chat_id, None)
            bot.send_message(chat_id, "✅ نام ویرایش شد.", reply_markup=get_admin_keyboard())
        elif current_state == "editing_price":
            conn, c = db_connect()
            c.execute("UPDATE plans SET price = ? WHERE plan_id = ?", (int(message.text), state_info['data']['plan_id']))
            conn.commit()
            conn.close()
            user_states.pop(chat_id, None)
            bot.send_message(chat_id, "✅ قیمت ویرایش شد.", reply_markup=get_admin_keyboard())
        elif current_state == "editing_duration":
            conn, c = db_connect()
            c.execute("UPDATE plans SET duration_days = ? WHERE plan_id = ?", (int(message.text), state_info['data']['plan_id']))
            conn.commit()
            conn.close()
            user_states.pop(chat_id, None)
            bot.send_message(chat_id, "✅ زمان ویرایش شد.", reply_markup=get_admin_keyboard())
        elif current_state == "editing_add_configs":
            filepath = os.path.join(PLANS_CONFIG_DIR, f"{state_info['data']['plan_id']}.txt")
            with open(filepath, 'a', encoding='utf-8') as f:
                for config in message.text.strip().split('\n'): f.write(config + '\n')
            user_states.pop(chat_id, None)
            bot.send_message(chat_id, f"✅ کانفیگ‌های جدید اضافه شد.", reply_markup=get_admin_keyboard())
        elif current_state == "editing_card_number":
            update_env_file("CARD_NUMBER", message.text)
            user_states.pop(chat_id, None)
            bot.send_message(chat_id, "✅ شماره کارت ویرایش شد.", reply_markup=get_admin_keyboard())
        elif current_state == "editing_card_holder":
            update_env_file("CARD_HOLDER", message.text)
            user_states.pop(chat_id, None)
            bot.send_message(chat_id, "✅ نام صاحب حساب ویرایش شد.", reply_markup=get_admin_keyboard())

    except (ValueError, TypeError): bot.send_message(chat_id, "خطا: ورودی نامعتبر است. لطفاً دوباره تلاش کنید.", reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error(f"خطا در پردازش وضعیت ادمین: {e}")
        bot.send_message(chat_id, "یک خطای پیش‌بینی نشده رخ داد. عملیات لغو شد.", reply_markup=get_admin_keyboard())
        user_states.pop(chat_id, None)

def go_back(message):
    chat_id = message.chat.id
    state_info = user_states.get(chat_id)
    if not state_info or len(state_info["history"]) <= 1:
        cancel_operation(message)
        return
    
    state_info["history"].pop()
    previous_state = state_info["history"][-1]
    
    bot.send_message(chat_id, f"به مرحله قبل بازگشتید.\n{PROMPTS[previous_state]}", reply_markup=get_back_keyboard())
    
if __name__ == "__main__":
    init_db()
    logger.info("ربات در حال شروع به کار (Polling)...")
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        logger.error(f"خطای مرگبار در حلقه اصلی ربات: {e}")