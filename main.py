# main.py (نسخه بازنویسی‌شده، پایدار و بهینه)

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
SERVICE_NAME = "vpn_bot.service" # برای دستور ریستارت
bot = telebot.TeleBot(TOKEN)

# دیکشنری برای مدیریت وضعیت کاربر (جایگزین register_next_step_handler)
user_states = {}

# --- توابع دیتابیس و کمکی ---
def db_connect():
    """یک اتصال جدید به دیتابیس برقرار می‌کند"""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()

def init_db():
    """جداول دیتابیس را در صورت عدم وجود ایجاد می‌کند"""
    conn, c = db_connect()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, wallet_balance INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS plans (plan_id TEXT PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL, duration_days INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS services (service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id TEXT, config TEXT NOT NULL, purchase_date DATE, expiry_date DATE, FOREIGN KEY (user_id) REFERENCES users (user_id), FOREIGN KEY (plan_id) REFERENCES plans (plan_id))')
    # جدول جدید برای نگهداری کانفیگ‌ها
    c.execute('''
        CREATE TABLE IF NOT EXISTS configs (
            config_id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT NOT NULL,
            config_text TEXT NOT NULL UNIQUE,
            is_used INTEGER DEFAULT 0,
            assigned_user_id INTEGER,
            FOREIGN KEY (plan_id) REFERENCES plans (plan_id)
        )
    ''')
    conn.commit()
    conn.close()

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

def update_user_balance(user_id, amount):
    """موجودی کاربر را به صورت مستقیم افزایش می‌دهد (برای شارژ توسط ادمین)"""
    conn, c = db_connect()
    c.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_available_config_count(plan_id):
    """تعداد کانفیگ‌های استفاده نشده برای یک پلن را برمی‌گرداند"""
    conn, c = db_connect()
    c.execute("SELECT COUNT(*) FROM configs WHERE plan_id = ? AND is_used = 0", (plan_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def add_configs_to_db(plan_id, configs_list):
    """کانفیگ‌ها را به صورت دسته‌ای به دیتابیس اضافه می‌کند"""
    conn, c = db_connect()
    added_count = 0
    for config in configs_list:
        try:
            c.execute("INSERT INTO configs (plan_id, config_text) VALUES (?, ?)", (plan_id, config.strip()))
            if c.rowcount > 0:
                added_count += 1
        except sqlite3.IntegrityError:
            logger.warning(f"کانفیگ تکراری نادیده گرفته شد: {config[:30]}...")
    conn.commit()
    conn.close()
    return added_count

# --- کیبوردها ---
def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ افزودن پلن"), KeyboardButton("📋 مدیریت پلن‌ها"))
    markup.row(KeyboardButton("📊 آمار"), KeyboardButton("🔄 ریستارت ربات"))
    return markup

def get_user_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🛍 خرید سرویس"), KeyboardButton("🔄 سرویس‌های من"))
    markup.row(KeyboardButton("💰 کیف پول"))
    return markup

# --- مدیریت دستورات عمومی ---
@bot.message_handler(commands=['start', 'cancel'])
def send_welcome(message):
    user = message.from_user
    user_id = user.id
    # اگر کاربر در وضعیتی خاص بود، آن را لغو کن
    if user_id in user_states:
        del user_states[user_id]

    add_or_update_user(user_id, user.first_name, user.username)
    if user_id == ADMIN_ID:
        bot.send_message(user_id, "سلام ادمین عزیز! به پنل مدیریت خوش آمدید.", reply_markup=get_admin_keyboard())
    else:
        balance = get_user_balance(user_id)
        bot.send_message(user_id, f"سلام {user.first_name} عزیز!\n💰 موجودی: **{balance:,} تومان**", parse_mode="Markdown", reply_markup=get_user_keyboard())

# --- مدیریت پیام‌های کاربران عادی ---
@bot.message_handler(func=lambda m: m.from_user.id != ADMIN_ID and m.from_user.id not in user_states)
def handle_user_messages(message):
    user_id = message.from_user.id
    if message.content_type == 'text':
        if message.text == "🛍 خرید سرویس": show_plans_to_user(user_id)
        elif message.text == "💰 کیف پول": handle_wallet_request(user_id)
        elif message.text == "🔄 سرویس‌های من": show_my_services(user_id)
    elif message.content_type in ['photo', 'document']:
        handle_receipt(message)

# --- مدیریت پنل ادمین ---
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.from_user.id not in user_states)
def handle_admin_panel(message):
    if message.text == "➕ افزودن پلن":
        bot.send_message(ADMIN_ID, "لطفا نام پلن را وارد کنید:")
        user_states[ADMIN_ID] = {"state": "awaiting_plan_name"}
    elif message.text == "📋 مدیریت پلن‌ها":
        show_plan_management_panel(ADMIN_ID)
    elif message.text == "🔄 ریستارت ربات":
        bot.send_message(ADMIN_ID, "در حال ری‌استارت...")
        os.system(f"systemctl restart {SERVICE_NAME}")
    elif message.text == "📊 آمار":
        show_statistics(ADMIN_ID)
    else:
        bot.send_message(ADMIN_ID, "دستور نامشخص است.", reply_markup=get_admin_keyboard())

# --- مدیریت پیام‌های مبتنی بر وضعیت (Stateful) ---
@bot.message_handler(func=lambda message: message.from_user.id in user_states)
def handle_stateful_messages(message):
    user_id = message.from_user.id
    state_data = user_states[user_id]
    state = state_data.get("state")

    # وضعیت‌های مربوط به کاربر
    if state == "awaiting_charge_amount":
        try:
            amount = int(message.text)
            if amount <= 1000: raise ValueError("مبلغ کم است")
            payment_info = (f"برای شارژ **{amount:,} تومان**، وجه را به کارت زیر واریز و رسید را ارسال کنید:\n\n"
                            f"💳 `{CARD_NUMBER}`\n"
                            f"👤 **{CARD_HOLDER}**")
            bot.send_message(user_id, payment_info, parse_mode="Markdown")
        except (ValueError, TypeError):
            bot.send_message(user_id, "لطفاً مبلغ را به صورت یک عدد صحیح و مثبت (بیشتر از ۱۰۰۰ تومان) وارد کنید.")
        finally:
            del user_states[user_id] # خروج از وضعیت

    # وضعیت‌های مربوط به ادمین
    elif user_id == ADMIN_ID:
        try:
            if state == "awaiting_plan_name":
                user_states[ADMIN_ID]["name"] = message.text
                user_states[ADMIN_ID]["state"] = "awaiting_plan_price"
                bot.send_message(ADMIN_ID, f"نام پلن: '{message.text}'\nحالا قیمت را به تومان وارد کنید (فقط عدد):")
            elif state == "awaiting_plan_price":
                user_states[ADMIN_ID]["price"] = int(message.text)
                user_states[ADMIN_ID]["state"] = "awaiting_plan_duration"
                bot.send_message(ADMIN_ID, f"قیمت: {int(message.text):,} تومان\nحالا مدت زمان را به روز وارد کنید (فقط عدد):")
            elif state == "awaiting_plan_duration":
                user_states[ADMIN_ID]["duration"] = int(message.text)
                user_states[ADMIN_ID]["state"] = "awaiting_plan_configs"
                bot.send_message(ADMIN_ID, "عالی! حالا کانفیگ‌ها را ارسال کنید (هر کانفیگ در یک خط).")
            elif state == "awaiting_plan_configs":
                plan_info = user_states[ADMIN_ID]
                configs = [line.strip() for line in message.text.split('\n') if line.strip()]
                if not configs:
                    raise ValueError("حداقل یک کانفیگ باید وارد شود.")
                
                plan_id = str(uuid.uuid4())
                conn, c = db_connect()
                c.execute("INSERT INTO plans (plan_id, name, price, duration_days) VALUES (?, ?, ?, ?)", 
                          (plan_id, plan_info['name'], plan_info['price'], plan_info['duration']))
                conn.commit()
                conn.close()

                added_count = add_configs_to_db(plan_id, configs)
                bot.send_message(ADMIN_ID, f"✅ پلن '{plan_info['name']}' با {added_count} کانفیگ با موفقیت ساخته شد.", reply_markup=get_admin_keyboard())
                del user_states[ADMIN_ID]

            elif state == "awaiting_charge_confirmation":
                amount = int(message.text)
                target_user_id = state_data["target_user_id"]
                update_user_balance(target_user_id, amount)
                new_balance = get_user_balance(target_user_id)
                bot.send_message(ADMIN_ID, f"✅ مبلغ {amount:,} تومان به کیف پول کاربر {target_user_id} اضافه شد.", reply_markup=get_admin_keyboard())
                bot.send_message(target_user_id, f"✅ کیف پول شما توسط ادمین به مبلغ {amount:,} تومان شارژ شد.\nموجودی جدید: {new_balance:,} تومان")
                del user_states[ADMIN_ID]

            elif state == "awaiting_configs_for_plan":
                plan_id = state_data["plan_id"]
                configs = [line.strip() for line in message.text.split('\n') if line.strip()]
                added_count = add_configs_to_db(plan_id, configs)
                bot.send_message(ADMIN_ID, f"✅ تعداد {added_count} کانفیگ جدید به پلن اضافه شد.", reply_markup=get_admin_keyboard())
                del user_states[ADMIN_ID]

        except (ValueError, TypeError):
            bot.send_message(ADMIN_ID, "❌ ورودی نامعتبر است. لطفاً دوباره تلاش کنید یا /cancel را بزنید.")
        except Exception as e:
            logger.error(f"خطا در پردازش وضعیت ادمین: {e}")
            bot.send_message(ADMIN_ID, f"❌ خطایی رخ داد: {e}", reply_markup=get_admin_keyboard())
            if ADMIN_ID in user_states: del user_states[ADMIN_ID]


# --- پردازشگر Callback Query ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data.split('_')
    action = data[0]

    if user_id == ADMIN_ID:
        if action == "deleteplan":
            plan_id_to_delete = data[1]
            conn, c = db_connect()
            c.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id_to_delete,))
            c.execute("DELETE FROM services WHERE plan_id = ?", (plan_id_to_delete,))
            c.execute("DELETE FROM configs WHERE plan_id = ?", (plan_id_to_delete,)) # حذف کانفیگ‌ها از دیتابیس
            conn.commit()
            conn.close()
            bot.answer_callback_query(call.id, "پلن و تمام کانفیگ‌های مرتبط با آن حذف شد.")
            bot.delete_message(call.message.chat.id, call.message.message_id)
        
        elif action == "confirmcharge":
            target_user_id = int(data[1])
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, f"لطفاً مبلغ شارژ برای کاربر `{target_user_id}` را به عدد وارد کنید:", parse_mode="Markdown")
            user_states[ADMIN_ID] = {"state": "awaiting_charge_confirmation", "target_user_id": target_user_id}
            
        elif action == "addconfigs":
            plan_id = data[1]
            bot.answer_callback_query(call.id)
            bot.send_message(ADMIN_ID, "لطفا کانفیگ‌های جدید را ارسال کنید (هر کانفیگ در یک خط):")
            user_states[ADMIN_ID] = {"state": "awaiting_configs_for_plan", "plan_id": plan_id}

    else: # منطق برای کاربران عادی
        if action == "buy":
            plan_id = data[1]
            process_purchase(user_id, plan_id, call)

        elif action == 'chargewallet':
            bot.answer_callback_query(call.id)
            bot.send_message(user_id, "لطفاً مبلغ شارژ را به تومان وارد کنید (فقط عدد):")
            user_states[user_id] = {"state": "awaiting_charge_amount"}

def process_purchase(user_id, plan_id, call):
    """پردازش خرید سرویس با استفاده از تراکنش"""
    conn, c = db_connect()
    try:
        # دریافت اطلاعات پلن و موجودی کاربر
        c.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
        plan = c.fetchone()
        c.execute("SELECT wallet_balance FROM users WHERE user_id = ?", (user_id,))
        balance = c.fetchone()['wallet_balance']

        if not plan:
            bot.answer_callback_query(call.id, "پلن یافت نشد!", show_alert=True)
            return

        if balance < plan['price']:
            bot.answer_callback_query(call.id, "موجودی کافی نیست. لطفاً کیف پول خود را شارژ کنید.", show_alert=True)
            return

        # پیدا کردن و اختصاص دادن یک کانفیگ (بخش مهم تراکنش)
        c.execute("SELECT config_id, config_text FROM configs WHERE plan_id = ? AND is_used = 0 LIMIT 1", (plan_id,))
        config_row = c.fetchone()
        
        if not config_row:
            bot.answer_callback_query(call.id, "متاسفانه موجودی کانفیگ این پلن تمام شده است.", show_alert=True)
            bot.send_message(ADMIN_ID, f"⚠️ هشدار: موجودی کانفیگ پلن {plan['name']} تمام شد!")
            return

        config_id, config_text = config_row['config_id'], config_row['config_text']

        # شروع تراکنش: تمام عملیات زیر یا با هم انجام می‌شوند یا هیچکدام
        # 1. کم کردن موجودی کاربر
        c.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE user_id = ?", (plan['price'], user_id))
        
        # 2. علامت‌گذاری کانفیگ به عنوان استفاده شده
        c.execute("UPDATE configs SET is_used = 1, assigned_user_id = ? WHERE config_id = ?", (user_id, config_id))
        
        # 3. ایجاد سرویس برای کاربر
        purchase_date = datetime.date.today()
        expiry_date = purchase_date + datetime.timedelta(days=plan['duration_days'])
        c.execute("INSERT INTO services (user_id, plan_id, config, purchase_date, expiry_date) VALUES (?, ?, ?, ?, ?)", 
                  (user_id, plan_id, config_text, purchase_date, expiry_date))
        
        # ثبت نهایی تمام تغییرات
        conn.commit()

        bot.answer_callback_query(call.id, "خرید با موفقیت انجام شد.")
        bot.send_message(user_id, f"✅ خرید **{plan['name']}** با موفقیت انجام شد.\n\nکانفیگ شما:\n`{config_text}`", parse_mode="Markdown")

    except Exception as e:
        # در صورت بروز هرگونه خطا، تمام تغییرات لغو می‌شود
        conn.rollback()
        logger.error(f"خطا در تراکنش خرید برای کاربر {user_id}: {e}")
        bot.answer_callback_query(call.id, "خطایی در فرآیند خرید رخ داد. لطفاً مجددا تلاش کنید.", show_alert=True)
    finally:
        # اتصال به دیتابیس بسته می‌شود
        conn.close()

# --- توابع نمایش اطلاعات ---
def show_plans_to_user(user_id):
    conn, c = db_connect()
    c.execute("SELECT * FROM plans ORDER BY price")
    plans = c.fetchall()
    conn.close()
    if not plans:
        bot.send_message(user_id, "در حال حاضر هیچ پلنی برای فروش وجود ندارد.")
        return
    
    markup = InlineKeyboardMarkup()
    for plan in plans:
        available_configs = get_available_config_count(plan['plan_id'])
        if available_configs > 0:
            btn_text = f"{plan['name']} - {plan['price']:,} تومان ({plan['duration_days']} روز)"
            markup.add(InlineKeyboardButton(btn_text, callback_data=f"buy_{plan['plan_id']}"))

    if len(markup.keyboard) > 0:
        bot.send_message(user_id, "لطفاً پلن مورد نظر خود را انتخاب کنید:", reply_markup=markup)
    else:
        bot.send_message(user_id, "متاسفانه موجودی تمام پلن‌ها به اتمام رسیده است.")


def show_my_services(user_id):
    conn, c = db_connect()
    c.execute("""
        SELECT s.config, s.expiry_date, p.name 
        FROM services s JOIN plans p ON s.plan_id = p.plan_id
        WHERE s.user_id = ? AND s.expiry_date >= date('now')
    """, (user_id,))
    active_services = c.fetchall()
    conn.close()

    if not active_services:
        bot.send_message(user_id, "شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return
    
    response = "سرویس‌های فعال شما:\n\n"
    for service in active_services:
        response += (f"🔹 **{service['name']}**\n"
                     f"   - تاریخ انقضا: {service['expiry_date']}\n"
                     f"   - کانفیگ: `{service['config']}`\n\n")
    bot.send_message(user_id, response, parse_mode="Markdown")

def handle_wallet_request(user_id):
    balance = get_user_balance(user_id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("افزایش موجودی", callback_data="chargewallet"))
    bot.send_message(user_id, f"موجودی فعلی شما: **{balance:,} تومان**", reply_markup=markup, parse_mode="Markdown")

def handle_receipt(message):
    user = message.from_user
    add_or_update_user(user.id, user.first_name, user.username)
    
    msg_to_admin = (f"رسید شارژ کیف پول از:\n"
                    f"👤 کاربر: {user.first_name}\n"
                    f"🆔 آیدی: `{user.id}`\n\n"
                    "برای تایید، روی دکمه زیر کلیک کرده و مبلغ را وارد کنید.")
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ تایید و شارژ", callback_data=f"confirmcharge_{user.id}"))

    bot.forward_message(ADMIN_ID, user.id, message.message_id)
    bot.send_message(ADMIN_ID, msg_to_admin, reply_markup=markup, parse_mode="Markdown")
    bot.reply_to(message, "✅ رسید شما برای ادمین ارسال شد. پس از تایید، کیف پول شما شارژ خواهد شد.")

def show_plan_management_panel(chat_id):
    conn, c = db_connect()
    c.execute("SELECT * FROM plans ORDER BY price")
    plans = c.fetchall()
    conn.close()
    if not plans:
        bot.send_message(chat_id, "هیچ پلنی تعریف نشده است. از دکمه '➕ افزودن پلن' استفاده کنید.")
        return
        
    for plan in plans:
        available = get_available_config_count(plan['plan_id'])
        response = (f"🔹 **{plan['name']}** - {plan['price']:,} تومان ({plan['duration_days']} روز)\n"
                    f"   - موجودی کانفیگ: {available}\n"
                    f"   - ID: `{plan['plan_id']}`")
        
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("➕ افزودن کانفیگ", callback_data=f"addconfigs_{plan['plan_id']}"),
            InlineKeyboardButton("🗑 حذف پلن", callback_data=f"deleteplan_{plan['plan_id']}")
        )
        bot.send_message(chat_id, response, parse_mode="Markdown", reply_markup=markup)

def show_statistics(chat_id):
    conn, c = db_connect()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT user_id) FROM services WHERE expiry_date >= date('now')")
    active_customers = c.fetchone()[0]
    c.execute("SELECT COUNT(*), SUM(p.price) FROM services s JOIN plans p ON s.plan_id = p.plan_id")
    sales_info = c.fetchone()
    total_sales, total_income = (sales_info[0] or 0, sales_info[1] or 0)
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


if __name__ == "__main__":
    init_db()
    logger.info("ربات با معماری بهینه و پایدار در حال شروع به کار (Polling)...")
    try:
        bot.infinity_polling(timeout=60, logger_level=logging.WARNING)
    except Exception as e:
        logger.error(f"خطای مرگبار در حلقه اصلی ربات: {e}")
