# database.py (نسخه کاملاً جدید)

import sqlite3
import datetime

DB_NAME = "vpn_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جدول کاربران
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, join_date TEXT)')
    # جدول پلن‌ها
    cursor.execute('CREATE TABLE IF NOT EXISTS plans (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price REAL NOT NULL, days INTEGER NOT NULL, gb INTEGER NOT NULL)')
    # جدول تنظیمات
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    # جدول سرویس‌های فعال کاربران
    cursor.execute('CREATE TABLE IF NOT EXISTS active_services (service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, sub_link TEXT, expiry_date TEXT)')
    # جدول فروش‌ها برای آمار
    cursor.execute('CREATE TABLE IF NOT EXISTS sales (sale_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id INTEGER, price REAL, sale_date TEXT)')
    conn.commit()
    # مقداردهی اولیه تنظیمات
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_holder', 'نام صاحب حساب'))
    conn.commit()
    conn.close()

# --- توابع تنظیمات ---
def get_setting(key):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def set_setting(key, value):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()
    conn.close()

# --- توابع کاربران ---
def get_or_create_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        join_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO users (user_id, join_date) VALUES (?, ?)", (user_id, join_date))
        conn.commit()
        user = (user_id, 0.0)
    conn.close()
    return {"user_id": user[0], "balance": user[1]}

def update_balance(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_all_user_ids():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    user_ids = [item[0] for item in cursor.fetchall()]
    conn.close()
    return user_ids

# --- توابع پلن‌ها (بدون تغییر) ---
def add_plan(name, price, days, gb):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb))
    conn.commit()
    conn.close()
def list_plans():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT plan_id, name, price, days, gb FROM plans")
    plans = cursor.fetchall()
    conn.close()
    return [{"plan_id": p[0], "name": p[1], "price": p[2], "days": p[3], "gb": p[4]} for p in plans]
def get_plan(plan_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT plan_id, name, price, days, gb FROM plans WHERE plan_id = ?", (plan_id,))
    plan = cursor.fetchone()
    conn.close()
    if not plan: return None
    return {"plan_id": plan[0], "name": plan[1], "price": plan[2], "days": plan[3], "gb": plan[4]}
def delete_plan(plan_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
    conn.commit()
    conn.close()


# --- توابع سرویس‌های فعال ---
def add_active_service(user_id, sub_link, days):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    expiry_date = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO active_services (user_id, sub_link, expiry_date) VALUES (?, ?, ?)", (user_id, sub_link, expiry_date))
    conn.commit()
    conn.close()

def get_user_services(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT service_id, sub_link, expiry_date FROM active_services WHERE user_id = ?", (user_id,))
    services = cursor.fetchall()
    conn.close()
    return [{"service_id": s[0], "sub_link": s[1], "expiry_date": s[2]} for s in services]

# --- توابع آمار ---
def log_sale(user_id, plan_id, price):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    sale_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO sales (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)", (user_id, plan_id, price, sale_date))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users")
    user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(sale_id), SUM(price) FROM sales")
    sales_data = cursor.fetchone()
    sales_count = sales_data[0] or 0
    total_revenue = sales_data[1] or 0
    conn.close()
    return {"user_count": user_count, "sales_count": sales_count, "total_revenue": total_revenue}