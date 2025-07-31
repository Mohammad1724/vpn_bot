#!/usr/bin/env python3
# vpn_bot.py

import os
import json
import logging
from datetime import datetime, timedelta
import telebot
from telebot import types
import random
import string

# تنظیمات
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
CARD_NUMBER = os.getenv('CARD_NUMBER', '6037-xxxx-xxxx-xxxx')
CARD_HOLDER = os.getenv('CARD_HOLDER', 'نام صاحب کارت')
DATA_FILE = 'bot_data.json'

bot = telebot.TeleBot(BOT_TOKEN)
logging.basicConfig(level=logging.INFO)

# بارگذاری/ذخیره دیتا
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'configs': [],
        'users': {},
        'orders': [],
        'plans': [
            {'id': 1, 'name': '1 ماهه', 'days': 30, 'price': 50000},
            {'id': 2, 'name': '3 ماهه', 'days': 90, 'price': 120000},
            {'id': 3, 'name': '6 ماهه', 'days': 180, 'price': 200000}
        ],
        'card_info': {
            'number': CARD_NUMBER,
            'holder': CARD_HOLDER
        }
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_order_id():
    return ''.join(random.choices(string.digits, k=8))

# کیبورد ادمین
def admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('➕ افزودن کانفیگ', '📋 لیست کانفیگ‌ها')
    markup.row('💳 تنظیم کارت', '📊 لیست سفارشات')
    markup.row('💰 مدیریت پلن‌ها', '✅ تایید پرداخت‌ها')
    markup.row('🔙 بازگشت')
    return markup

# دستورات ادمین
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    bot.send_message(message.chat.id, "🔧 پنل مدیریت:", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.text == '➕ افزودن کانفیگ' and m.from_user.id == ADMIN_ID)
def add_config(message):
    msg = bot.send_message(message.chat.id, "کانفیگ جدید را ارسال کنید:")
    bot.register_next_step_handler(msg, process_config)

def process_config(message):
    data = load_data()
    config_id = len(data['configs']) + 1
    
    config = {
        'id': config_id,
        'config': message.text,
        'status': 'available',
        'created_at': datetime.now().isoformat()
    }
    
    data['configs'].append(config)
    save_data(data)
    
    bot.send_message(message.chat.id, f"✅ کانفیگ #{config_id} اضافه شد", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.text == '📋 لیست کانفیگ‌ها' and m.from_user.id == ADMIN_ID)
def list_configs(message):
    data = load_data()
    if not data['configs']:
        bot.send_message(message.chat.id, "❌ کانفیگی موجود نیست")
        return
    
    text = "📋 لیست کانفیگ‌ها:\n\n"
    available = 0
    sold = 0
    
    for config in data['configs']:
        if config['status'] == 'available':
            available += 1
        else:
            sold += 1
    
    text += f"✅ موجود: {available}\n"
    text += f"❌ فروخته شده: {sold}\n"
    text += f"📊 مجموع: {len(data['configs'])}"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == '💳 تنظیم کارت' and m.from_user.id == ADMIN_ID)
def set_card(message):
    msg = bot.send_message(message.chat.id, "شماره کارت جدید را وارد کنید:")
    bot.register_next_step_handler(msg, process_card_number)

def process_card_number(message):
    msg = bot.send_message(message.chat.id, "نام صاحب کارت را وارد کنید:")
    bot.register_next_step_handler(msg, process_card_holder, message.text)

def process_card_holder(message, card_number):
    data = load_data()
    data['card_info'] = {
        'number': card_number,
        'holder': message.text
    }
    save_data(data)
    bot.send_message(message.chat.id, "✅ اطلاعات کارت ذخیره شد", reply_markup=admin_keyboard())

@bot.message_handler(func=lambda m: m.text == '💰 مدیریت پلن‌ها' and m.from_user.id == ADMIN_ID)
def manage_plans(message):
    data = load_data()
    text = "📋 پلن‌های فعلی:\n\n"
    
    for plan in data['plans']:
        text += f"🔸 {plan['name']}: {plan['price']:,} تومان\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ افزودن پلن", callback_data="add_plan"))
    markup.add(types.InlineKeyboardButton("✏️ ویرایش پلن‌ها", callback_data="edit_plans"))
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '📊 لیست سفارشات' and m.from_user.id == ADMIN_ID)
def list_orders(message):
    data = load_data()
    pending = [o for o in data['orders'] if o['status'] == 'pending']
    
    if not pending:
        bot.send_message(message.chat.id, "❌ سفارش در انتظاری وجود ندارد")
        return
    
    text = f"📋 سفارشات در انتظار تایید: {len(pending)}\n\n"
    for order in pending[-10:]:
        text += f"🔸 کد: {order['order_id']}\n"
        text += f"👤 کاربر: {order['user_name']}\n"
        text += f"💰 مبلغ: {order['amount']:,} تومان\n"
        text += f"📅 زمان: {order['date'][:16]}\n"
        text += "➖➖➖➖➖\n"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == '✅ تایید پرداخت‌ها' and m.from_user.id == ADMIN_ID)
def confirm_payments(message):
    data = load_data()
    pending = [o for o in data['orders'] if o['status'] == 'pending']
    
    if not pending:
        bot.send_message(message.chat.id, "❌ سفارشی برای تایید وجود ندارد")
        return
    
    order = pending[0]
    text = f"""
🔸 سفارش #{order['order_id']}
👤 کاربر: {order['user_name']}
💰 مبلغ: {order['amount']:,} تومان
📱 پلن: {order['plan_name']}
📅 زمان: {order['date'][:16]}

آیا این پرداخت را تایید می‌کنید؟
"""
    
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"confirm_{order['order_id']}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"reject_{order['order_id']}")
    )
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

# دستورات کاربر
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🛒 خرید VPN', '📞 پشتیبانی')
    markup.row('📊 سفارشات من', '❓ راهنما')
    
    welcome_text = """
🌐 به ربات فروش VPN خوش آمدید!

✅ سرویس‌های پرسرعت و پایدار
✅ پشتیبانی 24/7
✅ قیمت‌های مناسب
✅ پرداخت امن کارت به کارت

برای شروع روی دکمه 'خرید VPN' کلیک کنید.
"""
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '🛒 خرید VPN')
def buy_vpn(message):
    data = load_data()
    available_configs = [c for c in data['configs'] if c['status'] == 'available']
    
    if not available_configs:
        bot.send_message(message.chat.id, "❌ متاسفانه در حال حاضر سرویسی موجود نیست")
        return
    
    text = "📋 پلن مورد نظر خود را انتخاب کنید:\n\n"
    markup = types.InlineKeyboardMarkup()
    
    for plan in data['plans']:
        text += f"🔸 {plan['name']}: {plan['price']:,} تومان\n"
        markup.add(types.InlineKeyboardButton(
            f"{plan['name']} - {plan['price']:,} تومان", 
            callback_data=f"buy_{plan['id']}"
        ))
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def process_purchase(call):
    plan_id = int(call.data.split('_')[1])
    data = load_data()
    plan = next((p for p in data['plans'] if p['id'] == plan_id), None)
    
    if not plan:
        bot.answer_callback_query(call.id, "❌ پلن یافت نشد")
        return
    
    order_id = generate_order_id()
    
    # ذخیره سفارش
    order = {
        'order_id': order_id,
        'user_id': call.from_user.id,
        'user_name': call.from_user.first_name,
        'plan_id': plan_id,
        'plan_name': plan['name'],
        'amount': plan['price'],
        'status': 'pending',
        'date': datetime.now().isoformat()
    }
    
    data['orders'].append(order)
    save_data(data)
    
    # ارسال اطلاعات پرداخت
    payment_text = f"""
💳 اطلاعات پرداخت:

🔸 شماره کارت: `{data['card_info']['number']}`
🔸 به نام: {data['card_info']['holder']}
🔸 مبلغ: {plan['price']:,} تومان
🔸 کد پیگیری: {order_id}

⚠️ لطفا دقیقا مبلغ فوق را واریز کنید
⚠️ بعد از واریز، رسید را ارسال کنید
"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📸 ارسال رسید", callback_data=f"receipt_{order_id}"))
    
    bot.send_message(call.message.chat.id, payment_text, parse_mode='Markdown', reply_markup=markup)
    
    # اطلاع به ادمین
    bot.send_message(ADMIN_ID, f"🔔 سفارش جدید!\n👤 {call.from_user.first_name}\n💰 {plan['price']:,} تومان\n🔢 کد: {order_id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('receipt_'))
def request_receipt(call):
    order_id = call.data.split('_')[1]
    msg = bot.send_message(call.message.chat.id, "📸 لطفا تصویر رسید پرداخت را ارسال کنید:")
    bot.register_next_step_handler(msg, process_receipt, order_id)

def process_receipt(message, order_id):
    if not message.photo:
        bot.send_message(message.chat.id, "❌ لطفا تصویر رسید را ارسال کنید")
        return
    
    # ارسال رسید به ادمین
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    bot.send_message(ADMIN_ID, f"🔢 رسید مربوط به سفارش: {order_id}")
    
    bot.send_message(message.chat.id, 
                    "✅ رسید شما دریافت شد\n⏳ در حال بررسی...\n\n"
                    "معمولا در کمتر از 5 دقیقه تایید می‌شود.")

@bot.callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_'))
def confirm_order(call):
    order_id = call.data.split('_')[1]
    data = load_data()
    
    # پیدا کردن سفارش
    order = next((o for o in data['orders'] if o['order_id'] == order_id), None)
    if not order:
        bot.answer_callback_query(call.id, "❌ سفارش یافت نشد")
        return
    
    # پیدا کردن کانفیگ موجود
    available_config = next((c for c in data['configs'] if c['status'] == 'available'), None)
    if not available_config:
        bot.answer_callback_query(call.id, "❌ کانفیگی موجود نیست")
        return
    
    # تایید سفارش
    order['status'] = 'completed'
    order['config_id'] = available_config['id']
    available_config['status'] = 'sold'
    available_config['user_id'] = order['user_id']
    save_data(data)
    
    # ارسال کانفیگ به کاربر
    config_text = f"""
✅ پرداخت شما تایید شد!

🔐 کانفیگ شما:
    
📅 اعتبار: {data['plans'][order['plan_id']-1]['days']} روز
🆔 کد سفارش: {order_id}

❓ در صورت نیاز به راهنمایی از بخش پشتیبانی استفاده کنید.
"""
    
    bot.send_message(order['user_id'], config_text, parse_mode='Markdown')
    bot.edit_message_text(f"✅ سفارش {order_id} تایید شد", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_order(call):
    order_id = call.data.split('_')[1]
    data = load_data()
    
    order = next((o for o in data['orders'] if o['order_id'] == order_id), None)
    if order:
        order['status'] = 'rejected'
        save_data(data)
        
        bot.send_message(order['user_id'], 
                        f"❌ متاسفانه پرداخت شما تایید نشد.\n"
                        f"کد سفارش: {order_id}\n\n"
                        "لطفا با پشتیبانی تماس بگیرید.")
        
        bot.edit_message_text(f"❌ سفارش {order_id} رد شد", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda message: message.text == '📊 سفارشات من')
def my_orders(message):
    data = load_data()
    user_orders = [o for o in data['orders'] if o['user_id'] == message.from_user.id]
    
    if not user_orders:
        bot.send_message(message.chat.id, "❌ شما هنوز سفارشی ثبت نکرده‌اید")
        return
    
    text = "📋 سفارشات شما:\n\n"
    for order in user_orders[-5:]:  # آخرین 5 سفارش
        status_emoji = "✅" if order['status'] == 'completed' else "⏳" if order['status'] == 'pending' else "❌"
        text += f"{status_emoji} کد: {order['order_id']}\n"
        text += f"📅 تاریخ: {order['date'][:10]}\n"
        text += f"💰 مبلغ: {order['amount']:,} تومان\n"
        text += "➖➖➖➖➖\n"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda message: message.text == '📞 پشتیبانی')
def support(message):
    bot.send_message(message.chat.id, 
                    "📞 برای ارتباط با پشتیبانی:\n\n"
                    "👤 @your_support\n"
                    "📧 support@example.com\n\n"
                    "⏰ پاسخگویی: 24/7")

@bot.message_handler(func=lambda message: message.text == '❓ راهنما')
def help_guide(message):
    help_text = """
📚 راهنمای استفاده:

1️⃣ روی دکمه 'خرید VPN' کلیک کنید
2️⃣ پلن مورد نظر را انتخاب کنید
3️⃣ مبلغ را به شماره کارت اعلامی واریز کنید
4️⃣ رسید پرداخت را ارسال کنید
5️⃣ منتظر تایید و دریافت کانفیگ باشید

⚡️ معمولا تایید در کمتر از 5 دقیقه انجام می‌شود

❓ سوالات متداول:
• آیا نیاز به نرم‌افزار خاصی دارم؟ بله، از V2Ray استفاده کنید
• چگونه کانفیگ را وارد کنم؟ کانفیگ را کپی و در برنامه Import کنید
• اگر کانفیگ کار نکرد؟ با پشتیبانی تماس بگیرید
"""
    bot.send_message(message.chat.id, help_text)

# اجرای ربات
if __name__ == '__main__':
    print("🤖 ربات VPN شروع به کار کرد...")
    print(f"👤 Admin ID: {ADMIN_ID}")
    bot.infinity_polling()
