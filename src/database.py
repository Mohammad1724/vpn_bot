# -*- coding: utf-8 -*-

import sqlite3
import logging
from datetime import datetime, timedelta

DB_NAME = "vpn_bot.db"
logger = logging.getLogger(__name__)
_db_connection = None

def _get_connection():
    global _db_connection
    if _db_connection is None:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error as e:
            logger.warning(f"Failed to set PRAGMA options: {e}")
        _db_connection = conn
    return _db_connection

def _connect_db():
    return _get_connection()

def close_db():
    global _db_connection
    if _db_connection is not None:
        _db_connection.close()
        _db_connection = None
        logger.info("Database connection closed.")

def _add_column_if_not_exists(conn, table_name, column_name, column_type):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row['name'] for row in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        logger.info(f"Added column '{column_name}' to table '{table_name}'.")

def _remove_device_limit_alert_column_if_exists(conn: sqlite3.Connection):
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA table_info(active_services)")
        cols = [row["name"] for row in cur.fetchall()]
        if "device_limit_alert_sent" not in cols:
            return
        version_tuple = tuple(map(int, sqlite3.sqlite_version.split(".")))
        if version_tuple >= (3, 35, 0):
            cur.execute("ALTER TABLE active_services DROP COLUMN device_limit_alert_sent")
            conn.commit()
            logger.info("Removed column device_limit_alert_sent from active_services (SQLite >= 3.35).")
        else:
            logger.info("Rebuilding active_services to drop device_limit_alert_sent (SQLite < 3.35).")
            cur.execute("BEGIN")
            cur.execute('''
                CREATE TABLE IF NOT EXISTS active_services_new (
                    service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT,
                    sub_uuid TEXT NOT NULL UNIQUE, sub_link TEXT NOT NULL, plan_id INTEGER,
                    created_at TEXT NOT NULL, low_usage_alert_sent INTEGER DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(plan_id) REFERENCES plans(plan_id) ON DELETE SET NULL
                )
            ''')
            cur.execute('''
                INSERT INTO active_services_new (
                    service_id, user_id, name, sub_uuid, sub_link, plan_id, created_at, low_usage_alert_sent
                )
                SELECT service_id, user_id, name, sub_uuid, sub_link, plan_id, created_at, low_usage_alert_sent
                FROM active_services
            ''')
            cur.execute("DROP TABLE active_services")
            cur.execute("ALTER TABLE active_services_new RENAME TO active_services")
            conn.commit()
            conn.execute("CREATE INDEX IF NOT EXISTS idx_active_services_user ON active_services(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_active_services_uuid ON active_services(sub_uuid)")
            conn.commit()
            logger.info("Rebuild completed; device_limit_alert_sent removed.")
    except Exception as e:
        logger.warning(f"Couldn't remove device_limit_alert_sent column: {e}")

def init_db():
    conn = _connect_db()
    cursor = conn.cursor()

    # users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0,
            join_date TEXT NOT NULL, is_banned INTEGER DEFAULT 0, has_used_trial INTEGER DEFAULT 0,
            referred_by INTEGER, has_received_referral_bonus INTEGER DEFAULT 0
        )
    ''')
    try:
        cursor.execute("SELECT referred_by FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
    try:
        cursor.execute("SELECT has_received_referral_bonus FROM users LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE users ADD COLUMN has_received_referral_bonus INTEGER DEFAULT 0")

    # plans
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price REAL NOT NULL,
            days INTEGER NOT NULL, gb INTEGER NOT NULL, is_visible INTEGER DEFAULT 1,
            category TEXT
        )
    ''')
    try:
        cursor.execute("SELECT category FROM plans LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE plans ADD COLUMN category TEXT")

    # settings
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

    # active_services
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_services (
            service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT,
            sub_uuid TEXT NOT NULL UNIQUE, sub_link TEXT NOT NULL, plan_id INTEGER,
            created_at TEXT NOT NULL, low_usage_alert_sent INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(plan_id) REFERENCES plans(plan_id) ON DELETE SET NULL
        )
    ''')

    _remove_device_limit_alert_column_if_exists(conn)

    # sales_log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales_log (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan_id INTEGER,
            price REAL NOT NULL, sale_date TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(plan_id) REFERENCES plans(plan_id) ON DELETE SET NULL
        )
    ''')

    # gift_codes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gift_codes (
            code TEXT PRIMARY KEY, amount REAL NOT NULL, is_used INTEGER DEFAULT 0,
            used_by INTEGER, used_date TEXT, FOREIGN KEY(used_by) REFERENCES users(user_id)
        )
    ''')

    # transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan_id INTEGER,
            service_id INTEGER, type TEXT NOT NULL, amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, note TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    _add_column_if_not_exists(conn, "transactions", "note", "TEXT")

    # reminder_log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminder_log (
            service_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            PRIMARY KEY(service_id, date, type)
        )
    ''')

    # Promo codes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promo_codes (
        code TEXT PRIMARY KEY,
        percent INTEGER NOT NULL,
        max_uses INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0,
        expires_at TEXT,
        first_purchase_only INTEGER DEFAULT 1,
        is_active INTEGER DEFAULT 1
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promo_code_usages (
        code TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        used_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (code, user_id)
    )""")

    # Default settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))
    # ... (بقیه default settings)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_services_user ON active_services(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_services_uuid ON active_services(sub_uuid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_log_user ON sales_log(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_log_plan ON sales_log(plan_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

    conn.commit()
    logger.info("Database initialized successfully.")

def get_or_create_user(user_id: int, username: str = None) -> dict:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    norm_username = (username or "").lstrip('@') if username else None
    if not user:
        join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, norm_username, join_date))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    elif user['username'] != norm_username and username is not None:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (norm_username, user_id))
        conn.commit()
    return dict(user) if user else None

def get_user(user_id: int) -> dict:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def get_user_by_username(username: str) -> dict:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.lstrip('@'),))
    row = cur.fetchone()
    return dict(row) if row else None

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

def reset_user_trial(user_id: int):
    conn = _connect_db()
    conn.execute("UPDATE users SET has_used_trial = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_all_user_ids() -> list:
    conn = _connect_db()
    cur = conn.execute("SELECT user_id FROM users WHERE is_banned = 0")
    return [row['user_id'] for row in cur.fetchall()]

def get_new_users_count(days: int) -> int:
    conn = _connect_db()
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users WHERE join_date >= ?", (start_date,))
    count = cursor.fetchone()[0]
    return count or 0

def set_referrer(user_id: int, referrer_id: int):
    user = get_user(user_id)
    if user and not user.get('referred_by'):
        conn = _connect_db()
        conn.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
        conn.commit()

def apply_referral_bonus(user_id: int):
    user = get_user(user_id)
    if user and user.get('referred_by') and not user.get('has_received_referral_bonus'):
        referrer_id = user['referred_by']
        bonus_str = get_setting('referral_bonus_amount')
        try:
            bonus_amount = float(bonus_str) if bonus_str else 0.0
        except (ValueError, TypeError):
            bonus_amount = 0.0
        if bonus_amount > 0:
            conn = _connect_db()
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus_amount, user_id))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus_amount, referrer_id))
            conn.execute("UPDATE users SET has_received_referral_bonus = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            return referrer_id, bonus_amount
    return None, 0

def add_plan(name: str, price: float, days: int, gb: int, category: str):
    conn = _connect_db()
    conn.execute(
        "INSERT INTO plans (name, price, days, gb, category) VALUES (?, ?, ?, ?, ?)",
        (name, price, days, gb, category)
    )
    conn.commit()

def get_plan(plan_id: int) -> dict:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def get_plan_categories() -> list[str]:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM plans WHERE is_visible = 1 AND category IS NOT NULL ORDER BY category ASC")
    return [row['category'] for row in cur.fetchall()]

def list_plans(only_visible: bool = False, category: str = None) -> list:
    conn = _connect_db()
    cur = conn.cursor()
    query = "SELECT * FROM plans"
    conditions = []
    params = []

    if only_visible:
        conditions.append("is_visible = 1")
    if category:
        conditions.append("category = ?")
        params.append(category)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY days ASC, gb ASC"

    cur.execute(query, tuple(params))
    return [dict(r) for r in cur.fetchall()]

def update_plan(plan_id: int, data: dict):
    fields, params = [], []
    for k in ('name', 'price', 'days', 'gb', 'category'):
        if k in data:
            fields.append(f"{k} = ?")
            params.append(data[k])
    if not fields:
        return
    params.append(plan_id)
    q = f"UPDATE plans SET {', '.join(fields)} WHERE plan_id = ?"
    conn = _connect_db()
    conn.execute(q, tuple(params))
    conn.commit()

def toggle_plan_visibility(plan_id: int):
    conn = _connect_db()
    conn.execute("UPDATE plans SET is_visible = 1 - is_visible WHERE plan_id = ?", (plan_id,))
    conn.commit()

def delete_plan_safe(plan_id: int):
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN")
        detached_active = cursor.execute("UPDATE active_services SET plan_id = NULL WHERE plan_id = ?", (plan_id,)).rowcount
        detached_sales = cursor.execute("UPDATE sales_log SET plan_id = NULL WHERE plan_id = ?", (plan_id,)).rowcount
        cursor.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
        conn.commit()
        logger.info("Plan %s deleted safely. Detached active=%s, sales=%s", plan_id, detached_active, detached_sales)
        return detached_active, detached_sales
    except sqlite3.Error as e:
        logger.error("Safe delete plan %s failed: %s", plan_id, e, exc_info=True)
        conn.rollback()
        return None

def add_active_service(user_id: int, name: str, sub_uuid: str, sub_link: str, plan_id: int | None):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    conn.execute(
        "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name, sub_uuid, sub_link, plan_id, now_str)
    )
    conn.commit()

def get_service(service_id: int) -> dict:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM active_services WHERE service_id = ?", (service_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def get_service_by_uuid(uuid: str) -> dict:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM active_services WHERE sub_uuid = ?", (uuid,))
    row = cur.fetchone()
    return dict(row) if row else None

def get_user_services(user_id: int) -> list:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM active_services WHERE user_id = ?", (user_id,))
    return [dict(r) for r in cur.fetchall()]

def get_all_active_services() -> list:
    conn = _connect_db()
    cur = conn.execute("SELECT * FROM active_services")
    return [dict(r) for r in cur.fetchall()]

def set_low_usage_alert_sent(service_id: int, status=True):
    conn = _connect_db()
    conn.execute("UPDATE active_services SET low_usage_alert_sent = ? WHERE service_id = ?", (1 if status else 0, service_id))
    conn.commit()

def delete_service(service_id: int):
    conn = _connect_db()
    conn.execute("DELETE FROM active_services WHERE service_id = ?", (service_id,))
    conn.commit()

def initiate_purchase_transaction(user_id: int, plan_id: int, final_price: float) -> int | None:
    conn = _connect_db()
    cur = conn.cursor()
    try:
        user = get_user(user_id)
        if not user or user['balance'] < final_price:
            return None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO transactions (user_id, plan_id, type, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, 'purchase', final_price, 'pending', now_str, now_str)
        )
        txn_id = cur.lastrowid
        conn.commit()
        return txn_id
    except sqlite3.Error as e:
        logger.error(f"Error initiating purchase: {e}")
        conn.rollback()
        return None

def finalize_purchase_transaction(transaction_id: int, sub_uuid: str, sub_link: str, custom_name: str):
    conn = _connect_db()
    cur = conn.cursor()
    try:
        conn.execute("BEGIN")
        cur.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending'", (transaction_id,))
        txn = cur.fetchone()
        if not txn:
            raise ValueError("Transaction not found or not pending.")
        cur.execute("UPDATE users SET balance = balance 