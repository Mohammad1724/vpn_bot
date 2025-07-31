import telebot
from telebot import types
import os
from dotenv import load_dotenv
import qrcode
import io
import logging
import json
import random

logging.basicConfig(filename='bot_log.txt', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else None
CARD_NUMBER = os.getenv('CARD_NUMBER', '6037-XXXX-XXXX-XXXX')
PLANS_STR = os.getenv('PLANS', '1GB:10000,10GB:50000,Unlimited:100000')
PLANS = {p.split(':')[0]: int(p.split(':')[1]) for p in PLANS_STR.split(',')} if PLANS_STR else {}

if not BOT_TOKEN or not ADMIN_ID:
    logging.error("BOT_TOKEN یا ADMIN_ID تنظیم نشده!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

CONFIG_FILE = 'configs.json'
PAYMENT_FILE = 'payments.json'

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

CONFIGS = load_configs()
PAYMENTS = load_payments()

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

@bot.message_handler(commands=['help'], func=lambda m: m.text == 'راهنما')
def help_command(message):
    help_text = """
    راهنما:
    - خرید VPN: پلن انتخاب کن، رسید کارت به کارت بفرست، منتظر تایید باش.
    - /get_config: اگر پرداخت تایید شده باشه، کانفیگ بگیر.
    - ادمین: /add_config, /delete_config, /pending_payments, /stats
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
    # چک تکراری (ساده)
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
        bot.reply_to(message, "پرداخت تاییدشده‌ای نداری. اول خرید کن.")
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

# دیگر هندلرها (پنل ادمین, اضافه/حذف کانفیگ, pending_payments, stats) مثل کد قبلی هستن – برای کوتاهی تکرار نکردم، اما در کد کامل قبلی هستن.

if __name__ == '__main__':
    logging.info("بات شروع شد.")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"خطا: {e}")
