import telebot
from telebot import types
import os
from dotenv import load_dotenv
import qrcode
import io
import logging
import json
import random
import sys
import shutil
import time

# ---------- Setup Section: Create .env if not exists ----------
def setup_env():
    if not os.path.exists('.env'):
        print("فایل .env پیدا نشد. اطلاعات زیر را وارد کنید:")
        bot_token = input("توکن ربات تلگرام: ").strip()
        admin_id = input("آیدی عددی ادمین (مثلاً 123456789): ").strip()
        card_number = input("شماره کارت (مثلاً 6037-XXXX-XXXX-XXXX): ").strip()
        with open('.env', 'w') as f:
            f.write(f"BOT_TOKEN={bot_token}\n")
            f.write(f"ADMIN_ID={admin_id}\n")
            f.write(f"CARD_NUMBER={card_number}\n")
        print("فایل .env ساخته شد!\n")

setup_env()
# -------------------------------------------------------------

logging.basicConfig(filename='bot_log.txt', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else None
CARD_NUMBER = os.getenv('CARD_NUMBER', '6037-XXXX-XXXX-XXXX')

if not BOT_TOKEN or not ADMIN_ID:
    logging.error("BOT_TOKEN یا ADMIN_ID تنظیم نشده!")
    print("خطا: BOT_TOKEN یا ADMIN_ID تنظیم نشده.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

CONFIG_FILE = 'configs.json'
PAYMENT_FILE = 'payments.json'
PLANS_FILE = 'plans.json'
BACKUP_DIR = 'backups'

def load_configs():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return []

def save_configs(configs):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=4)

def load_payments():
    if os.path.exists(PAYMENT_FILE):
        with open(PAYMENT_FILE, 'r') as f:
            return json.load(f)
    return []

def save_payments(payments):
    with open(PAYMENT_FILE, 'w') as f:
        json.dump(payments, f, indent=4)

def load_plans():
    if os.path.exists(PLANS_FILE):
        with open(PLANS_FILE, 'r') as f:
            return json.load(f)
    # مقدار پیش‌فرض اگر فایل نبود
    return {
        "1GB": 10000,
        "10GB": 50000,
        "Unlimited": 100000
    }

def save_plans(plans):
    with open(PLANS_FILE, 'w') as f:
        json.dump(plans, f, indent=4)

CONFIGS = load_configs()
PAYMENTS = load_payments()
PLANS = load_plans()

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_buy = types.KeyboardButton('خرید VPN')
    btn_support = types.KeyboardButton('پشتیبانی')
    btn_help = types.KeyboardButton('راهنما')
    btn_admin = types.KeyboardButton('پنل ادمین') if message.from_user.id == ADMIN_ID else None
    markup.add(btn_buy, btn_support, btn_help)
    if btn_admin:
        markup.add(btn_admin)
    bot.send_message(message.chat.id, "سلام! به ربات فروش VPN دستی خوش آمدید.", reply_markup=markup)
    logging.info(f"کاربر {message.from_user.id} شروع کرد.")

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """
    راهنما:
    - خرید VPN: پلن انتخاب کن، رسید کارت به کارت بفرست، منتظر تایید باش.
    - /get_config: اگر پرداخت تایید شده باشه، کانفیگ بگیر.
    - ادمین: پنل ادمین برای اضافه/حذف کانفیگ، تایید رسیدها، آمار.
    """
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(func=lambda message: message.text == 'خرید VPN')
def buy_vpn(message):
    markup = types.InlineKeyboardMarkup()
    for plan, price in PLANS.items():
        markup.add(types.InlineKeyboardButton(f"{plan} - {price} تومان", callback_data=f"plan_{plan}"))
    bot.send_message(message.chat.id, "پلن انتخاب کن:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('plan_'))
def select_plan(call):
    plan = call.data.split('_')[1]
    price = PLANS[plan]
    bot.answer_callback_query(call.id, f"پلن {plan} انتخاب شد.")
    bot.send_message(call.message.chat.id, f"پلن: {plan}\nقیمت: {price} تومان\nکارت: {CARD_NUMBER}\nرسید (عکس/متن) بفرست.")
    bot.register_next_step_handler(call.message, lambda m: handle_receipt(m, call.from_user.id, plan, price))

def handle_receipt(message, user_id, plan, price):
    receipt = message.text if message.text else (message.photo[0].file_id if message.photo else None)
    if not receipt:
        bot.reply_to(message, "رسید معتبر بفرست.")
        return
    if any(p['receipt'] == receipt and p['user_id'] == user_id for p in PAYMENTS):
        bot.reply_to(message, "این رسید قبلاً ارسال شده!")
        return
    PAYMENTS.append({'user_id': user_id, 'plan': plan, 'price': price, 'receipt': receipt, 'status': 'pending'})
    save_payments(PAYMENTS)
    bot.reply_to(message, "رسید دریافت شد. منتظر تایید باش.")
    logging.info(f"رسید جدید از {user_id}")

@bot.message_handler(commands=['get_config'])
def get_config(message):
    user_payments = [p for p in PAYMENTS if p['user_id'] == message.from_user.id and p['status'] == 'confirmed']
    if not user_payments:
        bot.reply_to(message, "پرداخت تاییدشده‌ای نداری.")
        return
    if not CONFIGS:
        bot.reply_to(message, "کانفیگی موجود نیست!")
        return
    config = random.choice(CONFIGS)
    bot.reply_to(message, f"کانفیگ: {config['link']}\nحجم: {config['volume']}, انقضا: {config['expiry']}")
    qr_img = generate_qr(config['link'])
    bot.send_photo(message.chat.id, qr_img, caption="QR کد")

def generate_qr(link):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    bio = io.BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio

@bot.message_handler(func=lambda message: message.text == 'پشتیبانی')
def support(message):
    bot.send_message(message.chat.id, "پیامت رو بفرست یا با ادمین تماس بگیر.")

@bot.message_handler(func=lambda message: message.text == 'پنل ادمین')
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    markup = types.InlineKeyboardMarkup()
    btn_add = types.InlineKeyboardButton('اضافه کانفیگ', callback_data='add_config')
    btn_del = types.InlineKeyboardButton('حذف کانفیگ', callback_data='delete_config')
    btn_pending = types.InlineKeyboardButton('رسیدهای در انتظار', callback_data='pending_payments')
    btn_stats = types.InlineKeyboardButton('آمار', callback_data='stats')
    btn_plans = types.InlineKeyboardButton('مدیریت پلن و قیمت', callback_data='manage_plans')
    btn_backup = types.InlineKeyboardButton('دریافت بکاپ', callback_data='backup')
    btn_log = types.InlineKeyboardButton('دریافت لاگ', callback_data='get_log')
    btn_restart = types.InlineKeyboardButton('ریستارت ربات', callback_data='restart_bot')
    btn_stop = types.InlineKeyboardButton('توقف ربات', callback_data='stop_bot')
    btn_delete = types.InlineKeyboardButton('حذف کامل ربات', callback_data='delete_bot')
    markup.add(btn_add, btn_del)
    markup.add(btn_pending, btn_stats)
    markup.add(btn_plans)
    markup.add(btn_backup, btn_log)
    markup.add(btn_restart, btn_stop)
    markup.add(btn_delete)
    bot.send_message(message.chat.id, "پنل ادمین:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def admin_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    if call.data == 'add_config':
        bot.answer_callback_query(call.id, "کانفیگ جدید وارد کن.")
        bot.send_message(call.message.chat.id, "فرمت: نام:لینک:حجم:زمان (مثل Test:vless://...:1GB:30روز)")
        bot.register_next_step_handler(call.message, add_config_handler)
    elif call.data == 'delete_config':
        bot.answer_callback_query(call.id, "نام کانفیگ برای حذف.")
        bot.register_next_step_handler(call.message, delete_config_handler)
    elif call.data == 'pending_payments':
        show_pending_payments(call.message.chat.id)
    elif call.data == 'stats':
        show_stats(call.message.chat.id)
    elif call.data == 'manage_plans':
        show_plans_menu(call.message.chat.id)
    elif call.data == 'add_plan':
        bot.send_message(call.message.chat.id, "فرمت: نام پلن:قیمت (مثال: 20GB:120000)")
        bot.register_next_step_handler(call.message, add_plan_handler)
    elif call.data == 'edit_plan':
        show_edit_plan_menu(call.message.chat.id)
    elif call.data.startswith('editprice_'):
        plan_name = call.data.split('_', 1)[1]
        bot.send_message(call.message.chat.id, f"قیمت جدید برای پلن {plan_name} را وارد کن:")
        bot.register_next_step_handler(call.message, lambda m: edit_plan_price_handler(m, plan_name))
    elif call.data == 'delete_plan':
        show_delete_plan_menu(call.message.chat.id)
    elif call.data.startswith('delplan_'):
        plan_name = call.data.split('_', 1)[1]
        if plan_name in PLANS:
            del PLANS[plan_name]
            save_plans(PLANS)
            bot.send_message(call.message.chat.id, f"پلن {plan_name} حذف شد.")
        else:
            bot.send_message(call.message.chat.id, "پلن پیدا نشد.")
        show_plans_menu(call.message.chat.id)
    elif call.data == 'back_admin':
        admin_panel(call.message)
    elif call.data == 'backup':
        send_backup(call.message.chat.id)
    elif call.data == 'get_log':
        send_log(call.message.chat.id)
    elif call.data == 'restart_bot':
        bot.answer_callback_query(call.id, "در حال ریستارت ربات...")
        bot.send_message(call.message.chat.id, "ربات در حال ریستارت است...")
        logging.info("ادمین درخواست ریستارت داد.")
        restart_bot()
    elif call.data == 'stop_bot':
        bot.answer_callback_query(call.id, "در حال توقف ربات...")
        bot.send_message(call.message.chat.id, "ربات متوقف شد.")
        logging.info("ادمین درخواست توقف داد.")
        stop_bot()
    elif call.data == 'delete_bot':
        bot.answer_callback_query(call.id, "در حال حذف کامل ربات...")
        bot.send_message(call.message.chat.id, "در حال حذف کامل ربات و فایل‌ها...")
        logging.info("ادمین درخواست حذف کامل داد.")
        delete_bot()
    elif call.data.startswith('confirm_') or call.data.startswith('reject_'):
        handle_payment_action(call)
    logging.info(f"ادمین callback: {call.data}")

def add_config_handler(message):
    parts = message.text.split(':')
    if len(parts) != 4:
        bot.reply_to(message, "فرمت اشتباه!")
        return
    name, link, volume, expiry = parts
    CONFIGS.append({'name': name.strip(), 'link': link.strip(), 'volume': volume.strip(), 'expiry': expiry.strip()})
    save_configs(CONFIGS)
    bot.reply_to(message, f"کانفیگ {name} اضافه شد.")
    logging.info(f"کانفیگ جدید: {name}")

def delete_config_handler(message):
    name = message.text.strip()
    global CONFIGS
    CONFIGS = [c for c in CONFIGS if c['name'] != name]
    save_configs(CONFIGS)
    bot.reply_to(message, f"کانفیگ {name} حذف شد.")
    logging.info(f"حذف کانفیگ: {name}")

def show_pending_payments(chat_id):
    pending = [p for p in PAYMENTS if p['status'] == 'pending']
    if not pending:
        bot.send_message(chat_id, "هیچ رسیدی در انتظار نیست.")
        return
    for idx, p in enumerate(pending):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('تایید', callback_data=f"confirm_{idx}"), types.InlineKeyboardButton('رد', callback_data=f"reject_{idx}"))
        bot.send_message(chat_id, f"رسید {idx+1}: کاربر {p['user_id']}, پلن {p['plan']}, رسید: {p['receipt']}", reply_markup=markup)

def handle_payment_action(call):
    action, idx = call.data.split('_')
    idx = int(idx)
    if action == 'confirm':
        PAYMENTS[idx]['status'] = 'confirmed'
        user_id = PAYMENTS[idx]['user_id']
        if CONFIGS:
            config = random.choice(CONFIGS)
            bot.send_message(user_id, f"پرداخت تایید شد! کانفیگ: {config['link']}\nحجم: {config['volume']}, انقضا: {config['expiry']}")
            qr_img = generate_qr(config['link'])
            bot.send_photo(user_id, qr_img, caption="QR کد")
        bot.answer_callback_query(call.id, "تایید شد.")
    else:
        PAYMENTS[idx]['status'] = 'rejected'
        bot.send_message(PAYMENTS[idx]['user_id'], "پرداخت رد شد.")
        bot.answer_callback_query(call.id, "رد شد.")
    save_payments(PAYMENTS)
    logging.info(f"پرداخت {idx} {action} شد.")

def show_stats(chat_id):
    total_users = len(set(p['user_id'] for p in PAYMENTS))
    successful = len([p for p in PAYMENTS if p['status'] == 'confirmed'])
    total_revenue = sum(p['price'] for p in PAYMENTS if p['status'] == 'confirmed')
    stats_text = f"آمار:\nکاربران: {total_users}\nپرداخت‌های موفق: {successful}\nدرآمد: {total_revenue} تومان\nکانفیگ‌ها: {len(CONFIGS)}"
    bot.send_message(chat_id, stats_text)

# ------------------- مدیریت پلن و قیمت -------------------
def show_plans_menu(chat_id):
    text = "پلن‌های فعلی:\n"
    for name, price in PLANS.items():
        text += f"- {name}: {price} تومان\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('افزودن پلن', callback_data='add_plan'))
    markup.add(types.InlineKeyboardButton('ویرایش قیمت', callback_data='edit_plan'))
    markup.add(types.InlineKeyboardButton('حذف پلن', callback_data='delete_plan'))
    markup.add(types.InlineKeyboardButton('بازگشت', callback_data='back_admin'))
    bot.send_message(chat_id, text, reply_markup=markup)

def add_plan_handler(message):
    try:
        name, price = message.text.split(':')
        name = name.strip()
        price = int(price.strip())
        if name in PLANS:
            bot.reply_to(message, "این پلن قبلاً وجود دارد.")
            return
        PLANS[name] = price
        save_plans(PLANS)
        bot.reply_to(message, f"پلن {name} با قیمت {price} تومان اضافه شد.")
    except:
        bot.reply_to(message, "فرمت اشتباه! مثال: 20GB:120000")
    show_plans_menu(message.chat.id)

def show_edit_plan_menu(chat_id):
    markup = types.InlineKeyboardMarkup()
    for name in PLANS:
        markup.add(types.InlineKeyboardButton(f"{name}", callback_data=f"editprice_{name}"))
    markup.add(types.InlineKeyboardButton('بازگشت', callback_data='manage_plans'))
    bot.send_message(chat_id, "کدام پلن را ویرایش می‌کنی؟", reply_markup=markup)

def edit_plan_price_handler(message, plan_name):
    try:
        price = int(message.text.strip())
        PLANS[plan_name] = price
        save_plans(PLANS)
        bot.reply_to(message, f"قیمت پلن {plan_name} به {price} تومان تغییر کرد.")
    except:
        bot.reply_to(message, "قیمت معتبر وارد کن (عدد).")
    show_plans_menu(message.chat.id)

def show_delete_plan_menu(chat_id):
    markup = types.InlineKeyboardMarkup()
    for name in PLANS:
        markup.add(types.InlineKeyboardButton(f"{name}", callback_data=f"delplan_{name}"))
    markup.add(types.InlineKeyboardButton('بازگشت', callback_data='manage_plans'))
    bot.send_message(chat_id, "کدام پلن را حذف می‌کنی؟", reply_markup=markup)
# --------------------------------------------------------

def send_backup(chat_id):
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_files = []
    for file in [CONFIG_FILE, PAYMENT_FILE, PLANS_FILE, '.env', 'bot_log.txt']:
        if os.path.exists(file):
            backup_path = os.path.join(BACKUP_DIR, f"{file}_{timestamp}")
            shutil.copy(file, backup_path)
            backup_files.append(backup_path)
    if backup_files:
        for f in backup_files:
            with open(f, 'rb') as doc:
                bot.send_document(chat_id, doc, caption=f"بکاپ {os.path.basename(f)}")
        bot.send_message(chat_id, "بکاپ ارسال شد.")
    else:
        bot.send_message(chat_id, "فایلی برای بکاپ پیدا نشد.")

def send_log(chat_id):
    if os.path.exists('bot_log.txt'):
        with open('bot_log.txt', 'rb') as log_file:
            bot.send_document(chat_id, log_file, caption="لاگ ربات")
    else:
        bot.send_message(chat_id, "فایل لاگ پیدا نشد.")

def restart_bot():
    python = sys.executable
    os.execl(python, python, *sys.argv)

def stop_bot():
    os._exit(0)

def delete_bot():
    files_to_delete = [CONFIG_FILE, PAYMENT_FILE, PLANS_FILE, '.env', 'bot_log.txt']
    for file in files_to_delete:
        if os.path.exists(file):
            os.remove(file)
    if os.path.exists(BACKUP_DIR):
        shutil.rmtree(BACKUP_DIR)
    bot.stop_polling()
    time.sleep(1)
    os._exit(0)

if __name__ == '__main__':
    logging.info("بات شروع شد.")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"خطا: {e}")
        print(f"خطا: {e}")
