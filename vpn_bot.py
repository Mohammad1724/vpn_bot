import telebot
from telebot import types
import os
from dotenv import load_dotenv
import qrcode
import io
import logging
import json
import random

# تنظیم logging
logging.basicConfig(filename='bot_log.txt', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# لود تنظیمات از .env
load_dotenv()

# چک متغیرهای ضروری
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else None
CARD_NUMBER = os.getenv('CARD_NUMBER', '6037-XXXX-XXXX-XXXX')  # شماره کارت پیش‌فرض
PLANS_STR = os.getenv('PLANS', '1GB:10000,10GB:50000,Unlimited:100000')
PLANS = {p.split(':')[0]: int(p.split(':')[1]) for p in PLANS_STR.split(',')} if PLANS_STR else {}

if not BOT_TOKEN or not ADMIN_ID:
    logging.error("BOT_TOKEN یا ADMIN_ID در .env وجود ندارد!")
    print("خطا: BOT_TOKEN یا ADMIN_ID تنظیم نشده.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# فایل‌های ذخیره (JSON برای پایداری)
CONFIG_FILE = 'configs.json'  # ذخیره کانفیگ‌ها
PAYMENT_FILE = 'payments.json'  # ذخیره پرداخت‌ها

# لود کانفیگ‌ها از فایل
def load_configs():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return []

# ذخیره کانفیگ‌ها
def save_configs(configs):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=4)

# لود پرداخت‌ها
def load_payments():
    if os.path.exists(PAYMENT_FILE):
        with open(PAYMENT_FILE, 'r') as f:
            return json.load(f)
    return []

# ذخیره پرداخت‌ها
def save_payments(payments):
    with open(PAYMENT_FILE, 'w') as f:
        json.dump(payments, f, indent=4)

CONFIGS = load_configs()
PAYMENTS = load_payments()

# هندلر شروع
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

# راهنما
@bot.message_handler(commands=['help'], func=lambda m: m.text == 'راهنما')
def help_command(message):
    help_text = """
    راهنما:
    - /start: شروع
    - خرید VPN: پلن انتخاب کن، رسید کارت به کارت بفرست، منتظر تایید ادمین باش.
    - /get_config: اگر پرداخت تایید شده باشه، کانفیگ بگیر.
    - ادمین: /add_config, /delete_config, /pending_payments, /stats
    """
    bot.send_message(message.chat.id, help_text)

# خرید VPN (انتخاب پلن)
@bot.message_handler(func=lambda message: message.text == 'خرید VPN')
def buy_vpn(message):
    markup = types.InlineKeyboardMarkup()
    for plan, price in PLANS.items():
        btn = types.InlineKeyboardButton(f"{plan} - {price} تومان", callback_data=f"plan_{plan}")
    markup.add(*markup.keyboard[0])  # اضافه کردن دکمه‌ها
    bot.send_message(message.chat.id, "پلن مورد نظر رو انتخاب کن:", reply_markup=markup)

# هندل انتخاب پلن (callback)
@bot.callback_query_handler(func=lambda call: call.data.startswith('plan_'))
def select_plan(call):
    plan = call.data.split('_')[1]
    price = PLANS[plan]
    bot.answer_callback_query(call.id, f"پلن {plan} انتخاب شد.")
    bot.send_message(call.message.chat.id, f"پلن: {plan}\nقیمت: {price} تومان\nشماره کارت: {CARD_NUMBER}\n\nرسید پرداخت رو (عکس یا متن) بفرست.")
    bot.register_next_step_handler(call.message, lambda m: handle_receipt(m, call.from_user.id, plan, price))

# هندل رسید پرداخت
def handle_receipt(message, user_id, plan, price):
    receipt = message.text or "عکس رسید ارسال شد" if message.photo else None
    if not receipt:
        bot.reply_to(message, "رسید معتبر بفرست (متن یا عکس).")
        return
    # ذخیره پرداخت در حال انتظار
    PAYMENTS.append({'user_id': user_id, 'plan': plan, 'price': price, 'receipt': receipt, 'status': 'pending'})
    save_payments(PAYMENTS)
    bot.reply_to(message, "رسید دریافت شد. منتظر تایید ادمین باش.")
    logging.info(f"رسید جدید از {user_id} برای {plan}")

# پنل ادمین
@bot.message_handler(func=lambda message: message.text == 'پنل ادمین')
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    markup = types.InlineKeyboardMarkup()
    btn_add = types.InlineKeyboardButton('اضافه کانفیگ', callback_data='add_config')
    btn_del = types.InlineKeyboardButton('حذف کانفیگ', callback_data='delete_config')
    btn_pending = types.InlineKeyboardButton('رسیدهای در انتظار', callback_data='pending_payments')
    btn_stats = types.InlineKeyboardButton('آمار', callback_data='stats')
    markup.add(btn_add, btn_del, btn_pending, btn_stats)
    bot.send_message(message.chat.id, "پنل ادمین:", reply_markup=markup)

# هندل callback ادمین
@bot.callback_query_handler(func=lambda call: True)
def admin_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    if call.data == 'add_config':
        bot.answer_callback_query(call.id, "کانفیگ جدید وارد کن.")
        bot.send_message(call.message.chat.id, "کانفیگ رو بفرست (فرمت: نام:لینک:حجم:زمان انقضا، مثال: Test:vless://uuid@server:port:1GB:30روز)")
        bot.register_next_step_handler(call.message, add_config_handler)
    elif call.data == 'delete_config':
        bot.answer_callback_query(call.id, "نام کانفیگ برای حذف رو بفرست.")
        bot.register_next_step_handler(call.message, delete_config_handler)
    elif call.data == 'pending_payments':
        show_pending_payments(call.message.chat.id)
    elif call.data == 'stats':
        show_stats(call.message.chat.id)
    logging.info(f"ادمین callback: {call.data}")

# اضافه کانفیگ دستی
def add_config_handler(message):
    parts = message.text.split(':')
    if len(parts) != 4:
        bot.reply_to(message, "فرمت اشتباه! مثال: نام:لینک:حجم:زمان")
        return
    name, link, volume, expiry = parts
    CONFIGS.append({'name': name, 'link': link, 'volume': volume, 'expiry': expiry})
    save_configs(CONFIGS)
    bot.reply_to(message, f"کانفیگ {name} اضافه شد.")
    logging.info(f"کانفیگ جدید: {name}")

# حذف کانفیگ
def delete_config_handler(message):
    name = message.text.strip()
    global CONFIGS
    CONFIGS = [c for c in CONFIGS if c['name'] != name]
    save_configs(CONFIGS)
    bot.reply_to(message, f"کانفیگ {name} حذف شد." if name in [c['name'] for c in CONFIGS] else "کانفیگ پیدا نشد.")
    logging.info(f"حذف کانفیگ: {name}")

# نمایش رسیدهای در انتظار
def show_pending_payments(chat_id):
    pending = [p for p in PAYMENTS if p['status'] == 'pending']
    if not pending:
        bot.send_message(chat_id, "هیچ رسیدی در انتظار نیست.")
        return
    for idx, p in enumerate(pending):
        markup = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton('تایید', callback_data=f"confirm_{idx}")
        btn_reject = types.InlineKeyboardButton('رد', callback_data=f"reject_{idx}")
        markup.add(btn_confirm, btn_reject)
        bot.send_message(chat_id, f"رسید {idx+1}: کاربر {p['user_id']}, پلن {p['plan']}, رسید: {p['receipt']}", reply_markup=markup)

# هندل تایید/رد (callback)
@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_') or call.data.startswith('reject_'))
def handle_payment_action(call):
    if call.from_user.id != ADMIN_ID:
        return
    action, idx = call.data.split('_')
    idx = int(idx)
    if action == 'confirm':
        PAYMENTS[idx]['status'] = 'confirmed'
        user_id = PAYMENTS[idx]['user_id']
        if CONFIGS:
            config = random.choice(CONFIGS)
            bot.send_message(user_id, f"پرداخت تایید شد! کانفیگ شما: {config['link']}\nحجم: {config['volume']}, انقضا: {config['expiry']}")
            # ارسال QR
            qr_img = generate_qr(config['link'])
            bot.send_photo(user_id, qr_img, caption="QR کد کانفیگ")
        else:
            bot.send_message(user_id, "پرداخت تایید شد اما کانفیگی موجود نیست!")
        bot.answer_callback_query(call.id, "تایید شد.")
    else:
        PAYMENTS[idx]['status'] = 'rejected'
        bot.send_message(PAYMENTS[idx]['user_id'], "پرداخت رد شد. دوباره سعی کن.")
        bot.answer_callback_query(call.id, "رد شد.")
    save_payments(PAYMENTS)
    logging.info(f"پرداخت {idx} {action} شد.")

# آمار
def show_stats(chat_id):
    total_users = len(set(p['user_id'] for p in PAYMENTS))
    successful = len([p for p in PAYMENTS if p['status'] == 'confirmed'])
    total_revenue = sum(p['price'] for p in PAYMENTS if p['status'] == 'confirmed')
    stats_text = f"آمار:\nکاربران: {total_users}\nپرداخت‌های موفق: {successful}\nدرآمد کل: {total_revenue} تومان\nکانفیگ‌های موجود: {len(CONFIGS)}"
    bot.send_message(chat_id, stats_text)

# تولید QR کد
def generate_qr(link):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    bio = io.BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio

# پشتیبانی
@bot.message_handler(func=lambda message: message.text == 'پشتیبانی')
def support(message):
    bot.send_message(message.chat.id, "برای پشتیبانی، پیامت رو بفرست یا با ادمین تماس بگیر.")

# شروع polling
if __name__ == '__main__':
    logging.info("بات شروع شد.")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"خطا: {e}")
        print(f"خطا: {e}")
