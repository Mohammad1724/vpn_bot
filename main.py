# main.py (نسخه نهایی، قطعی و پایدار با معماری ساده‌شده)

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

# --- کیبوردها ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ افزودن پلن"), KeyboardButton("📋 لیست/مدیریت پلن‌ها"))
    markup.row(KeyboardButton("📊 آمار"), KeyboardButton("🔄 ریستارت ربات"))
    return markup

def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🛍 خرید سرویس"), KeyboardButton("🔄 سرویس‌های من"))
    markup.row(KeyboardButton("💰 کیف پول"))
    return markup

# --- مدیریت دستورات ---
@bot.message_handler(commands=['start', 'cancel'])
def send_welcome(message):
    user = message.from_user
    add_or_update_user(user.id, user.first_name, user.username)
    if user.id == ADMIN_ID:
        bot.send_message(user.id, "سلام ادمین عزیز! به پنل مدیریت خوش آمدید.", reply_markup=get_admin_keyboard())
    else:
        balance = get_user_balance(user.id)
        bot.send_message(user.id, f"سلام {user.first_name} عزیز!\n💰 موجودی: **{balance:,} تومان**", parse_mode="Markdown", reply_markup=get_user_keyboard())

# --- مدیریت کاربران عادی ---
@bot.message_handler(func=lambda m: m.from_user.id != ADMIN_ID)
def handle_user_messages(message):
    if message.content_type == 'text':
        if message.text == "🛍 خرید سرویس": show_plans_to_user(message.from_user.id)
        elif message.text == "💰 کیف پول": handle_wallet_request(message)
        elif message.text == "🔄 سرویس‌های من": show_my_services(message.from_user.id)
    elif message.content_type in ['photo', 'document']: handle_receipt(message)

def handle_wallet_request(message):
    balance = get_user_balance(message.from_user.id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("افزایش موجودی", callback_data="charge_wallet"))
    bot.send_message(message.from_user.id, f"موجودی فعلی شما: **{balance:,} تومان**", reply_markup=markup, parse_mode="Markdown")

def handle_receipt(message):
    user = message.from_user
    add_or_update_user(user.id, user.first_name, user.username)
    msg_to_admin = (f" رسید شارژ کیف پول از:\n👤 کاربر: {message.from_user.first_name}\n🆔 آیدی: `{user.id}`\n\n"
                    "لطفا مبلغ را از رسید خوانده و برای تایید، روی این پیام ریپلای کرده و **مبلغ را به عدد** ارسال کنید.")
    bot.forward_message(ADMIN_ID, user.id, message.message_id)
    bot.send_message(ADMIN_ID, msg_to_admin, parse_mode="Markdown")
    bot.reply_to(message, "✅ رسید شما برای ادمین ارسال شد. پس از تایید، کیف پول شما شارژ خواهد شد.")

# --- مدیریت پنل ادمین ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def handle_admin_panel(message):
    if message.reply_to_message:
        if "رسید شارژ کیف پول" in message.reply_to_message.text:
            process_admin_charge_confirmation(message)
        elif "برای افزودن کانفیگ به این پلن" in message.reply_to_message.text:
            process_add_configs_to_plan(message)
        return
        
    if message.text == "➕ افزودن پلن":
        prompt = (
            "برای افزودن پلن جدید، یک پیام با فرمت زیر ارسال کنید:\n"
            "دستور را با `/addplan` شروع کنید.\n\n"
            "**/addplan**\n"
            "نام پلن\n"
            "قیمت (فقط عدد)\n"
            "مدت زمان (روز)\n"
            "---\n"
            "کانفیگ ۱\n"
            "کانفیگ ۲\n"
        )
        bot.send_message(ADMIN_ID, prompt, parse_mode="Markdown")
    elif message.text == "📋 لیست/مدیریت پلن‌ها":
        show_plan_management_panel(ADMIN_ID)
    elif message.text == "🔄 ریستارت ربات":
        bot.send_message(ADMIN_ID, "در حال ری‌استارت...")
        os.system(f"systemctl restart {SERVICE_NAME}")
    elif message.text == "📊 آمار":
        show_statistics(ADMIN_ID)
    elif message.text.startswith("/addplan"):
        process_new_plan_message(message)
    else:
        bot.send_message(ADMIN_ID, "دستور نامشخص است.", reply_markup=get_admin_keyboard())

def process_new_plan_message(message):
    try:
        # حذف /addplan از ابتدای پیام
        content = message.text.replace("/addplan", "").strip()
        parts = content.split('---')
        if len(parts) != 2: raise ValueError("فرمت پیام صحیح نیست (باید از '---' استفاده شود).")
        header, configs_str = parts[0].strip(), parts[1].strip()
        header_lines = header.split('\n')
        if len(header_lines) != 3: raise ValueError("بخش اول باید شامل ۳ خط (نام، قیمت، زمان) باشد.")
        name, price_str, duration_str = header_lines[0].strip(), header_lines[1].strip(), header_lines[2].strip()
        price, duration = int(price_str), int(duration_str)
        configs = [line.strip() for line in configs_str.split('\n') if line.strip()]
        if not configs: raise ValueError("حداقل یک کانفیگ باید وارد شود.")

        plan_id = str(uuid.uuid4())
        conn, c = db_connect()
        c.execute("INSERT INTO plans (plan_id, name, price, duration_days) VALUES (?, ?, ?, ?)", (plan_id, name, price, duration))
        conn.commit()
        conn.close()

        filepath = os.path.join(PLANS_CONFIG_DIR, f"{plan_id}.txt")
        with open(filepath, 'w', encoding='utf-8') as f:
            for config_line in configs: f.write(config_line + '\n')

        bot.send_message(ADMIN_ID, f"✅ پلن جدید '{name}' با موفقیت ساخته شد.", reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"خطا در افزودن پلن: {e}")
        bot.send_message(ADMIN_ID, f"❌ خطایی در پردازش پیام رخ داد:\n`{e}`", parse_mode="Markdown", reply_markup=get_admin_keyboard())

def show_plan_management_panel(chat_id):
    conn, c = db_connect()
    c.execute("SELECT * FROM plans ORDER BY price")
    plans = c.fetchall()
    conn.close()
    if not plans:
        bot.send_message(chat_id, "هیچ پلنی تعریف نشده است.")
        return
        
    for plan in plans:
        config_path = os.path.join(PLANS_CONFIG_DIR, f"{plan['plan_id']}.txt")
        try:
            with open(config_path, 'r') as f: available = len(f.readlines())
        except: available = 0
        
        response = (f"🔹 **{plan['name']}** - {plan['price']:,} تومان ({plan['duration_days']} روز)\n"
                    f"   - موجودی کانفیگ: {available}\n"
                    f"   - ID: `{plan['plan_id']}`\n\n"
                    "برای افزودن کانفیگ به این پلن، روی این پیام ریپلای کرده و کانفیگ‌ها را ارسال کنید.")
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"🗑 حذف این پلن", callback_data=f"delete_plan_{plan['plan_id']}"))
        bot.send_message(chat_id, response, parse_mode="Markdown", reply_markup=markup)

def process_add_configs_to_plan(message):
    try:
        plan_id_line = [line for line in message.reply_to_message.text.split('\n') if 'ID:' in line]
        plan_id = plan_id_line[0].split('`')[1]

        new_configs = message.text.strip().split('\n')
        filepath = os.path.join(PLANS_CONFIG_DIR, f"{plan_id}.txt")
        with open(filepath, 'a', encoding='utf-8') as f:
            for config in new_configs: f.write(config + '\n')
        
        bot.reply_to(message, f"✅ تعداد {len(new_configs)} کانفیگ جدید به پلن اضافه شد.")
    except Exception as e:
        logger.error(f"خطا در افزودن کانفیگ به پلن: {e}")
        bot.reply_to(message, "خطا در پردازش. لطفاً روی پیام صحیح ریپلای کنید.")


def process_admin_charge_confirmation(message):
    try:
        amount_to_add = int(message.text)
        user_id_line = [line for line in message.reply_to_message.text.split('\n') if 'آیدی:' in line]
        target_user_id = int(user_id_line[0].split('`')[1])

        update_user_balance(target_user_id, amount_to_add, top_up=True)
        new_balance = get_user_balance(target_user_id)
        
        bot.send_message(ADMIN_ID, f"✅ مبلغ {amount_to_add:,} تومان به کیف پول کاربر {target_user_id} اضافه شد.")
        bot.send_message(target_user_id, f"✅ کیف پول شما توسط ادمین به مبلغ {amount_to_add:,} تومان شارژ شد.\nموجودی جدید: {new_balance:,} تومان")
    except Exception as e:
        logger.error(f"خطا در پردازش تایید شارژ: {e}")
        bot.reply_to(message, "خطا در پردازش. لطفاً مطمئن شوید مبلغ را به عدد و روی پیام صحیح ریپلای کرده‌اید.")

def show_statistics(chat_id):
    conn, c = db_connect()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT user_id) FROM services WHERE expiry_date >= date('now')")
    active_customers = c.fetchone()[0]
    c.execute("SELECT COUNT(*), SUM(p.price) FROM services s JOIN plans p ON s.plan_id = p.plan_id")
    sales_info = c.fetchone()
    total_sales, total_income = sales_info if sales_info else (0, 0)
    total_income = total_income or 0
    conn.close()
    
    stats_text = (
        f"📊 **آمار کلی ربات:**\n\n"
        f"👥 **کاربران:**\n"
        f"   -  تعداد کل کاربران ربات: {total_users}\n"
        f"   -  مشتریان دارای سرویس فعال: {active_customers}\n\n"
        f"📈 **فروش و درآمد:**\n"
        f"   -  تعداد کل سرویس‌های فروخته شده: {total_sales}\n"
        f"   -  درآمد کل: {total_income:,} تومان"
    )
    bot.send_message(chat_id, stats_text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    
    if user_id == ADMIN_ID:
        if data.startswith("delete_plan_"):
            plan_id_to_delete = data.split('_')[2]
            conn, c = db_connect()
            c.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id_to_delete,))
            c.execute("DELETE FROM services WHERE plan_id = ?", (plan_id_to_delete,))
            conn.commit()
            conn.close()
            filepath = os.path.join(PLANS_CONFIG_DIR, f"{plan_id_to_delete}.txt")
            if os.path.exists(filepath): os.remove(filepath)
            bot.answer_callback_query(call.id, "پلن با موفقیت حذف شد.")
            bot.delete_message(call.message.chat.id, call.message.message_id)
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
                bot.answer_callback_query(call.id, "خرید انجام شد.")
                bot.send_message(user_id, f"✅ خرید **{plan['name']}** انجام شد.\nکانفیگ:\n`{config}`", parse_mode="Markdown")
            else: bot.answer_callback_query(call.id, "موجودی کانفیگ تمام شده.", show_alert=True)
        else: bot.answer_callback_query(call.id, "موجودی کافی نیست.", show_alert=True)
    elif data == 'charge_wallet':
        bot.answer_callback_query(call.id)
        msg = bot.send_message(user_id, "لطفاً مبلغ شارژ را به تومان وارد کنید (فقط عدد):")
        bot.register_next_step_handler(msg, process_charge_user_amount)

def process_charge_user_amount(message):
    try:
        amount = int(message.text)
        if amount <= 0: raise ValueError()
        payment_info = (f"برای شارژ **{amount:,} تومان**، وجه را به کارت زیر واریز و رسید را ارسال کنید:\n\n💳 `{os.getenv('CARD_NUMBER')}`\n👤 **{os.getenv('CARD_HOLDER')}**")
        bot.send_message(message.chat.id, payment_info, parse_mode="Markdown")
    except ValueError: 
        msg = bot.send_message(message.chat.id, "لطفاً عدد صحیح و مثبت وارد کنید.")
        bot.register_next_step_handler(msg, process_charge_user_amount)

if __name__ == "__main__":
    init_db()
    logger.info("ربات با معماری پایدار در حال شروع به کار (Polling)...")
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        logger.error(f"خطای مرگبار در حلقه اصلی ربات: {e}")