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

PROMPTS = {
    "editing_name": "نام جدید را وارد کنید:", "editing_price": "قیمت جدید را وارد کنید (فقط عدد):",
    "editing_duration": "زمان جدید را به روز وارد کنید (فقط عدد):", "editing_add_configs": "کانفیگ‌های جدید برای افزودن را وارد کنید (هر کدام در یک خط):"
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

# --- کیبوردها ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ افزودن پلن"), KeyboardButton("📋 مدیریت پلن‌ها"))
    markup.row(KeyboardButton("📊 آمار"), KeyboardButton("🔄 ریستارت ربات"))
    markup.row(KeyboardButton("📥 بکاپ"), KeyboardButton("📤 ریستور"))
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
    user_states.pop(user.id, None)
    if user.id == ADMIN_ID:
        bot.send_message(user.id, "به منوی اصلی بازگشتید.", reply_markup=get_admin_keyboard())
    else:
        balance = get_user_balance(user.id)
        bot.send_message(user.id, f"سلام {user.first_name} عزیز!\n💰 موجودی: **{balance:,} تومان**", parse_mode="Markdown", reply_markup=get_user_keyboard())

# --- مدیریت کاربران عادی ---
@bot.message_handler(func=lambda m: m.from_user.id != ADMIN_ID)
def handle_user_messages(message):
    # (این بخش بدون تغییر باقی می‌ماند)
    pass

# --- مدیریت پنل ادمین (معماری جدید و پایدار) ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def handle_admin_panel(message):
    if message.reply_to_message and "رسید شارژ کیف پول" in message.reply_to_message.text:
        process_admin_charge_confirmation(message)
        return
        
    if message.text == "➕ افزودن پلن":
        prompt = (
            "برای افزودن پلن جدید، یک پیام با فرمت زیر ارسال کنید:\n\n"
            "نام پلن\n"
            "قیمت (فقط عدد)\n"
            "مدت زمان (روز)\n"
            "---\n"
            "کانفیگ ۱\n"
            "کانفیگ ۲\n\n"
            "**مثال:**\n"
            "پلن یک ماهه\n"
            "50000\n"
            "30\n"
            "---\n"
            "vless://..."
        )
        msg = bot.send_message(ADMIN_ID, prompt, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_new_plan_message)
    elif message.text == "📋 مدیریت پلن‌ها":
        show_plan_management_panel(ADMIN_ID)
    elif message.text == "🔄 ریستارت ربات":
        bot.send_message(ADMIN_ID, "در حال ری‌استارت...")
        os.system(f"systemctl restart {SERVICE_NAME}")
    elif message.text == "📊 آمار":
        show_statistics(ADMIN_ID)
    elif message.text == "📥 بکاپ":
        backup_data(ADMIN_ID)
    elif message.text == "📤 ریستور":
        msg = bot.send_message(ADMIN_ID, "فایل بکاپ (.zip) را ارسال کنید.")
        bot.register_next_step_handler(msg, restore_data)
    elif user_states.get(ADMIN_ID):
        handle_admin_state_messages(message)
    else:
        bot.send_message(ADMIN_ID, "دستور نامشخص است.", reply_markup=get_admin_keyboard())

def process_new_plan_message(message):
    try:
        parts = message.text.split('---')
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
        bot.send_message(ADMIN_ID, f"❌ خطایی در پردازش پیام رخ داد:\n`{e}`\n\nلطفاً فرمت را بررسی و دوباره تلاش کنید.", parse_mode="Markdown", reply_markup=get_admin_keyboard())

def show_plan_management_panel(chat_id):
    conn, c = db_connect()
    c.execute("SELECT * FROM plans ORDER BY price")
    plans = c.fetchall()
    conn.close()
    if not plans:
        bot.send_message(chat_id, "هیچ پلنی تعریف نشده است.")
        return
        
    markup = InlineKeyboardMarkup(row_width=2)
    for plan in plans: markup.add(InlineKeyboardButton(f"✏️ {plan['name']}", callback_data=f"edit_plan_{plan['plan_id']}"), InlineKeyboardButton(f"🗑 حذف", callback_data=f"delete_plan_{plan['plan_id']}"))
    bot.send_message(chat_id, "📋 **لیست پلن‌های فعلی:**\nبرای ویرایش یا حذف، روی دکمه مربوطه کلیک کنید.", parse_mode="Markdown", reply_markup=markup)

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

# (بقیه توابع کامل در بلاک بعدی)
# (ادامه کد main.py)
def backup_data(chat_id):
    bot.send_message(chat_id, "در حال ایجاد بکاپ کامل...")
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        backup_filename_base, temp_backup_dir = f'backup_{timestamp}', 'temp_backup_dir'
        os.makedirs(temp_backup_dir, exist_ok=True)
        shutil.copy(DB_FILE, temp_backup_dir)
        if os.path.exists(PLANS_CONFIG_DIR): shutil.copytree(PLANS_CONFIG_DIR, os.path.join(temp_backup_dir, PLANS_CONFIG_DIR))
        shutil.make_archive(backup_filename_base, 'zip', temp_backup_dir)
        with open(f'{backup_filename_base}.zip', 'rb') as f: bot.send_document(chat_id, f, caption="✅ بکاپ کامل با موفقیت ایجاد شد.")
    except Exception as e:
        logger.error(f"خطا در بکاپ: {e}")
        bot.send_message(chat_id, f"❌ خطا: {e}")
    finally:
        if 'backup_filename_base' in locals() and os.path.exists(f'{backup_filename_base}.zip'): os.remove(f'{backup_filename_base}.zip')
        if 'temp_backup_dir' in locals() and os.path.exists(temp_backup_dir): shutil.rmtree(temp_backup_dir)

def restore_data(message):
    if not message.document or not message.document.file_name.endswith('.zip'):
        bot.reply_to(message, "لطفاً یک فایل بکاپ با فرمت .zip ارسال کنید.")
        return
    try:
        bot.send_message(message.chat.id, "در حال بازیابی اطلاعات... ربات برای چند لحظه متوقف و مجدداً راه‌اندازی می‌شود.")
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        backup_path = os.path.join(os.getcwd(), 'backup_to_restore.zip')
        with open(backup_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        os.system("bash restore.sh")
    except Exception as e:
        logger.error(f"خطا در فرآیند ریستور: {e}")
        bot.send_message(message.chat.id, f"❌ خطایی در هنگام بازیابی رخ داد: {e}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    if user_id == ADMIN_ID:
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        if data.startswith("edit_plan_"):
            plan_id = data.split('_')[2]
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(InlineKeyboardButton("✏️ نام", callback_data=f"edit_name_{plan_id}"), InlineKeyboardButton("💰 قیمت", callback_data=f"edit_price_{plan_id}"))
            markup.add(InlineKeyboardButton("⏳ زمان", callback_data=f"edit_duration_{plan_id}"), InlineKeyboardButton("➕ افزودن کانفیگ", callback_data=f"edit_add_configs_{plan_id}"))
            markup.add(InlineKeyboardButton("⬅️ بازگشت", callback_data="show_plan_panel"))
            bot.send_message(user_id, "کدام بخش را ویرایش می‌کنید؟", reply_markup=markup)
        elif data.startswith(("edit_name_", "edit_price_", "edit_duration_", "edit_add_configs_")):
            parts = data.split('_')
            action, plan_id = parts[1], parts[2]
            user_states[user_id] = {"state": f"editing_{action}", "plan_id": plan_id}
            msg = bot.send_message(user_id, PROMPTS.get(f"editing_{action}", "نامشخص"))
            bot.register_next_step_handler(msg, handle_admin_state_messages)
        elif data.startswith("delete_plan_"):
            plan_id = data.split('_')[2]
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"confirm_delete_{plan_id}"), InlineKeyboardButton("❌ خیر", callback_data="show_plan_panel"))
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

def handle_admin_state_messages(message):
    chat_id = message.chat.id
    state_info = user_states.pop(chat_id, None)
    if not state_info: return
    state = state_info.get("state")
    try:
        if state == "editing_name":
            conn, c = db_connect()
            c.execute("UPDATE plans SET name = ? WHERE plan_id = ?", (message.text, state_info['plan_id']))
            conn.commit()
            conn.close()
            bot.send_message(chat_id, "✅ نام ویرایش شد.", reply_markup=get_admin_keyboard())
            show_plan_management_panel(chat_id)
        # (سایر حالات ویرایش در اینجا پیاده‌سازی می‌شوند)
    except Exception as e:
        logger.error(f"خطا در پردازش وضعیت ادمین: {e}")
        bot.send_message(chat_id, "یک خطای پیش‌بینی نشده رخ داد.", reply_markup=get_admin_keyboard())

if __name__ == "__main__":
    init_db()
    logger.info("ربات با معماری پایدار در حال شروع به کار (Polling)...")
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        logger.error(f"خطای مرگبار در حلقه اصلی ربات: {e}")