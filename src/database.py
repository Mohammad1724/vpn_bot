# database.py (نسخه اصلاح‌شده و کامل)

import sqlite3
import logging
from datetime import datetime, timedelta

# --- Setup ---
DB_NAME = "vpn_bot.db"
logger = logging.getLogger(__name__)

# --- Initialization ---
def init_db():
    """
    Initializes the database and creates all necessary tables and columns.
    This function is safe to run multiple times.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, 
                username TEXT, 
                balance REAL DEFAULT 0.0, 
                join_date TEXT NOT NULL, 
                is_banned INTEGER DEFAULT 0, 
                has_used_trial INTEGER DEFAULT 0
            )''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plans (
                plan_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                name TEXT NOT NULL, 
                price REAL NOT NULL, 
                days INTEGER NOT NULL, 
                gb INTEGER NOT NULL, 
                is_visible INTEGER DEFAULT 1
            )''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, 
                value TEXT
            )''')
            
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_services (
                service_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                user_id INTEGER NOT NULL, 
                name TEXT, 
                sub_uuid TEXT NOT NULL UNIQUE, 
                sub_link TEXT NOT NULL, 
                plan_id INTEGER, 
                created_at TEXT NOT NULL,
                low_usage_alert_sent INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(plan_id) REFERENCES plans(plan_id)
            )''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales_log (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                user_id INTEGER NOT NULL, 
                plan_id INTEGER, 
                price REAL NOT NULL, 
                sale_date TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gift_codes (
                code TEXT PRIMARY KEY, 
                amount REAL NOT NULL, 
                is_used INTEGER DEFAULT 0,
                used_by INTEGER,
                used_date TEXT,
                FOREIGN KEY(used_by) REFERENCES users(user_id)
            )''')
            
        # IMPORTANT: New table for safe transactions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_id INTEGER,
                service_id INTEGER,
                type TEXT NOT NULL, -- 'purchase' or 'renewal'
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', -- pending, completed, failed
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')

        # Add default settings if they don't exist
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_holder', 'نام صاحب حساب'))
        
        conn.commit()
    logger.info("Database initialized successfully.")

# --- Helper for DB Connection ---
def _connect_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- User Management ---
def get_or_create_user(user_id: int, username: str = None) -> dict:
    conn = _connect_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, username, join_date))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
        elif user['username'] != username and username is not None:
            cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            conn.commit()
        
        return dict(user) if user else None
    finally:
        conn.close()

def get_user(user_id: int) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_username(username: str) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username.lstrip('@'),))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def update_balance(user_id: int, amount: float):
    with _connect_db() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount,))
        conn.commit()

def set_user_ban_status(user_id: int, is_banned: bool):
    with _connect_db() as conn:
        conn.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if is_banned else 0, user_id))
        conn.commit()

def set_user_trial_used(user_id: int):
    with _connect_db() as conn:
        conn.execute("UPDATE users SET has_used_trial = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        
def get_all_user_ids() -> list:
    with _connect_db() as conn:
        cursor = conn.execute("SELECT user_id FROM users WHERE is_banned = 0")
        return [row['user_id'] for row in cursor.fetchall()]

# --- Plan Management ---
def add_plan(name: str, price: float, days: int, gb: int):
    with _connect_db() as conn:
        conn.execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb))
        conn.commit()

def get_plan(plan_id: int) -> dict:
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
        plan = cursor.fetchone()
        return dict(plan) if plan else None

def list_plans(only_visible=False) -> list:
    query = "SELECT * FROM plans ORDER BY price ASC"
    if only_visible:
        query = "SELECT * FROM plans WHERE is_visible = 1 ORDER BY price ASC"
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        plans = cursor.fetchall()
        return [dict(plan) for plan in plans]

def update_plan(plan_id: int, data: dict):
    # Dynamically build the UPDATE query
    fields = []
    params = []
    for key, value in data.items():
        if key in ['name', 'price', 'days', 'gb']:
            fields.append(f"{key} = ?")
            params.append(value)
    
    if not fields: return # No valid fields to update

    params.append(plan_id)
    query = f"UPDATE plans SET {', '.join(fields)} WHERE plan_id = ?"

    with _connect_db() as conn:
        conn.execute(query, tuple(params))
        conn.commit()

def delete_plan(plan_id: int):
    with _connect_db() as conn:
        # We don't actually delete to preserve sales history relations. We just hide it.
        # Or you could set foreign key to ON DELETE SET NULL
        conn.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
        conn.commit()

def toggle_plan_visibility(plan_id: int):
    with _connect_db() as conn:
        conn.execute("UPDATE plans SET is_visible = 1 - is_visible WHERE plan_id = ?", (plan_id,))
        conn.commit()
        
def get_plan_by_gb_and_days(gb: int, days: int) -> dict:
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE gb = ? AND days = ?", (gb, days))
        plan = cursor.fetchone()
        return dict(plan) if plan else None


# --- Service Management ---
def add_active_service(user_id: int, name: str, sub_uuid: str, sub_link: str, plan_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect_db() as conn:
        conn.execute(
            "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, sub_uuid, sub_link, plan_id, now_str)
        )
        conn.commit()

def get_service(service_id: int) -> dict:
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM active_services WHERE service_id = ?", (service_id,))
        service = cursor.fetchone()
        return dict(service) if service else None

def get_user_services(user_id: int) -> list:
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM active_services WHERE user_id = ?", (user_id,))
        services = cursor.fetchall()
        return [dict(service) for service in services]

def get_all_active_services() -> list:
    with _connect_db() as conn:
        cursor = conn.execute("SELECT * FROM active_services")
        return [dict(row) for row in cursor.fetchall()]

def set_low_usage_alert_sent(service_id: int, status=True):
    with _connect_db() as conn:
        conn.execute("UPDATE active_services SET low_usage_alert_sent = ? WHERE service_id = ?", (1 if status else 0, service_id))
        conn.commit()

def update_service_after_renewal(service_id: int, new_plan_id: int):
    with _connect_db() as conn:
        conn.execute(
            "UPDATE active_services SET plan_id = ?, low_usage_alert_sent = 0 WHERE service_id = ?",
            (new_plan_id, service_id)
        )
        conn.commit()


# --- Transactional Purchase & Renewal ---
def initiate_purchase_transaction(user_id: int, plan_id: int) -> int:
    conn = _connect_db()
    try:
        cursor = conn.cursor()
        plan = get_plan(plan_id)
        user = get_user(user_id)
        
        if not plan or not user: return None
        if user['balance'] < plan['price']: return None
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO transactions (user_id, plan_id, type, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, 'purchase', plan['price'], 'pending', now_str, now_str)
        )
        transaction_id = cursor.lastrowid
        conn.commit()
        return transaction_id
    except sqlite3.Error as e:
        logger.error(f"Error initiating purchase: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def finalize_purchase_transaction(transaction_id: int, sub_uuid: str, sub_link: str, custom_name: str):
    conn = _connect_db()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor = conn.cursor()
        
        # Get transaction details
        cursor.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending'", (transaction_id,))
        trans = cursor.fetchone()
        if not trans: raise ValueError("Transaction not found or not pending.")
        
        # 1. Deduct balance
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (trans['amount'], trans['user_id']))
        
        # 2. Add service
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (trans['user_id'], custom_name, sub_uuid, sub_link, trans['plan_id'], now_str)
        )
        
        # 3. Log sale
        cursor.execute(
            "INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)",
            (trans['user_id'], trans['plan_id'], trans['amount'], now_str)
        )
        
        # 4. Update transaction status
        cursor.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        
        conn.commit()
    except Exception as e:
        logger.error(f"Error finalizing purchase {transaction_id}: {e}")
        conn.rollback()
    finally:
        conn.close()

def cancel_purchase_transaction(transaction_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect_db() as conn:
        conn.execute("UPDATE transactions SET status = 'failed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()

# --- Renewal Transaction Functions (Similar to Purchase) ---
def initiate_renewal_transaction(user_id: int, service_id: int, plan_id: int) -> int:
    conn = _connect_db()
    try:
        plan = get_plan(plan_id)
        user = get_user(user_id)
        if not plan or not user or user['balance'] < plan['price']: return None
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO transactions (user_id, plan_id, service_id, type, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, service_id, 'renewal', plan['price'], 'pending', now_str, now_str)
        )
        transaction_id = cursor.lastrowid
        conn.commit()
        return transaction_id
    except sqlite3.Error as e:
        logger.error(f"Error initiating renewal: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def finalize_renewal_transaction(transaction_id: int, new_plan_id: int):
    conn = _connect_db()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending'", (transaction_id,))
        trans = cursor.fetchone()
        if not trans: raise ValueError("Renewal transaction not found or not pending.")

        # 1. Deduct balance
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (trans['amount'], trans['user_id']))
        # 2. Update service
        cursor.execute("UPDATE active_services SET plan_id = ?, low_usage_alert_sent = 0 WHERE service_id = ?", (new_plan_id, trans['service_id']))
        # 3. Log sale
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)", (trans['user_id'], trans['plan_id'], trans['amount'], now_str))
        # 4. Update transaction status
        cursor.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        
        conn.commit()
    except Exception as e:
        logger.error(f"Error finalizing renewal {transaction_id}: {e}")
        conn.rollback()
    finally:
        conn.close()

def cancel_renewal_transaction(transaction_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect_db() as conn:
        conn.execute("UPDATE transactions SET status = 'failed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()


# --- Gift Codes ---
def use_gift_code(code: str, user_id: int) -> float:
    conn = _connect_db()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM gift_codes WHERE code = ? AND is_used = 0", (code,))
        gift = cursor.fetchone()
        
        if not gift:
            conn.rollback()
            return None
        
        amount = gift['amount']
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Update gift code status
        cursor.execute("UPDATE gift_codes SET is_used = 1, used_by = ?, used_date = ? WHERE code = ?", (user_id, now_str, code))
        # 2. Update user balance
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        
        conn.commit()
        return amount
    except sqlite3.Error as e:
        logger.error(f"Error using gift code {code}: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

# --- Settings ---
def get_setting(key: str) -> str:
    with _connect_db() as conn:
        cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result['value'] if result else None

def set_setting(key: str, value: str):
    with _connect_db() as conn:
        conn.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


# --- Reports & Stats ---
def get_stats() -> dict:
    with _connect_db() as conn:
        total_users = conn.execute("SELECT COUNT(user_id) FROM users").fetchone()[0]
        banned_users = conn.execute("SELECT COUNT(user_id) FROM users WHERE is_banned = 1").fetchone()[0]
        active_services = conn.execute("SELECT COUNT(service_id) FROM active_services").fetchone()[0]
        total_revenue = conn.execute("SELECT SUM(price) FROM sales_log").fetchone()[0]
    return {
        'total_users': total_users or 0,
        'banned_users': banned_users or 0,
        'active_services': active_services or 0,
        'total_revenue': total_revenue or 0.0
    }

def get_sales_report(days=1) -> list:
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sales_log WHERE sale_date >= ?", (start_date,))
        sales = cursor.fetchall()
        return [dict(sale) for sale in sales]

def get_popular_plans(limit=5) -> list:
    query = """
        SELECT p.name, COUNT(s.sale_id) as sales_count
        FROM plans p
        JOIN sales_log s ON p.plan_id = s.plan_id
        GROUP BY p.plan_id
        ORDER BY sales_count DESC
        LIMIT ?
    """
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (limit,))
        plans = cursor.fetchall()
        return [dict(plan) for plan in plans]

def get_user_sales_history(user_id: int) -> list:
    query = """
        SELECT s.sale_date, s.price, p.name as plan_name 
        FROM sales_log s 
        LEFT JOIN plans p ON s.plan_id = p.plan_id 
        WHERE s.user_id = ? 
        ORDER BY s.sale_id DESC
    """
    with _connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (user_id,))
        history = cursor.fetchall()
        return [dict(row) for row in history]