#!/bin/bash

# رنگ‌ها برای خروجی
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 نصب و راه‌اندازی ربات فروش VPN${NC}"
echo "==============================================="

# تابع چک کردن موفقیت دستور
check_success() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $1 با موفقیت انجام شد${NC}"
    else
        echo -e "${RED}❌ خطا در $1${NC}"
        exit 1
    fi
}

# بررسی دسترسی root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ لطفاً با دسترسی root اجرا کنید (sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}📦 به‌روزرسانی سیستم...${NC}"
apt update && apt upgrade -y
check_success "به‌روزرسانی سیستم"

echo -e "${YELLOW}🐍 نصب Python و ابزارهای مربوطه...${NC}"
apt install python3 python3-pip python3-venv git screen nano curl -y
check_success "نصب Python"

# بررسی نسخه Python
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo -e "${GREEN}✅ Python نسخه $PYTHON_VERSION نصب شد${NC}"

echo -e "${YELLOW}📁 ایجاد دایرکتوری پروژه...${NC}"
PROJECT_DIR="/opt/vpn-bot"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR
check_success "ایجاد دایرکتوری"

echo -e "${YELLOW}🔧 ایجاد محیط مجازی Python...${NC}"
python3 -m venv venv
source venv/bin/activate
check_success "ایجاد محیط مجازی"

echo -e "${YELLOW}📚 نصب کتابخانه‌های مورد نیاز...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
check_success "نصب کتابخانه‌ها"

echo -e "${YELLOW}📝 ایجاد فایل‌های پروژه...${NC}"

# ایجاد فایل config.py
cat > config.py << 'EOF'
"""
تنظیمات ربات فروش VPN
لطفاً تمام مقادیر را با اطلاعات واقعی خود جایگزین کنید
"""

# اطلاعات ربات تلگرام
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# لیست آیدی ادمین‌ها
ADMIN_IDS = [123456789] # اینجا باید آیدی تلگرام خودتان را قرار دهید

# اطلاعات پنل HiddiFy  
HIDDIFY_API_URL = "https://your-panel.com" # آدرس پنل Hiddify شما
HIDDIFY_API_KEY = "your-api-key" # API Key پنل Hiddify شما

# زرین‌پال
ZARINPAL_MERCHANT_ID = "" # کد مرچنت زرین پال شما (اختیاری)

# اطلاعات کارت
CARD_NUMBER = "6037-9977-****-****" # شماره کارت بانکی برای پرداخت دستی
CARD_HOLDER_NAME = "نام صاحب کارت" # نام صاحب کارت بانکی

# پشتیبانی
SUPPORT_USERNAME = "@your_support" # یوزرنیم تلگرام پشتیبانی
SUPPORT_PHONE = "09123456789" # شماره تماس پشتیبانی

# وب‌هوک (اختیاری، برای تأیید خودکار پرداخت زرین‌پال)
BOT_WEBHOOK_URL = "" 
EOF

echo -e "${GREEN}✅ فایل config.py ایجاد شد${NC}"

# ایجاد فایل bot.py
# توجه: محتوای کامل bot.py اینجا قرار می‌گیرد
cat > bot.py << 'EOF'
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
            order = self.get_order(order_id)
            if order:
                duration_days = order[10] # order[10] is duration_days
                expire_date = datetime.now() + timedelta(days=duration_days)
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
                # Hiddify API might return 'subscription_url' or 'config_url'
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
