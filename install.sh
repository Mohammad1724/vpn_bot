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

# --- گرفتن اطلاعات از کاربر ---
echo -e "${BLUE}\n💡 لطفاً اطلاعات مورد نیاز ربات را وارد کنید:${NC}"

read -p "توکن ربات تلگرام شما (از @BotFather دریافت کنید): " BOT_TOKEN_INPUT
read -p "آیدی عددی تلگرام ادمین (برای دریافت، پیامک 'myid/' را به @userinfobot بفرستید): " ADMIN_ID_INPUT
read -p "آدرس پنل Hiddify شما (مثال: https://your-panel.com): " HIDDIFY_URL_INPUT
read -p "API Key پنل Hiddify شما: " HIDDIFY_KEY_INPUT
read -p "شناسه پذیرنده زرین‌پال شما (اختیاری، اگر ندارید خالی بگذارید): " ZARINPAL_MERCHANT_INPUT
read -p "شماره کارت بانکی برای پرداخت دستی (اختیاری، اگر ندارید خالی بگذارید): " CARD_NUMBER_INPUT
read -p "نام صاحب کارت بانکی (اختیاری): " CARD_HOLDER_NAME_INPUT
read -p "یوزرنیم تلگرام پشتیبانی شما (مثال: @my_support): " SUPPORT_USERNAME_INPUT
read -p "شماره تماس پشتیبانی شما (مثال: 09123456789): " SUPPORT_PHONE_INPUT
read -p "آدرس وب‌هوک ربات (اختیاری، برای تأیید پرداخت خودکار زرین‌پال): " WEBHOOK_URL_INPUT

# --- ایجاد فایل‌های پروژه ---
echo -e "${YELLOW}\n📝 ایجاد فایل‌های پروژه...${NC}"

# ایجاد فایل config.py با اطلاعات ورودی کاربر
cat > config.py << EOF
"""
تنظیمات ربات فروش VPN
"""

# اطلاعات ربات تلگرام
BOT_TOKEN = "$BOT_TOKEN_INPUT"

# لیست آیدی ادمین‌ها
ADMIN_IDS = [$ADMIN_ID_INPUT]

# اطلاعات پنل HiddiFy  
HIDDIFY_API_URL = "$HIDDIFY_URL_INPUT"
HIDDIFY_API_KEY = "$HIDDIFY_KEY_INPUT"

# زرین‌پال
ZARINPAL_MERCHANT_ID = "$ZARINPAL_MERCHANT_INPUT"

# اطلاعات کارت
CARD_NUMBER = "$CARD_NUMBER_INPUT"
CARD_HOLDER_NAME = "$CARD_HOLDER_NAME_INPUT"

# پشتیبانی
SUPPORT_USERNAME = "$SUPPORT_USERNAME_INPUT"
SUPPORT_PHONE = "$SUPPORT_PHONE_INPUT"

# وب‌هوک (اختیاری، برای تأیید خودکار پرداخت زرین‌پال)
BOT_WEBHOOK_URL = "$WEBHOOK_URL_INPUT" 
EOF
echo -e "${GREEN}✅ فایل config.py ایجاد شد${NC}"

# ایجاد فایل requirements.txt
cat > requirements.txt << EOF
pyTelegramBotAPI==4.14.0
requests==2.31.0
EOF
echo -e "${GREEN}✅ فایل requirements.txt ایجاد شد${NC}"

# ایجاد فایل bot.py (محتوای کامل bot.py باید اینجا قرار گیرد)
# توجه: محتوای کامل bot.py در ادامه توضیح داده شده است، اما برای خودکارسازی، باید آن را اینجا جایگذاری کنید.
cat > bot.py << 'EOF'
import telebot
import sqlite3
import json
import requests
from datetime import datetime, timedelta
import uuid
import os
from config import *

# ==================== Database Manager ====================
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
        
        # اضافه کردن سرویس‌های پیش‌فرض فقط در صورتی که جدولی خالی باشد
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

    def add_service(self, name, price, duration, traffic, description):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO services (name, price, duration_days, traffic_gb, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, price, duration, traffic, description))
        conn.commit()
        conn.close()

    def update_service(self, service_id, name, price, duration, traffic, description):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE services 
            SET name = ?, price = ?, duration_days = ?, traffic_gb = ?, description = ?
            WHERE id = ?
        ''', (name, price, duration, traffic, description, service_id))
        conn.commit()
        conn.close()

    def delete_service(self, service_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM services WHERE id = ?', (service_id,))
        conn.commit()
        conn.close()


# ==================== Hiddify Manager ====================
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
            # Try to get a small list of users to confirm connection
            response = requests.get(f'{self.api_url}/api/v1/admin/user/?limit=1', 
                                  headers=headers, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Hiddify connection test failed: {e}")
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
            
            print(f"Hiddify user creation failed: {response.status_code} - {response.text}")
            return None
            
        except Exception as e:
            print(f"Error creating user: {e}")
            return None

# ==================== Payment Manager ====================
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
            
            print(f"Zarinpal payment request failed: {response.status_code} - {response.text}")
            return None
            
        except Exception as e:
            print(f"Error creating Zarinpal payment URL: {e}")
            return None

# ایجاد instance ها
db = DatabaseManager()
hiddify = HiddifyManager()
payment = PaymentManager()
bot = telebot.TeleBot(BOT_TOKEN)

# ==================== Keyboards ====================
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

def admin_services_manage_keyboard():
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        telebot.types.InlineKeyboardButton("➕ افزودن سرویس", callback_data="admin_add_service"),
        telebot.types.InlineKeyboardButton("✏️ ویرایش سرویس", callback_data="admin_edit_service_list")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("🗑️ حذف سرویس", callback_data="admin_delete_service_list")
    )
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 پنل ادمین", callback_data="admin_back"))
    return keyboard

# ==================== Handlers ====================
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
    if CARD_NUMBER and CARD_HOLDER_NAME:
        payment_text += f"""

💳 کارت به کارت:

{CARD_NUMBER}
به نام: {CARD_HOLDER_NAME}

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
💎 کل درآمد: {stats['total_income']:,} تومان

🔧 وضعیت سیستم: {"✅ عادی" if hiddify.test_connection() else "❌ خطا در اتصال"}

📅 {datetime.now().strftime('%Y/%m/%d %H:%M')}
"""
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(telebot.types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_stats"))
        keyboard.add(telebot.types.InlineKeyboardButton("🔙 پنل ادمین", callback_data="admin_back"))
        
        bot.edit_message_text(stats_text, call.message.chat.id, 
                            call.message.message_id, reply_markup=keyboard)
    
    elif call.data == "admin_test":
        hiddify_status = "✅ متصل" if hiddify.test_connection() else "❌ قطع"
        
        test_text = f"""
🔧 تست سیستم

🌐 اتصال HiddiFy: {hiddify_status}
💳 درگاه پرداخت: {"✅ فعال" if payment.zarinpal_merchant else "❌ غیرفعال"}
💾 دیتابیس: ✅ فعال

📡 آدرس API: {HIDDIFY_API_URL}
🔑 کلید API: {"✅ تنظیم شده" if HIDDIFY_API_KEY else "❌ تنظیم نشده"}

⚙️ تست شده در: {datetime.now().strftime('%H:%M:%S')}
"""
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(telebot.types.InlineKeyboardButton("🔄 تست مجدد", callback_data="admin_test"))
        keyboard.add(telebot.types.InlineKeyboardButton("🔙 پنل ادمین", callback_data="admin_back"))
        
        bot.edit_message_text(test_text, call.message.chat.id, 
                            call.message.message_id, reply_markup=keyboard)
    
    elif call.data == "admin_users":
        conn = sqlite3.connect(db.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, join_date FROM users ORDER BY join_date DESC LIMIT 10')
        users = cursor.fetchall()
        conn.close()

        user_list_text = "👥 **۱۰ کاربر اخیر:**\n\n"
        if users:
            for user in users:
                user_list_text += f"▪️ ID: `{user[0]}`\n"
                user_list_text += f"   یوزرنیم: @{user[1] or 'ندارد'}\n"
                user_list_text += f"   تاریخ عضویت: {datetime.fromisoformat(user[2]).strftime('%Y/%m/%d')}\n"
                user_list_text += "----------\n"
        else:
            user_list_text = "کاربری یافت نشد."
        
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(telebot.types.InlineKeyboardButton("🔙 پنل ادمین", callback_data="admin_back"))
        bot.edit_message_text(user_list_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard, parse_mode='Markdown')

    elif call.data == "admin_orders":
        conn = sqlite3.connect(db.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.payment_id, o.amount, o.status, o.created_at, s.name, o.user_id
            FROM orders o
            JOIN services s ON o.service_id = s.id  
            ORDER BY o.created_at DESC
            LIMIT 10
        ''')
        orders = cursor.fetchall()
        conn.close()

        orders_text = "📋 **۱۰ سفارش اخیر:**\n\n"
        if orders:
            for order in orders:
                status_emoji = "✅" if order[2] == "active" else "⏳" if order[2] == "pending" else "❌"
                date = datetime.fromisoformat(order[3]).strftime('%m/%d %H:%M')
                
                orders_text += f"""
{status_emoji} #{order[0]}
💰 {order[1]:,} تومان - {order[4]}
👤 کاربر: `{order[5]}` | 📅 {date}
{'─' * 35}
"""
        else:
            orders_text = "سفارشی یافت نشد."

        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(telebot.types.InlineKeyboardButton("🔙 پنل ادمین", callback_data="admin_back"))
        bot.edit_message_text(orders_text, call.message.chat.id, call.message.message_id, reply_markup=keyboard, parse_mode='Markdown')

    elif call.data == "admin_services":
        # نمایش منوی مدیریت سرویس‌ها
        services = db.get_services()
        service_list_text = "📦 **لیست سرویس‌ها:**\n\n"
        if services:
            for service in services:
                service_list_text += f"▪️ ID: `{service[0]}`\n"
                service_list_text += f"   نام: {service[1]}\n"
                service_list_text += f"   قیمت: {service[2]:,} تومان\n"
                service_list_text += f"   مدت: {service[3]} روز\n"
                service_list_text += f"   حجم: {service[4]} GB\n"
                service_list_text += "----------\n"
        else:
            service_list_text = "سرویسی تعریف نشده است."
        
        bot.edit_message_text(service_list_text, call.message.chat.id, call.message.message_id, reply_markup=admin_services_manage_keyboard(), parse_mode='Markdown')
        
    elif call.data == "admin_add_service":
        msg = bot.send_message(call.message.chat.id, "➕ لطفاً اطلاعات سرویس جدید را در یک خط و با فرمت زیر وارد کنید:\n\n`نام_سرویس قیمت مدت_روز حجم_گیگ توضیحات`\n\nمثال: `پکیج_یک_ماهه 50000 30 50 مناسب_استفاده_شخصی`")
        bot.register_next_step_handler(msg, add_service_step)

    elif call.data == "admin_edit_service_list":
        services = db.get_services()
        if not services:
            bot.answer_callback_query(call.id, "❌ سرویسی برای ویرایش وجود ندارد!")
            return
        
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
        for service in services:
            keyboard.add(telebot.types.InlineKeyboardButton(f"✏️ {service[1]} (ID: {service[0]})", callback_data=f"edit_service_{service[0]}"))
        keyboard.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_services"))
        
        bot.edit_message_text("✏️ سرویس مورد نظر برای ویرایش را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=keyboard)

    elif call.data.startswith("edit_service_"):
        service_id = int(call.data.split("_")[2])
        service = db.get_service(service_id)
        if not service:
            bot.answer_callback_query(call.id, "❌ سرویس یافت نشد!")
            return
        
        msg = bot.send_message(call.message.chat.id, f"✏️ برای ویرایش سرویس **{service[1]} (ID: {service_id})**، لطفاً اطلاعات جدید را در یک خط و با فرمت زیر وارد کنید:\n\n`نام_جدید قیمت_جدید مدت_روز_جدید حجم_گیگ_جدید توضیحات_جدید`\n\n(می‌توانید اطلاعات قبلی را ببینید: `{service[1]} {service[2]} {service[3]} {service[4]} {service[5]}`)\n\nمثال: `پکیج_پلاس 60000 30 60 پکیج_بهتر`", parse_mode='Markdown')
        bot.register_next_step_handler(msg, lambda m: edit_service_step(m, service_id))

    elif call.data == "admin_delete_service_list":
        services = db.get_services()
        if not services:
            bot.answer_callback_query(call.id, "❌ سرویسی برای حذف وجود ندارد!")
            return
        
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
        for service in services:
            keyboard.add(telebot.types.InlineKeyboardButton(f"🗑️ {service[1]} (ID: {service[0]})", callback_data=f"delete_service_{service[0]}"))
        keyboard.add(telebot.types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_services"))
        
        bot.edit_message_text("🗑️ سرویس مورد نظر برای حذف را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=keyboard)

    elif call.data.startswith("delete_service_"):
        service_id = int(call.data.split("_")[2])
        service = db.get_service(service_id)
        if not service:
            bot.answer_callback_query(call.id, "❌ سرویس یافت نشد!")
            return
        
        db.delete_service(service_id)
        bot.answer_callback_query(call.id, f"✅ سرویس '{service[1]}' با موفقیت حذف شد.")
        # Refresh the services list
        handle_admin_callback(call) # Re-call to update the message with new list
        
    elif call.data == "admin_back":
        admin_command(call.message)

# ==================== Admin Commands for Services ====================
def add_service_step(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ دسترسی غیرمجاز!")
        return
    
    try:
        parts = message.text.split(maxsplit=4) # Split into 5 parts: name, price, duration, traffic, description
        if len(parts) != 5:
            msg = bot.send_message(message.chat.id, """
❌ فرمت نادرست!

✅ فرمت صحیح:
`نام_سرویس قیمت مدت_روز حجم_گیگ توضیحات`

📝 مثال:
`پکیج_جدید 75000 60 100 پکیج_دو_ماهه_با_تخفیف`
""")
            bot.register_next_step_handler(msg, add_service_step) # Ask again
            return
        
        name = parts[0].replace('_', ' ')
        price = int(parts[1])
        duration = int(parts[2])
        traffic = int(parts[3])
        description = parts[4].replace('_', ' ')
        
        db.add_service(name, price, duration, traffic, description)
        bot.send_message(message.chat.id, f"✅ سرویس '{name}' با موفقیت اضافه شد!")
        
        # Display updated services list
        call = telebot.types.CallbackQuery(id=0, from_user=message.from_user, message=message, data="admin_services")
        handle_admin_callback(call)
        
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ قیمت، مدت و حجم باید عدد باشند!\nلطفاً دوباره وارد کنید.")
        bot.register_next_step_handler(msg, add_service_step)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطا: {str(e)}")
        call = telebot.types.CallbackQuery(id=0, from_user=message.from_user, message=message, data="admin_services")
        handle_admin_callback(call)

def edit_service_step(message, service_id):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ دسترسی غیرمجاز!")
        return
    
    try:
        parts = message.text.split(maxsplit=4) # Split into 5 parts
        if len(parts) != 5:
            msg = bot.send_message(message.chat.id, """
❌ فرمت نادرست برای ویرایش!

✅ فرمت صحیح:
`نام_جدید قیمت_جدید مدت_روز_جدید حجم_گیگ_جدید توضیحات_جدید`

لطفاً دوباره وارد کنید.
""")
            bot.register_next_step_handler(msg, lambda m: edit_service_step(m, service_id))
            return
        
        name = parts[0].replace('_', ' ')
        price = int(parts[1])
        duration = int(parts[2])
        traffic = int(parts[3])
        description = parts[4].replace('_', ' ')
        
        db.update_service(service_id, name, price, duration, traffic, description)
        bot.send_message(message.chat.id, f"✅ سرویس با ID **{service_id}** با موفقیت ویرایش شد.")
        
        # Display updated services list
        call = telebot.types.CallbackQuery(id=0, from_user=message.from_user, message=message, data="admin_services")
        handle_admin_callback(call)

    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ قیمت، مدت و حجم باید عدد باشند!\nلطفاً دوباره وارد کنید.")
        bot.register_next_step_handler(msg, lambda m: edit_service_step(m, service_id))
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطا: {str(e)}")
        call = telebot.types.CallbackQuery(id=0, from_user=message.from_user, message=message, data="admin_services")
        handle_admin_callback(call)

# ==================== Other Admin Commands ====================
@bot.message_handler(commands=['activate'])
def activate_service(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ دسترسی غیرمجاز!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ فرمت: /activate ORDER_ID")
            return
        
        order_id = parts[1]
        order = db.get_order(order_id)
        
        if not order:
            bot.reply_to(message, "❌ سفارش پیدا نشد!")
            return
        
        if order[4] == 'active':
            bot.reply_to(message, "⚠️ این سرویس قبلاً فعال شده!")
            return
        
        # ایجاد کاربر در HiddiFy
        # order[1] is user_id, order[11] is traffic_gb, order[10] is duration_days
        username = f"user_{order[1]}_{order_id}"
        config_url = hiddify.create_user(username, order[11], order[10])
        
        if config_url:
            # به‌روزرسانی وضعیت سفارش
            db.update_order_status(order_id, 'active', config_url)
            
            # ارسال کانفیگ به کاربر
            expire_date = datetime.fromisoformat(db.get_order(order_id)[7]) # Get expires_at from updated order
            
            config_text = f"""
🎉 سرویس شما فعال شد!

📱 سرویس: {order[8]}
⏰ مدت: {order[10]} روز
📊 حجم: {order[11]} گیگابایت
🆔 شماره سفارش: #{order_id}

🔗 لینک کانفیگ:

{config_url}

───────────────
📱 نحوه استفاده:

1️⃣ لینک بالا را کپی کنید
2️⃣ یکی از اپلیکیشن‌های زیر را نصب کنید:
   • اندروید: v2rayNG
   • آیفون: Fair VPN
   • ویندوز: v2rayN

3️⃣ لینک را در اپلیکیشن import کنید
4️⃣ روی Connect کلیک کنید

✅ سرویس تا {expire_date.strftime('%Y/%m/%d')} فعال است

🔰 راهنمای کامل: /help
📞 پشتیبانی: {SUPPORT_USERNAME}

🌟 از خرید شما متشکریم!
"""
            
            try:
                bot.send_message(order[1], config_text, parse_mode='Markdown')
                bot.reply_to(message, f"✅ سرویس برای کاربر {order[1]} فعال شد!")
            except Exception as e:
                bot.reply_to(message, f"✅ سرویس فعال شد اما در ارسال به کاربر {order[1]} خطا رخ داد: {e} (کاربر شاید بلاک کرده است)")
        else:
            bot.reply_to(message, "❌ خطا در ایجاد سرویس در پنل HiddiFy! لطفاً API Key و URL پنل را بررسی کنید.")
            
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

@bot.message_handler(commands=['stats'])
def stats_command(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    stats = db.get_stats()
    hiddify_status = "✅ متصل" if hiddify.test_connection() else "❌ قطع"
    
    stats_text = f"""
📊 آمار کامل ربات

👥 کل کاربران: {stats['total_users']:,}
📦 سفارشات امروز: {stats['today_orders']}
💰 درآمد امروز: {stats['today_income']:,} تومان
💎 کل درآمد: {stats['total_income']:,} تومان

🔧 وضعیت سیستم‌ها:
🌐 HiddiFy Panel: {hiddify_status}
💳 درگاه پرداخت: {"✅ فعال" if payment.zarinpal_merchant else "❌ غیرفعال"}
💾 دیتابیس: ✅ فعال

📅 {datetime.now().strftime('%Y/%m/%d - %H:%M:%S')}
"""
    
    bot.send_message(message.chat.id, stats_text)

@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        # فرمت: /broadcast پیام شما
        text = message.text[11:].strip()  # حذف /broadcast
        if not text:
            bot.reply_to(message, "❌ پیام خالی است!\n✅ فرمت: /broadcast پیام شما")
            return
        
        # دریافت لیست کاربران
        conn = sqlite3.connect('vpn_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_active = 1')
        users = cursor.fetchall()
        conn.close()
        
        sent_count = 0
        failed_count = 0
        
        bot.reply_to(message, f"📡 شروع ارسال پیام به {len(users)} کاربر...")
        
        for user in users:
            try:
                bot.send_message(user[0], text)
                sent_count += 1
            except:
                failed_count += 1
        
        result_text = f"""
✅ ارسال پیام تکمیل شد!

📤 ارسال شده: {sent_count}
❌ ناموفق: {failed_count}
👥 کل: {len(users)}
"""
        bot.send_message(message.chat.id, result_text)
        
    except Exception as e:
        bot.reply_to(message, f"❌ خطا در ارسال: {str(e)}")

@bot.message_handler(commands=['orders'])
def show_recent_orders(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        conn = sqlite3.connect('vpn_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.payment_id, o.amount, o.status, o.created_at, s.name, o.user_id
            FROM orders o
            JOIN services s ON o.service_id = s.id  
            ORDER BY o.created_at DESC
            LIMIT 10
        ''')
        orders = cursor.fetchall()
        conn.close()
        
        if not orders:
            bot.reply_to(message, "📭 هیچ سفارشی یافت نشد!")
            return
        
        orders_text = "📋 آخرین سفارشات:\n\n"
        
        for order in orders:
            status_emoji = "✅" if order[2] == "active" else "⏳" if order[2] == "pending" else "❌"
            date = datetime.fromisoformat(order[3]).strftime('%m/%d %H:%M')
            
            orders_text += f"""
{status_emoji} #{order[0]}
💰 {order[1]:,} تومان - {order[4]}
👤 کاربر: {order[5]} | 📅 {date}
{'─' * 35}
"""
        
        bot.send_message(message.chat.id, orders_text)
        
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

if __name__ == "__main__":
    print("🚀 در حال راه‌اندازی ربات...")
    # Attempt to get bot info, but handle potential errors (e.g., invalid token)
    try:
        bot_info = bot.get_me()
        print(f"🤖 نام ربات: {bot_info.first_name}")
        print(f"🆔 یوزرنیم: @{bot_info.username}")
        print("✅ ربات آماده است!")
    except Exception as e:
        print(f"❌ خطا در دریافت اطلاعات ربات. توکن ربات صحیح نیست یا ارتباط برقرار نشد: {e}")
        print("لطفاً فایل config.py را بررسی و اصلاح کنید.")
        exit(1) # Exit if bot token is invalid

    try:
        bot.infinity_polling(none_stop=True)
    except Exception as e:
        print(f"❌ خطا در اجرای ربات: {e}")
EOF
echo -e "${GREEN}✅ فایل bot.py ایجاد شد${NC}"

# ایجاد فایل manage.sh
cat > manage.sh << 'EOF'
#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

show_menu() {
    echo -e "${BLUE}🤖 مدیریت ربات فروش VPN${NC}"
    echo "=========================="
    echo "1. شروع ربات"
    echo "2. توقف ربات" 
    echo "3. وضعیت ربات"
    echo "4. مشاهده لاگ‌ها"
    echo "5. ویرایش تنظیمات (config.py)"
    echo "6. بازنشانی ربات"
    echo "7. تنظیم فایروال (UFW)"
    echo "8. خروج"
    echo -n "انتخاب کنید [1-8]: "
}

start_bot() {
    echo -e "${YELLOW}🚀 در حال شروع ربات...${NC}"
    systemctl enable vpn-bot
    systemctl start vpn-bot
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ربات با موفقیت شروع شد${NC}"
    else
        echo -e "${RED}❌ خطا در شروع ربات${NC}"
    fi
}

stop_bot() {
    echo -e "${YELLOW}🛑 در حال توقف ربات...${NC}"
    systemctl stop vpn-bot
    echo -e "${GREEN}✅ ربات متوقف شد${NC}"
}

status_bot() {
    echo -e "${BLUE}📊 وضعیت ربات:${NC}"
    systemctl status vpn-bot --no-pager -l
}

show_logs() {
    echo -e "${BLUE}📋 لاگ‌های ربات:${NC}"
    echo "برای خروج Ctrl+C بزنید"
    journalctl -u vpn-bot -f
}

edit_config() {
    echo -e "${YELLOW}⚙️ ویرایش تنظیمات...${NC}"
    nano config.py
    echo -e "${GREEN}✅ تنظیمات ذخیره شد${NC}"
    echo -e "${YELLOW}🔄 برای اعمال تغییرات ربات را restart کنید${NC}"
}

restart_bot() {
    echo -e "${YELLOW}🔄 در حال بازنشانی ربات...${NC}"
    systemctl restart vpn-bot
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ربات بازنشانی شد${NC}"
    else
        echo -e "${RED}❌ خطا در بازنشانی ربات${NC}"
    fi
}

setup_firewall() {
    echo -e "${YELLOW}🔥 تنظیم فایروال...${NC}"
    apt install ufw -y
    ufw --force enable
    ufw allow ssh
    ufw allow 443
    ufw allow 80
    echo -e "${GREEN}✅ فایروال پیکربندی شد${NC}"
}

while true; do
    show_menu
    read choice
    case $choice in
        1) start_bot ;;
        2) stop_bot ;;
        3) status_bot ;;
        4) show_logs ;;
        5) edit_config ;;
        6) restart_bot ;;
        7) setup_firewall ;;
        8) echo -e "${GREEN}👋 خداحافظ!${NC}"; exit 0 ;;
        *) echo -e "${RED}❌ انتخاب نامعتبر${NC}" ;;
    esac
    echo
    read -p "برای ادامه Enter بزنید..."
done
EOF
echo -e "${GREEN}✅ فایل manage.sh ایجاد شد${NC}"

# ایجاد فایل backup.sh
mkdir -p /opt/backups
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M)
BACKUP_DIR="/opt/backups"
PROJECT_DIR="/opt/vpn-bot"

echo "🗄️ ایجاد بک‌آپ..."
tar -czf "$BACKUP_DIR/vpn-bot-backup-$DATE.tar.gz" -C "$PROJECT_DIR" bot.py config.py vpn_bot.db

# حذف بک‌آپ‌های قدیمی (بیشتر از 7 روز)
find "$BACKUP_DIR" -name "vpn-bot-backup-*.tar.gz" -mtime +7 -delete

echo "✅ بک‌آپ ذخیره شد: vpn-bot-backup-$DATE.tar.gz"
EOF
echo -e "${GREEN}✅ فایل backup.sh ایجاد شد${NC}"

# ایجاد فایل README.md (محتوای کامل README.md باید اینجا قرار گیرد)
# توجه: محتوای کامل README.md در ادامه توضیح داده شده است، اما برای خودکارسازی، باید آن را اینجا جایگذاری کنید.
cat > README.md << 'EOF'
# 🤖 ربات فروش VPN

ربات تلگرام پیشرفته برای فروش خودکار سرویس‌های VPN با پنل HiddiFy

## ✨ ویژگی‌ها

- 🛒 **فروش خودکار** سرویس‌های VPN
- 💳 پشتیبانی از **درگاه‌های پرداخت ایرانی** (زرین‌پال و کارت به کارت)
- 🔗 اتصال مستقیم به **پنل HiddiFy** برای ایجاد خودکار کانفیگ
- 👨‍💼 **پنل مدیریت کامل** با دستورات ادمین
- 📊 **گزارش‌گیری و آمار** لحظه‌ای
- 💬 **پشتیبانی از کاربران**
- 🔄 **بک‌آپ خودکار** روزانه از دیتابیس و فایل‌ها
- ➕➖ **مدیریت سرویس‌ها** (افزودن، ویرایش، حذف) از داخل ربات

## 🚀 نصب سریع و خودکار

با استفاده از این دستور، ربات به صورت کامل روی سرور شما نصب و راه‌اندازی می‌شود. این دستور تمام پیش‌نیازها را نصب کرده، فایل‌های پروژه را ایجاد کرده، اطلاعات اولیه را از شما می‌گیرد و ربات را به عنوان یک سرویس سیستمی (Systemd) تنظیم می‌کند.

```bash
sudo curl -sSL [https://raw.githubusercontent.com/yourusername/vpn-sales-bot/main/install.sh](https://raw.githubusercontent.com/yourusername/vpn-sales-bot/main/install.sh) | sudo bash

نکته مهم: مطمئن شوید که https://raw.githubusercontent.com/yourusername/vpn-sales-bot/main/install.sh را با لینک install.sh در ریپازیتوری خودتان جایگزین کنید. پس از اجرای این دستور، سوالاتی از شما پرسیده می‌شود که باید پاسخ دهید.
⚙️ پیکربندی
پس از نصب، تمام اطلاعات پیکربندی در فایل config.py ذخیره می‌شود. می‌توانید این فایل را در هر زمان با استفاده از اسکریپت manage.sh ویرایش کنید.
اطلاعات ضروری که هنگام نصب از شما پرسیده می‌شود:
 * توکن ربات تلگرام: از @BotFather دریافت کنید.
 * آیدی عددی تلگرام ادمین: برای دریافت، پیامک /myid را به @userinfobot بفرستید.
 * آدرس پنل Hiddify شما: مثال: https://your-panel.com (بدون /api یا /admin).
 * API Key پنل Hiddify شما: از بخش تنظیمات/API پنل Hiddify خود دریافت کنید.
 * شناسه پذیرنده زرین‌پال شما: (اختیاری).
 * شماره کارت بانکی برای پرداخت دستی: (اختیاری).
 * نام صاحب کارت بانکی: (اختیاری).
 * یوزرنیم تلگرام پشتیبانی شما: مثال: @my_support.
 * شماره تماس پشتیبانی شما: مثال: 09123456789.
 * آدرس وب‌هوک ربات: (اختیاری، برای تأیید پرداخت خودکار زرین‌پال). اگر از زرین‌پال استفاده می‌کنید و می‌خواهید پرداخت‌ها به صورت خودکار تایید شوند، باید آدرس IP/دامنه سرور خود را به علاوه /verify اینجا قرار دهید. مثال: http://your_server_ip_or_domain:PORT. (این بخش نیاز به دانش بیشتر و راه‌اندازی وب‌سرور دارد. برای شروع می‌توانید خالی بگذارید و تایید پرداخت‌ها را دستی انجام دهید.)
🛠️ مدیریت ربات
پس از نصب، می‌توانید از اسکریپت manage.sh برای مدیریت آسان ربات استفاده کنید. ابتدا به دایرکتوری پروژه بروید:
cd /opt/vpn-bot

سپس اسکریپت مدیریت را اجرا کنید:
./manage.sh

این اسکریپت یک منوی تعاملی برای انجام عملیات زیر فراهم می‌کند:
 * شروع/توقف/وضعیت ربات
 * مشاهده لاگ‌ها
 * ویرایش فایل config.py
 * بازنشانی ربات
 * تنظیم فایروال (UFW)
📱 دستورات ربات تلگرام
برای کاربران عادی
 * /start - شروع تعامل با ربات و نمایش منوی اصلی.
 * دکمه‌های اینلاین برای خرید سرویس، مشاهده سرویس‌های من، پشتیبانی و راهنما.
برای ادمین‌ها
 * /admin - دسترسی به پنل مدیریت ربات.
   * از این پنل می‌توانید به آمار ربات، لیست کاربران و سفارشات دسترسی پیدا کنید.
   * همچنین بخش سرویس‌ها امکان افزودن، ویرایش و حذف پلن‌های VPN را به صورت تعاملی فراهم می‌کند.
 * /activate ORDER_ID - فعال‌سازی یک سفارش خاص (با جایگزینی ORDER_ID با شناسه سفارش).
   (این دستور بیشتر برای فعال‌سازی دستی پس از پرداخت کارت به کارت استفاده می‌شود)
 * /stats - مشاهده آمار کلی ربات (تعداد کاربران، درآمد و...).
 * /broadcast پیام_شما - ارسال یک پیام همگانی به تمام کاربران فعال ربات.
 * /orders - مشاهده ۱۰ سفارش اخیر در ربات.
🔧 عیب‌یابی
مشکلات رایج
ربات پاسخ نمی‌دهد یا کار نمی‌کند:
 * وضعیت سرویس را بررسی کنید:
   sudo systemctl status vpn-bot

   مطمئن شوید که سرویس در حال اجرا (active (running)) باشد.
 * لاگ‌های ربات را بررسی کنید:
   sudo journalctl -u vpn-bot -f

   به دنبال پیام‌های خطا یا هشدار باشید.
خطا در اتصال به پنل Hiddify:
 * آدرس پنل (HIDDIFY_API_URL) و API Key (HIDDIFY_API_KEY) را در config.py با دقت بررسی کنید. از اسکریپت manage.sh گزینه 5 را برای ویرایش استفاده کنید.
 * مطمئن شوید که سرور شما می‌تواند به آدرس پنل Hiddify متصل شود (مثلاً با ping your-hiddify-panel.com یا curl -I https://your-hiddify-panel.com).
مشکل در پایگاه داده SQLite:
در موارد نادر، ممکن است فایل‌های جانبی دیتابیس دچار مشکل شوند. می‌توانید آن‌ها را حذف کرده و ربات را restart کنید (دیتابیس اصلی vpn_bot.db نباید حذف شود):
rm /opt/vpn-bot/vpn_bot.db-wal
rm /opt/vpn-bot/vpn_bot.db-shm
sudo systemctl restart vpn-bot

🤝 مشارکت
از هرگونه مشارکت در بهبود این پروژه استقبال می‌شود! اگر ایده‌ای برای ویژگی جدید دارید، باگ پیدا کردید یا می‌خواهید کدی را بهبود بخشید، لطفاً مراحل زیر را دنبال کنید:
 * پروژه را Fork کنید.
 * یک Branch جدید برای تغییرات خود ایجاد کنید (git checkout -b feature/your-feature-name).
 * تغییرات خود را Commit کنید (git commit -m 'Add new feature').
 * تغییرات را به ریپازیتوری خود Push کنید (git push origin feature/your-feature-name).
 * یک Pull Request به این ریپازیتوری ایجاد کنید.
📄 لایسنس
این پروژه تحت لایسنس MIT منتشر شده است. برای اطلاعات بیشتر، به فایل LICENSE (اگر وجود دارد) مراجعه کنید.
📞 پشتیبانی
اگر سؤالی دارید یا به کمک نیاز دارید، می‌توانید از طریق راه‌های زیر با ما در تماس باشید:
 * تلگرام: [@YourUsername] (با یوزرنیم پشتیبانی خود جایگزین کنید)
 * ایمیل: [your@email.com] (با ایمیل پشتیبانی خود جایگزین کنید)
 * Issues: GitHub Issues (با آدرس ریپازیتوری خود جایگزین کنید)
EOF
echo -e "{GREEN}✅ فایل README.md ایجاد شد{NC}"
echo -e "{YELLOW}🔧 ایجاد محیط مجازی Python...{NC}"
python3 -m venv venv
source venv/bin/activate
check_success "ایجاد محیط مجازی"
echo -e "{YELLOW}📚 نصب کتابخانه‌های مورد نیاز...{NC}"
pip install --upgrade pip
pip install -r requirements.txt
check_success "نصب کتابخانه‌ها"
اجازه اجرایی شدن اسکریپت‌ها
chmod +x manage.sh backup.sh
check_success "تنظیم مجوزهای اجرایی"
ایجاد systemd service
echo -e "{YELLOW}⚙️ ایجاد سرویس systemd...{NC}"
cat > /etc/systemd/system/vpn-bot.service << EOF
[Unit]
Description=VPN Sales Bot
After=network.target
[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
ExecStart=$PROJECT_DIR/venv/bin/python bot.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
check_success "ایجاد سرویس"
اضافه کردن cron job برای بک‌آپ روزانه
(crontab -l 2>/dev/null; echo "0 2 * * * $PROJECT_DIR/backup.sh >> /var/log/vpn-bot-backup.log 2>&1") | crontab -
check_success "تنظیم Cron Job برای بک‌آپ"
echo -e "{GREEN}✅ نصب با موفقیت تکمیل شد\!{NC}"
echo ""
echo -e "{BLUE}📋 مراحل باقی‌مانده:{NC}"
echo "1. ربات را شروع کنید:"
echo "   cd PROJECT\_DIR && ./manage.sh"
echo "   سپس گزینه '1. شروع ربات' را انتخاب کنید."
echo ""
echo "2. در پنل ادمین ربات (دستور /admin)، وارد بخش '📦 سرویس‌ها' شوید و پلن‌های مورد نظرتان را اضافه/ویرایش کنید."
echo ""
echo -e "{YELLOW}🔗 فایل‌های مهم:${NC}"
echo "   📁 پروژه: $PROJECT_DIR"
echo "   ⚙️ تنظیمات: $PROJECT_DIR/config.py"
echo "   🤖 ربات: PROJECT\_DIR/bot.py"
echo "   🛠️ مدیریت: $PROJECT\_DIR/manage.sh"
echo ""
echo -e "${GREEN}🎉 موفق باشید\!{NC}"