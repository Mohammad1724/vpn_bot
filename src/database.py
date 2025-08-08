# -*- coding: utf-8 -*-

# database.py

import sqlite3
import logging
from datetime import datetime, timedelta

# --- Setup ---
DB_NAME = "vpn_bot.db"
logger = logging.getLogger(__name__)

# --- Helper for DB Connection ---
_db_connection = None

def _get_connection():
    global _db_connection
    if _db_connection is None:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Stability & performance pragmas
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error as e:
            logger.warning(f"Failed to set PRAGMA options: {e}")
        _db_connection = conn
    return _db_connection

def close_db():
    global _db_connection
    if _db_connection is not None:
        _db_connection.close()
        _db_connection = None
        logger.info("Database connection closed.")

def _connect_db():
    return _get_connection()

# --- Initialization ---
def init_db():
    conn = _connect_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            balance REAL DEFAULT 0.0, 
            join_date TEXT NOT NULL, 
            is_banned INTEGER DEFAULT 0, 
            has_used_trial INTEGER DEFAULT 0,
            referred_by INTEGER,
            has_received_referral_bonus INTEGER DEFAULT 0
        )''')
    
    # Backward-compatible schema updates
    try:
        cursor.execute("SELECT referred_by FROM users LIMIT 1")
    except sqlite3.OperationalError:
        logger.info("Adding 'referred_by' column to users table...")
        cursor.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")

    try:
        cursor.execute("SELECT has_received_referral_bonus FROM users LIMIT 1")
    except sqlite3.OperationalError:
        logger.info("Adding 'has_received_referral_bonus' column to users table...")
        cursor.execute("ALTER TABLE users ADD COLUMN has_received_referral_bonus INTEGER DEFAULT 0")

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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id INTEGER,
            service_id INTEGER,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )''')

    # Default settings (insert if missing)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_holder', 'نام صاحب حساب'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('referral_bonus_amount', '5000'))
    
    # Helpful indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_services_user ON active_services(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_log_user ON sales_log(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

    conn.commit()
    logger.info("Database initialized successfully.")

# --- User Management ---
def get_or_create_user(user_id: int, username: str = None) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, (username or '').lstrip('@') or None, join_date))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    elif user['username'] != (username or '').lstrip('@') and username is not None:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", ((username or '').lstrip('@'), user_id))
        conn.commit()

    return dict(user) if user else None

def get_user(user_id: int) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    return dict(user) if user else None

def get_user_by_username(username: str) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.lstrip('@'),))
    user = cursor.fetchone()
    return dict(user) if user else None

def update_balance(user_id: int, amount: float):
    conn = _connect_db()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def set_user_ban_status(user_id: int, is_banned: bool):
    conn = _connect_db()
    conn.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if is_banned else 0, user_id))
    conn.commit()

def set_user_trial_used(user_id: int):
    conn = _connect_db()
    conn.execute("UPDATE users SET has_used_trial = 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_all_user_ids() -> list:
    conn = _connect_db()
    cursor = conn.execute("SELECT user_id FROM users WHERE is_banned = 0")
    return [row['user_id'] for row in cursor.fetchall()]

# --- Referral System Functions ---
def set_referrer(user_id: int, referrer_id: int):
    user = get_user(user_id)
    if user and not user.get('referred_by'):
        with _connect_db() as conn:
            conn.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
            conn.commit()
            logger.info(f"User {user_id} was referred by {referrer_id}.")

def apply_referral_bonus(user_id: int):
    user = get_user(user_id)
    if user and user.get('referred_by') and not user.get('has_received_referral_bonus'):
        referrer_id = user['referred_by']
        bonus_amount_str = get_setting('referral_bonus_amount')
        bonus_amount = float(bonus_amount_str) if bonus_amount_str else 0.0

        if bonus_amount > 0:
            with _connect_db() as conn:
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus_amount, user_id))
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus_amount, referrer_id))
                conn.execute("UPDATE users SET has_received_referral_bonus = 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                logger.info(f"Applied referral bonus of {bonus_amount} to user {user_id} and referrer {referrer_id}.")
                return referrer_id, bonus_amount
    return None, 0
    
# --- Plan Management ---
def add_plan(name: str, price: float, days: int, gb: int):
    conn = _connect_db()
    conn.execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb))
    conn.commit()

def get_plan(plan_id: int) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
    plan = cursor.fetchone()
    return dict(plan) if plan else None

def list_plans(only_visible=False) -> list:
    query = "SELECT * FROM plans ORDER BY price ASC"
    if only_visible:
        query = "SELECT * FROM plans WHERE is_visible = 1 ORDER BY price ASC"
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(query)
    plans = cursor.fetchall()
    return [dict(plan) for plan in plans]

def update_plan(plan_id: int, data: dict):
    fields = []
    params = []
    for key, value in data.items():
        if key in ['name', 'price', 'days', 'gb']:
            fields.append(f"{key} = ?")
            params.append(value)
    if not fields:
        return
    params.append(plan_id)
    query = f"UPDATE plans SET {', '.join(fields)} WHERE plan_id = ?"
    conn = _connect_db()
    conn.execute(query, tuple(params))
    conn.commit()

def delete_plan(plan_id: int):
    conn = _connect_db()
    conn.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
    conn.commit()

def toggle_plan_visibility(plan_id: int):
    conn = _connect_db()
    conn.execute("UPDATE plans SET is_visible = 1 - is_visible WHERE plan_id = ?", (plan_id,))
    conn.commit()

def get_plan_by_gb_and_days(gb: int, days: int) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plans WHERE gb = ? AND days = ?", (gb, days))
    plan = cursor.fetchone()
    return dict(plan) if plan else None

# --- Service Management ---
def add_active_service(user_id: int, name: str, sub_uuid: str, sub_link: str, plan_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    conn.execute(
        "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name, sub_uuid, sub_link, plan_id, now_str)
    )
    conn.commit()

def get_service(service_id: int) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM active_services WHERE service_id = ?", (service_id,))
    service = cursor.fetchone()
    return dict(service) if service else None

def get_user_services(user_id: int) -> list:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM active_services WHERE user_id = ?", (user_id,))
    services = cursor.fetchall()
    return [dict(service) for service in services]

def get_all_active_services() -> list:
    conn = _connect_db()
    cursor = conn.execute("SELECT * FROM active_services")
    return [dict(row) for row in cursor.fetchall()]

def set_low_usage_alert_sent(service_id: int, status=True):
    conn = _connect_db()
    conn.execute("UPDATE active_services SET low_usage_alert_sent = ? WHERE service_id = ?", (1 if status else 0, service_id))
    conn.commit()

def update_service_after_renewal(service_id: int, new_plan_id: int):
    conn = _connect_db()
    conn.execute(
        "UPDATE active_services SET plan_id = ?, low_usage_alert_sent = 0 WHERE service_id = ?",
        (new_plan_id, service_id)
    )
    conn.commit()

# --- Transactional Purchase & Renewal ---
def initiate_purchase_transaction(user_id: int, plan_id: int) -> int:
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        plan = get_plan(plan_id)
        user = get_user(user_id)
        if not plan or not user or user['balance'] < plan['price']:
            return None
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

def finalize_purchase_transaction(transaction_id: int, sub_uuid: str, sub_link: str, custom_name: str):
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending'", (transaction_id,))
        trans = cursor.fetchone()
        if not trans:
            raise ValueError("Transaction not found or not pending.")
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (trans['amount'], trans['user_id']))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (trans['user_id'], custom_name, sub_uuid, sub_link, trans['plan_id'], now_str)
        )
        cursor.execute(
            "INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)",
            (trans['user_id'], trans['plan_id'], trans['amount'], now_str)
        )
        cursor.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Error finalizing purchase {transaction_id}: {e}")
        conn.rollback()

def cancel_purchase_transaction(transaction_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    conn.execute("UPDATE transactions SET status = 'failed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
    conn.commit()

def initiate_renewal_transaction(user_id: int, service_id: int, plan_id: int) -> int:
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        plan = get_plan(plan_id)
        user = get_user(user_id)
        if not plan or not user or user['balance'] < plan['price']:
            return None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

def finalize_renewal_transaction(transaction_id: int, new_plan_id: int):
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending'", (transaction_id,))
        trans = cursor.fetchone()
        if not trans:
            raise ValueError("Renewal transaction not found or not pending.")
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (trans['amount'], trans['user_id']))
        cursor.execute("UPDATE active_services SET plan_id = ?, low_usage_alert_sent = 0 WHERE service_id = ?", (new_plan_id, trans['service_id']))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)", (trans['user_id'], trans['plan_id'], trans['amount'], now_str))
        cursor.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Error finalizing renewal {transaction_id}: {e}")
        conn.rollback()

def cancel_renewal_transaction(transaction_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    conn.execute("UPDATE transactions SET status = 'failed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
    conn.commit()

# --- Gift Codes ---
def use_gift_code(code: str, user_id: int) -> float:
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor.execute("SELECT * FROM gift_codes WHERE code = ? AND is_used = 0", (code,))
        gift = cursor.fetchone()
        if not gift:
            conn.rollback()
            return None
        amount = gift['amount']
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE gift_codes SET is_used = 1, used_by = ?, used_date = ? WHERE code = ?", (user_id, now_str, code))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        return amount
    except sqlite3.Error as e:
        logger.error(f"Error using gift code {code}: {e}")
        conn.rollback()
        return None

# --- Settings ---
def get_setting(key: str) -> str:
    conn = _connect_db()
    cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    return result['value'] if result else None

def set_setting(key: str, value: str):
    conn = _connect_db()
    conn.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

# --- Reports & Stats ---
def get_stats() -> dict:
    conn = _connect_db()
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
    conn = _connect_db()
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
    conn = _connect_db()
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
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute(query, (user_id,))
    history = cursor.fetchall()
    return [dict(row) for row in history]
