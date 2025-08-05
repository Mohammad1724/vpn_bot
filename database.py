# database.py

import sqlite3

DB_NAME = "vpn_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جدول کاربران
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0.0
    )
    ''')
    # جدول پلن‌ها
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS plans (
        plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        days INTEGER NOT NULL,
        gb INTEGER NOT NULL
    )
    ''')
    conn.commit()
    conn.close()

# --- User Functions ---
def get_or_create_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    conn.close()
    return {"user_id": user[0], "balance": user[1]}

def update_balance(user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- Plan Functions (Admin) ---
def add_plan(name, price, days, gb):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb))
    conn.commit()
    conn.close()

def list_plans():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plans")
    plans = cursor.fetchall()
    conn.close()
    return [{"plan_id": p[0], "name": p[1], "price": p[2], "days": p[3], "gb": p[4]} for p in plans]

def get_plan(plan_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
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
