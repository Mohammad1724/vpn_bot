# VPN Sales Bot - Complete Project Structure

## File: bot.py
import telebot
import sqlite3
import json
import requests
from datetime import datetime, timedelta
import uuid
import os
from config import *

class DatabaseManager:
    def __init__(self):
        self.db_name = 'vpn_bot.db'
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # جدول کاربران
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                phone TEXT,
                join_date TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # جدول سرویس‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER,
                duration_days INTEGER,
                traffic_gb INTEGER,
                description TEXT
            )
        ''')
        
        # جدول سفارشات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                payment_id TEXT,
                config_url TEXT,
                created_at TEXT,
                expires_at TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # اضافه کردن سرویس‌های پیش‌فرض
        self.add_default_services()
    
    def add_default_services(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM services')
        
        if cursor.fetchone()[0] == 0:
            default_services = [
                ("پکیج ۱ ماهه - ۵۰ گیگ", 50000, 30, 50, "مناسب استفاده شخصی روزانه"),
                ("پکیج ۳ ماهه - ۱۵۰ گیگ", 120000, 90, 150, "پرطرفدارترین پکیج - ۳۳٪ تخفیف"),
                ("پکیج ۶ ماهه - ۳۰۰ گیگ", 200000, 180, 300, "بهترین قیمت - ۴۴٪ تخفیف"),
                ("پکیج ویژه - نامحدود", 300000, 365, 1000, "یک سال کامل با ترافیک فراوان")
            ]
            
            cursor.executemany('''
                INSERT INTO services (name, price, duration_days, traffic_gb, description)
                VALUES (?, ?, ?, ?, ?)
            ''', default_services)
            conn.commit()
        
        conn.close()
    
    def add_user(self, user_id, username):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, join_date)
            VALUES (?, ?, ?)
        ''', (user_id, username, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def get_services(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM services WHERE id > 0')
        services = cursor.fetchall()
        conn.close()
        return services
    
    def get_service(self, service_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM services WHERE id = ?', (service_id,))
        service = cursor.fetchone()
        conn.close()
        return service
    
    def add_order(self, user_id, service_id, amount):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        order_id = str(uuid.uuid4())[:8].upper()
        cursor.execute('''
            INSERT INTO orders (user_id, service_id, amount, payment_id, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, service_id, amount, order_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return order_id
    
    def get_order(self, order_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, s.name, s.duration_days, s.traffic_gb 
            FROM orders o 
            JOIN services s ON o.service_id = s.id 
            WHERE o.payment_id = ?
        ''', (order_id,))
        order = cursor.fetchone()
        conn.close()
        return order
    
    def update_order_status(self, order_id, status, config_url=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        if config_url:
            expire_date = datetime.now() + timedelta(days=30)  # پیش‌فرض
            cursor.execute('''
                UPDATE orders 
                SET status = ?, config_url = ?, expires_at = ?
                WHERE payment_id = ?
            ''', (status, config_url, expire_date.isoformat(), order_id))
        else:
            cursor.execute('''
                UPDATE orders 
                SET status = ?
                WHERE payment_id = ?
            ''', (status, order_id))
        
        conn.commit()
        conn.close()
    
    def get_stats(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # کل کاربران
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # سفارشات امروز
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM orders WHERE created_at LIKE ?', (f'{today}%',))
        today_orders = cursor.fetchone()[0]
        
        # درآمد امروز
        cursor.execute('SELECT SUM(amount) FROM orders WHERE created_at LIKE ? AND status = "active"', (f'{today}%',))
        today_income = cursor.fetchone()[0] or 0
        
        # کل درآمد
        cursor.execute('SELECT SUM(amount) FROM orders WHERE status = "active"')
        total_income = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_users': total_users,
            'today_orders': today_orders,
            'today_income': today_income,
            'total_income': total_income
        }

class HiddifyManager:
    def __init__(self):
        self.api_url = HIDDIFY_API_URL.rstrip('/')
        self.api_key = HIDDIFY_API_KEY
    
    def test_connection(self):
        """تست اتصال به API"""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            response = requests.get(f'{self.api_url}/api/v1/admin/user/', 
                                  headers=headers, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def create_user(self, username, traffic_limit_gb, expire_days):
        """ایجاد کاربر جدید در پنل HiddiFy"""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'name': username,
                'usage_limit_GB': traffic_limit_gb,
                'package_days': expire_days,
                'mode': 'no_reset',
                'comment': f'Created by bot - {datetime.now().strftime("%Y-%m-%d %H:%M")}'
            }
            
            response = requests.post(f'{self.api_url}/api/v1/admin/user/', 
                                   json=data, headers=headers, timeout=30)
            
            if response.status_code in [200, 201]:
                result = response.json()
                return result.get('subscription_url') or result.get('config_url')
            
            return None
            
        except Exception as e:
            print(f"Error creating user: {e}")
            return None

class PaymentManager:
    def __init__(self):
        self.zarinpal_merchant = ZARINPAL_MERCHANT_ID
    
    def create_payment_url(self, amount, description, order_id):
        """ایجاد لینک پرداخت زرین‌پال"""
        if not self.zarinpal_merchant:
            return None
            
        try:
            data = {
                'merchant_id': self.zarinpal_merchant,
                'amount': amount,
                'description': description,
                'callback_url': f'{BOT_WEBHOOK_URL}/verify/{order_id}' if BOT_WEBHOOK_URL else 'https://example.com'
            }
            
            response = requests.post(
                'https://api.zarinpal.com/pg/v4/payment/request.json',
                json=data, timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('data', {}).get('code') == 100:
                    authority = result['data']['authority']
                    return f"https://www.zarinpal.com/pg/StartPay/{authority}"
            
            return None
            
        except:
            return None

# ایجاد instance ها
db = DatabaseManager()
hiddify = HiddifyManager()
payment = PaymentManager()
bot = telebot.TeleBot(BOT_TOKEN)

# کیبوردها
def main_keyboard():
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        telebot.types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy_service"),
        telebot.types.InlineKeyboardButton("💎 سرویس‌های من", callback_data="my_services")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support"),
        telebot.types.InlineKeyboardButton("ℹ️ راهنما", callback_data="help")
    )
    return keyboard

def services_keyboard():
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
    services = db.get_services()
    
    for service in services:
        discount = ""
        if service[3] >= 90:  # بیش از 3 ماه
            discount = " 🔥"
        
        text = f"📱 {service[1]} - {service[2]:,} تومان{discount}"
        keyboard.add(telebot.types.InlineKeyboardButton(
            text, callback_data=f"service_{service[0]}"
        ))
    
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    return keyboard

def admin_keyboard():
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        telebot.types.InlineKeyboardButton("📊 آمار", callback_data="admin_stats"),
        telebot.types.InlineKeyboardButton("👥 کاربران", callback_data="admin_users")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("📦 سرویس‌ها", callback_data="admin_services"),
        telebot.types.InlineKeyboardButton("💰 سفارشات", callback_data="admin_orders")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("🔧 تست سیستم", callback_data="admin_test"),
        telebot.types.InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_main")
    )
    return keyboard

# هندلرهای اصلی
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    db.add_user(user_id, username)
    
    welcome_text = f"""
🔥 سلام {message.from_user.first_name} عزیز!

به ربات فروش VPN پرسرعت خوش اومدی! 🚀

🌟 ویژگی‌های خاص ما:
✅ سرعت فوق‌العاده بالا
✅ پایداری ۹۹.۹٪ 
✅ پشتیبانی ۲۴ ساعته
✅ قیمت‌های استثنایی
✅ نصب آسان روی همه دستگاه‌ها
✅ بدون قطعی و فیلترینگ

💎 ویژه این ماه: تخفیف تا ۵۰٪ روی پکیج‌های بلندمدت!

برای شروع یکی از گزینه‌های زیر رو انتخاب کن:
"""
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_keyboard())

@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.from_user.id in ADMIN_IDS:
        admin_text = """
🔧 پنل مدیریت ربات

خوش اومدی مدیر عزیز!
از منوی زیر گزینه مورد نظرت رو انتخاب کن:
"""
        bot.send_message(message.chat.id, admin_text, reply_markup=admin_keyboard())
    else:
        bot.reply_to(message, "❌ شما دسترسی ادمین ندارید!")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    
    try:
        if call.data == "buy_service":
            show_services(call)
        
        elif call.data.startswith("service_"):
            service_id = int(call.data.split("_")[1])
            show_service_details(call, service_id)
        
        elif call.data.startswith("buy_"):
            service_id = int(call.data.split("_")[1])
            start_purchase(call, service_id)
        
        elif call.data.startswith("paid_"):
            order_id = call.data.split("_")[1]
            handle_payment_confirmation(call, order_id)
        
        elif call.data == "my_services":
            show_user_services(call)
        
        elif call.data == "support":
            show_support_info(call)
        
        elif call.data == "help":
            show_help(call)
        
        elif call.data == "back_main":
            show_main_menu(call)
        
        # ادمین handlers
        elif call.data.startswith("admin_") and user_id in ADMIN_IDS:
            handle_admin_callback(call)
            
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ خطا در پردازش درخواست!")
        print(f"Callback error: {e}")

def show_services(call):
    text = """
🛒 فروشگاه سرویس‌های VPN

💎 پکیج‌های ویژه ما:

🔥 تخفیف‌های ویژه برای پکیج‌های بلندمدت!
⚡ سرعت بالا و پایداری تضمینی
🌍 دسترسی به تمام سایت‌ها و اپلیکیشن‌ها

پکیج مورد نظرت رو انتخاب کن:
"""
    bot.edit_message_text(text, call.message.chat.id, 
                        call.message.message_id, reply_markup=services_keyboard())

def show_service_details(call, service_id):
    service = db.get_service(service_id)
    if not service:
        bot.answer_callback_query(call.id, "❌ سرویس یافت نشد!")
        return
    
    # محاسبه تخفیف
    discount_text = ""
    if service[3] >= 180:  # 6 ماه یا بیشتر
        discount_text = "\n🔥 تخفیف ۴۴٪ - پیشنهاد ویژه!"
    elif service[3] >= 90:  # 3 ماه یا بیشتر
        discount_text = "\n🔥 تخفیف ۳۳٪ - پرطرفدار!"
    
    text = f"""
📱 {service[1]}

💰 قیمت: {service[2]:,} تومان
⏱ مدت: {service[3]} روز  
📊 حجم: {service[4]} گیگابایت
📝 {service[5]}{discount_text}

───────────────
✨ مزایای این پکیج:

🚀 سرعت فوق‌العاده (تا ۸۰ مگ)
🛡️ امنیت کامل و رمزگذاری قوی
🌍 دسترسی به تمام سایت‌ها
📱 سازگار با همه دستگاه‌ها
🔄 پشتیبانی از همه پروتکل‌ها
⚡ اتصال فوری بدون تأخیر
🎯 IP اختصاصی و تمیز

💎 گارانتی ۱۰۰٪ بازگشت وجه در صورت عدم رضایت
"""
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton(
        f"💳 خرید {service[2]:,} تومان", 
        callback_data=f"buy_{service_id}"
    ))
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="buy_service"))
    
    bot.edit_message_text(text, call.message.chat.id, 
                        call.message.message_id, reply_markup=keyboard)

def start_purchase(call, service_id):
    service = db.get_service(service_id)
    if not service:
        bot.answer_callback_query(call.id, "❌ سرویس یافت نشد!")
        return
    
    user_id = call.from_user.id
    order_id = db.add_order(user_id, service_id, service[2])
    
    # ساخت لینک پرداخت
    payment_url = payment.create_payment_url(
        service[2], 
        f"خرید {service[1]}", 
        order_id
    )
    
    payment_text = f"""
💳 صورتحساب خرید

📱 سرویس: {service[1]}
💰 مبلغ: {service[2]:,} تومان
🆔 شماره سفارش: #{order_id}

───────────────
💳 روش‌های پرداخت:
"""
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    
    if payment_url:
        keyboard.add(telebot.types.InlineKeyboardButton(
            "💳 پرداخت آنلاین (زرین‌پال)", url=payment_url
        ))
    
    # اطلاعات کارت به کارت
    if CARD_NUMBER:
        payment_text += f"""

💳 کارت به کارت:
```
{CARD_NUMBER}
به نام: {CARD_HOLDER_NAME}
```

📱 شماره تماس جهت تأیید:
{SUPPORT_PHONE}
"""
        
    keyboard.add(telebot.types.InlineKeyboardButton(
        "✅ پرداخت کردم", callback_data=f"paid_{order_id}"
    ))
    keyboard.add(telebot.types.InlineKeyboardButton(
        "❌ انصراف", callback_data="back_main"
    ))
    
    payment_text += "\n\n⚠️ بعد از پرداخت، دکمه 'پرداخت کردم' را بزنید."
    
    bot.edit_message_text(payment_text, call.message.chat.id, 
                        call.message.message_id, reply_markup=keyboard, 
                        parse_mode='Markdown')

def handle_payment_confirmation(call, order_id):
    order = db.get_order(order_id)
    if not order:
        bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!")
        return
    
    text = f"""
✅ درخواست پرداخت شما ثبت شد!

🆔 شماره سفارش: #{order_id}
📱 سرویس: {order[8]}
💰 مبلغ: {order[3]:,} تومان

📋 وضعیت: در انتظار تأیید پرداخت

⏰ زمان بررسی: حداکثر ۱۰ دقیقه
📞 پشتیبانی: {SUPPORT_USERNAME}

✨ بعد از تأیید، سرویس شما فوراً فعال خواهد شد!
"""
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id)
    
    # اطلاع به ادمین‌ها
    admin_text = f"""
🔔 درخواست پرداخت جدید!

👤 کاربر: {call.from_user.first_name}
🆔 یوزرنیم: @{call.from_user.username or 'ندارد'}
📱 آیدی: {call.from_user.id}

🛒 سرویس: {order[8]}
💰 مبلغ: {order[3]:,} تومان
🆔 شماره سفارش: #{order_id}

برای فعال‌سازی: /activate {order_id}
"""
    
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, admin_text)
        except:
            pass

def show_user_services(call):
    # اینجا می‌تونید سرویس‌های فعال کاربر رو نمایش بدید
    text = """
💎 سرویس‌های شما

متأسفانه هنوز سرویسی فعال ندارید.
برای خرید سرویس جدید از منوی اصلی استفاده کنید.

📞 پشتیبانی: @YourSupportUsername
"""
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy_service"))
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    
    bot.edit_message_text(text, call.message.chat.id, 
                        call.message.message_id, reply_markup=keyboard)

def show_support_info(call):
    text = f"""
📞 راه‌های ارتباط با پشتیبانی

🆔 تلگرام: {SUPPORT_USERNAME}
📱 شماره تماس: {SUPPORT_PHONE}

⏰ ساعات پاسخگویی:
🌅 صبح: ۹:۰۰ تا ۱۲:۰۰
🌆 عصر: ۱۶:۰۰ تا ۲۳:۰۰

💬 برای پشتیبانی سریع‌تر، شماره سفارش خود را همراه پیام ارسال کنید.

✨ تیم پشتیبانی ما آماده کمک به شما هستند!
"""
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    
    bot.edit_message_text(text, call.message.chat.id, 
                        call.message.message_id, reply_markup=keyboard)

def show_help(call):
    text = """
ℹ️ راهنمای استفاده

📱 نحوه استفاده از سرویس:

1️⃣ یکی از پکیج‌ها را خریداری کنید
2️⃣ بعد از تأیید پرداخت، لینک کانفیگ دریافت کنید
3️⃣ اپلیکیشن مناسب را نصب کنید:
   • اندروید: v2rayNG یا Hiddify
   • آیفون: Fair VPN یا Streisand  
   • ویندوز: v2rayN یا Hiddify
   • مک: ClashX یا V2rayU

4️⃣ لینک کانفیگ را در اپلیکیشن وارد کنید
5️⃣ روی Connect کلیک کنید

🔗 لینک دانلود اپلیکیشن‌ها:
• اندروید: bit.ly/v2rayng-app
• آیفون: bit.ly/fair-vpn-app

❓ سوالات متداول در کانال: @YourChannelUsername

🎯 برای راهنمایی بیشتر با پشتیبانی تماس بگیرید.
"""
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    
    bot.edit_message_text(text, call.message.chat.id, 
                        call.message.message_id, reply_markup=keyboard)

def show_main_menu(call):
    text = """
🏠 منوی اصلی

خوش برگشتی! 🎉
یکی از گزینه‌های زیر رو انتخاب کن:
"""
    bot.edit_message_text(text, call.message.chat.id, 
                        call.message.message_id, reply_markup=main_keyboard())

def handle_admin_callback(call):
    if call.data == "admin_stats":
        stats = db.get_stats()
        stats_text = f"""
📊 آمار کلی ربات

👥 کل کاربران: {stats['total_users']:,}
📦 سفارشات امروز: {stats['today_orders']}
💰 درآمد امروز: {stats['today_income']:,} تومان
💎 کل درآمد: 
