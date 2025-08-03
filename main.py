# main.py
import os
import sqlite3
import logging
import datetime
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import uuid
import time
from hiddify_api import HiddifyAPI

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
    HIDDIFY_PANEL_DOMAIN = os.getenv("HIDDIFY_PANEL_DOMAIN")
    HIDDIFY_ADMIN_UUID = os.getenv("HIDDIFY_ADMIN_UUID")
    HIDDIFY_ADMIN_USER = os.getenv("HIDDIFY_ADMIN_USER")
    HIDDIFY_ADMIN_PASS = os.getenv("HIDDIFY_ADMIN_PASS")

    if not all([TOKEN, ADMIN_ID_STR, CARD_NUMBER, CARD_HOLDER, HIDDIFY_PANEL_DOMAIN, HIDDIFY_ADMIN_UUID, HIDDIFY_ADMIN_USER, HIDDIFY_ADMIN_PASS]):
        logger.error("فایل .env یافت نشد یا متغیرهای ضروری در آن تعریف نشده‌اند.")
        logger.error("لطفاً ابتدا اسکریپت setup.py را اجرا کنید.")
        exit("خطا در بارگذاری تنظیمات.")
    ADMIN_ID = int(ADMIN_ID_STR)
except (ValueError, TypeError) as e:
    logger.error(f"خطا در متغیرهای محیطی: {e}")
    exit(1)

DB_FILE = "bot_database.db"
bot = telebot.TeleBot(TOKEN)
user_states = {}

try:
    hiddify_client = HiddifyAPI(
        panel_domain=HIDDIFY_PANEL_DOMAIN,
        admin_uuid=HIDDIFY_ADMIN_UUID,
        admin_user=HIDDIFY_ADMIN_USER,
        admin_pass=HIDDIFY_ADMIN_PASS
    )
except ConnectionError as e:
    logger.error(f"نمی‌توان به پنل Hiddify متصل شد: {e}")
    exit("اتصال به Hiddify ناموفق بود. ربات متوقف می‌شود.")


# --- توابع دیتابیس ---
def db_connect():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db_connect()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, wallet_balance INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS plans (plan_id TEXT PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL, duration_days INTEGER NOT NULL, data_limit_gb INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS services (service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id TEXT, hiddify_uuid TEXT NOT NULL, purchase_date DATE, is_active INTEGER DEFAULT 1, FOREIGN KEY (user_id) REFERENCES users (user_id), FOREIGN KEY (plan_id) REFERENCES plans (plan_id))')
    conn.commit()
    conn.close()

# ... (سایر توابع کمکی ربات در اینجا قرار می‌گیرند)
def add_or_update_user(user_id, first_name, username):
    conn = db_connect()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)", (user_id, first_name, username))
    c.execute("UPDATE users SET first_name = ?, username = ? WHERE user_id = ?", (first_name, username, user_id))
    conn.commit()
    conn.close()

def get_user_balance(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result['wallet_balance'] if result else 0
    
# --- کیبوردها ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ افزودن پلن"), KeyboardButton("📋 مدیریت پلن‌ها"))
    markup.row(KeyboardButton("📊 آمار"))
    return markup

def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🛍 خرید سرویس"), KeyboardButton("🔄 سرویس‌های من"))
    markup.row(KeyboardButton("💰 کیف پول"))
    return markup
    
# --- منطق اصلی و هندلرها ---
# (این بخش‌ها عمدتاً شبیه کدهای قبلی هستند، اما برای کامل بودن آورده شده‌اند)

@bot.message_handler(commands=['start', 'cancel'])
def send_welcome(message):
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
        bot.send_message(user_id, "عملیات لغو شد.")

    add_or_update_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    if user_id == ADMIN_ID:
        bot.send_message(user_id, "به پنل مدیریت Hiddify خوش آمدید.", reply_markup=get_admin_keyboard())
    else:
        balance = get_user_balance(user_id)
        bot.send_message(user_id, f"سلام {message.from_user.first_name} عزیز!\n💰 موجودی: **{balance:,} تومان**", parse_mode="Markdown", reply_markup=get_user_keyboard())

def process_purchase(user_id, plan_id, call):
    # این تابع از کد قبلی با کمی تغییر استفاده می‌شود
    conn = db_connect()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
        plan = c.fetchone()
        c.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,))
        user_db = c.fetchone()
        balance = user_db['wallet_balance']

        if not plan:
            bot.answer_callback_query(call.id, "پلن یافت نشد!", show_alert=True)
            return
        if balance < plan['price']:
            bot.answer_callback_query(call.id, "موجودی کافی نیست.", show_alert=True)
            return

        user_name = f"user_{user_id}_{int(time.time())}"
        new_hiddify_user = hiddify_client.create_user(
            name=user_name,
            package_days=plan['duration_days'],
            package_size_gb=plan['data_limit_gb'],
            telegram_id=user_id
        )

        if not new_hiddify_user:
            bot.answer_callback_query(call.id, "خطا در ارتباط با پنل. لطفاً بعداً تلاش کنید.", show_alert=True)
            bot.send_message(ADMIN_ID, "⚠️ خطا در ایجاد کاربر جدید در Hiddify!")
            return

        hiddify_uuid = new_hiddify_user['uuid']
        subscription_link = new_hiddify_user['subscription_link']
        
        c.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?", (plan['price'], user_id))
        purchase_date = datetime.date.today()
        c.execute("INSERT INTO services (user_id, plan_id, hiddify_uuid, purchase_date, is_active) VALUES (?, ?, ?, ?, 1)", 
                  (user_id, plan_id, hiddify_uuid, purchase_date))
        
        conn.commit()

        bot.answer_callback_query(call.id, "خرید با موفقیت انجام شد.")
        response_text = (f"✅ خرید **{plan['name']}** با موفقیت انجام شد.\n\n"
                         f"این لینک اشتراک شماست. آن را کپی کرده و در اپلیکیشن خود وارد کنید:\n\n"
                         f"`{subscription_link}`")
        bot.edit_message_text(response_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=None)
    except Exception as e:
        conn.rollback()
        logger.error(f"خطا در تراکنش خرید Hiddify برای کاربر {user_id}: {e}")
        bot.answer_callback_query(call.id, "خطایی در فرآیند خرید رخ داد.", show_alert=True)
    finally:
        conn.close()

def show_my_services(user_id):
    # این تابع نیز از کد قبلی استفاده می‌کند
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT s.hiddify_uuid, p.name AS plan_name FROM services s JOIN plans p ON s.plan_id = p.plan_id WHERE s.user_id = ? AND s.is_active = 1", (user_id,))
    active_services_db = c.fetchall()
    
    if not active_services_db:
        bot.send_message(user_id, "شما در حال حاضر هیچ سرویس فعالی ندارید.")
        conn.close()
        return
        
    response_text = "سرویس‌های فعال شما:\n\n"
    found_any_active = False
    
    for service_db in active_services_db:
        h_uuid = service_db['hiddify_uuid']
        user_info = hiddify_client.get_user(h_uuid)
        
        if user_info and user_info.get('enable', False):
            found_any_active = True
            usage = user_info.get('current_usage_GB', 0)
            limit = user_info.get('data_limit_GB', 0)
            
            try:
                start_date_str = user_info.get('start_date') or user_info.get('last_reset_time')
                package_days = user_info.get('package_days', 30)
                start_date = datetime.datetime.fromisoformat(start_date_str.replace("Z", "+00:00")).date()
                expiry_date = start_date + datetime.timedelta(days=package_days)
                days_left = (expiry_date - datetime.date.today()).days
            except:
                days_left = "نامشخص"

            response_text += (
                f"🔹 **{service_db['plan_name']}**\n"
                f"   - مصرف: **{usage:.2f} / {limit} گیگابایت**\n"
                f"   - روزهای باقی‌مانده: **{days_left if days_left >= 0 else 'منقضی شده'}**\n"
                f"   - لینک اشتراک: `{os.getenv('HIDDIFY_PANEL_DOMAIN')}/{os.getenv('HIDDIFY_ADMIN_UUID')}/{h_uuid}/`\n\n"
            )

    conn.close()
    if found_any_active:
        bot.send_message(user_id, response_text, parse_mode="Markdown")
    else:
        bot.send_message(user_id, "شما در حال حاضر هیچ سرویس فعالی ندارید.")

# ... (سایر هندلرها مانند handle_callbacks, handle_user_text_messages و ... باید اینجا قرار گیرند)
# برای کامل بودن، یک نمونه از مهمترین هندلرها در اینجا آورده می‌شود
@bot.message_handler(func=lambda m: m.from_user.id != ADMIN_ID, content_types=['text'])
def handle_user_text_messages(message):
    # ... (از کد قبلی)
    pass
    
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    # ... (از کد قبلی، با فراخوانی process_purchase)
    user_id = call.from_user.id
    data = call.data.split('_')
    action = data[0]
    if action == 'buy':
        plan_id = data[1]
        process_purchase(user_id, plan_id, call)
    # ... سایر اکشن‌ها
    
# کد اجرایی اصلی
if __name__ == "__main__":
    init_db()
    logger.info("ربات متصل به Hiddify در حال شروع به کار است...")
    try:
        bot.infinity_polling(timeout=60, logger_level=logging.WARNING)
    except Exception as e:
        logger.error(f"خطای مرگبار در حلقه اصلی ربات: {e}")