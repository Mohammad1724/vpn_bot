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
            days INTEGER NOT NULL, gb INTEGER NOT NULL, is_visible INTEGER DEFAULT 1
        )
    ''')

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
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')

    # reminder_log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminder_log (
            service_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            PRIMARY KEY(service_id, date, type)
        )
    ''')

    # Default settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_holder', 'نام صاحب حساب'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('payment_instruction_text', 'لطفاً مبلغ را به شماره کارت بالا واریز کرده و از رسید اسکرین‌شات بگیرید.'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('referral_bonus_amount', '5000'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('default_sub_link_type', 'sub'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('daily_report_enabled', '1'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('weekly_report_enabled', '1'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('auto_backup_interval_hours', '24'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('maintenance_enabled', '0'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('maintenance_message', '⛔️ ربات در حال بروزرسانی است. لطفاً کمی بعد مراجعه کنید.'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('connection_guide', '📚 راهنمای اتصال:\n1) اپ مناسب را نصب کنید.\n2) از ربات لینک را بگیرید.\n3) وارد اپ کنید و متصل شوید.'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('expiry_reminder_enabled', '1'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('expiry_reminder_days', '3'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('expiry_reminder_hour', '9'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('expiry_reminder_message', '⏰ سرویس «{service_name}» شما {days} روز دیگر منقضی می‌شود.\nبرای جلوگیری از قطعی، از «📋 سرویس‌های من» تمدید کنید.'))

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

def add_plan(name: str, price: float, days: int, gb: int):
    conn = _connect_db()
    conn.execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb))
    conn.commit()

def get_plan(plan_id: int) -> dict:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def list_plans(only_visible: bool = False) -> list:
    conn = _connect_db()
    cur = conn.cursor()
    # مرتب‌سازی جدید: اول بر اساس روز، بعد بر اساس حجم
    sort_order = "ORDER BY days ASC, gb ASC"
    if only_visible:
        cur.execute(f"SELECT * FROM plans WHERE is_visible = 1 {sort_order}")
    else:
        cur.execute(f"SELECT * FROM plans {sort_order}")
    return [dict(r) for r in cur.fetchall()]

def update_plan(plan_id: int, data: dict):
    fields, params = [], []
    for k in ('name', 'price', 'days', 'gb'):
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

def set_device_limit_alert_sent(service_id: int, status: bool = True):
    logger.debug("set_device_limit_alert_sent() ignored (device limit removed).")

def delete_service(service_id: int):
    conn = _connect_db()
    conn.execute("DELETE FROM active_services WHERE service_id = ?", (service_id,))
    conn.commit()

def initiate_purchase_transaction(user_id: int, plan_id: int) -> int | None:
    conn = _connect_db()
    cur = conn.cursor()
    try:
        plan = get_plan(plan_id)
        user = get_user(user_id)
        if not plan or not user or user['balance'] < plan['price']:
            return None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO transactions (user_id, plan_id, type, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, 'purchase', plan['price'], 'pending', now_str, now_str)
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
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (txn['amount'], txn['user_id']))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (txn['user_id'], custom_name, sub_uuid, sub_link, txn['plan_id'], now_str)
        )
        cur.execute(
            "INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)",
            (txn['user_id'], txn['plan_id'], txn['amount'], now_str)
        )
        cur.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Error finalizing purchase {transaction_id}: {e}")
        conn.rollback()

def cancel_purchase_transaction(transaction_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    conn.execute("UPDATE transactions SET status = 'failed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
    conn.commit()

def initiate_renewal_transaction(user_id: int, service_id: int, plan_id: int) -> int | None:
    conn = _connect_db()
    cur = conn.cursor()
    try:
        plan = get_plan(plan_id)
        user = get_user(user_id)
        if not plan or not user or user['balance'] < plan['price']:
            return None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO transactions (user_id, plan_id, service_id, type, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, service_id, 'renewal', plan['price'], 'pending', now_str, now_str)
        )
        txn_id = cur.lastrowid
        conn.commit()
        return txn_id
    except sqlite3.Error as e:
        logger.error(f"Error initiating renewal: {e}")
        conn.rollback()
        return None

def finalize_renewal_transaction(transaction_id: int, new_plan_id: int):
    conn = _connect_db()
    cur = conn.cursor()
    try:
        conn.execute("BEGIN")
        cur.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending'", (transaction_id,))
        txn = cur.fetchone()
        if not txn:
            raise ValueError("Renewal transaction not found or not pending.")
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (txn['amount'], txn['user_id']))
        cur.execute("UPDATE active_services SET plan_id = ?, low_usage_alert_sent = 0 WHERE service_id = ?", (new_plan_id, txn['service_id']))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)", (txn['user_id'], txn['plan_id'], txn['amount'], now_str))
        cur.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Error finalizing renewal {transaction_id}: {e}")
        conn.rollback()

def cancel_renewal_transaction(transaction_id: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    conn.execute("UPDATE transactions SET status = 'failed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
    conn.commit()

def use_gift_code(code: str, user_id: int) -> float | None:
    conn = _connect_db()
    cur = conn.cursor()
    try:
        conn.execute("BEGIN")
        cur.execute("SELECT * FROM gift_codes WHERE code = ? AND is_used = 0", (code,))
        gift = cur.fetchone()
        if not gift:
            conn.rollback()
            return None
        amount = gift['amount']
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE gift_codes SET is_used = 1, used_by = ?, used_date = ? WHERE code = ?", (user_id, now_str, code))
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        return amount
    except sqlite3.Error as e:
        logger.error(f"Error using gift code {code}: {e}")
        conn.rollback()
        return None

def create_gift_code(code: str, amount: float):
    conn = _connect_db()
    try:
        conn.execute("INSERT INTO gift_codes (code, amount) VALUES (?, ?)", (code.upper(), amount))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_all_gift_codes() -> list:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gift_codes ORDER BY is_used ASC, code ASC")
    return [dict(row) for row in cursor.fetchall()]

def delete_gift_code(code: str) -> bool:
    conn = _connect_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gift_codes WHERE code = ?", (code,))
    conn.commit()
    return cursor.rowcount > 0

def get_setting(key: str) -> str | None:
    conn = _connect_db()
    cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    return row['value'] if row else None

def set_setting(key: str, value: str):
    conn = _connect_db()
    conn.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

def was_reminder_sent(service_id: int, type_: str, date: str) -> bool:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM reminder_log WHERE service_id = ? AND date = ? AND type = ?", (service_id, date, type_))
    return cur.fetchone() is not None

def mark_reminder_sent(service_id: int, type_: str, date: str):
    conn = _connect_db()
    conn.execute("INSERT OR IGNORE INTO reminder_log (service_id, date, type) VALUES (?, ?, ?)", (service_id, date, type_))
    conn.commit()

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
    cur = conn.cursor()
    cur.execute("SELECT * FROM sales_log WHERE sale_date >= ?", (start_date,))
    return [dict(r) for r in cur.fetchall()]

def get_popular_plans(limit=5) -> list:
    query = """
        SELECT p.name, COUNT(s.sale_id) as sales_count
        FROM plans p JOIN sales_log s ON p.plan_id = s.plan_id
        GROUP BY p.plan_id ORDER BY sales_count DESC LIMIT ?
    """
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute(query, (limit,))
    return [dict(r) for r in cur.fetchall()]

def get_user_sales_history(user_id: int) -> list:
    query = """
        SELECT s.sale_date, s.price, p.name as plan_name
        FROM sales_log s LEFT JOIN plans p ON s.plan_id = p.plan_id
        WHERE s.user_id = ? ORDER BY s.sale_id DESC
    """
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute(query, (user_id,))
    return [dict(r) for r in cur.fetchall()]

def get_service_by_name(user_id: int, name: str) -> dict | None:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM active_services WHERE user_id = ? AND name = ?", (user_id, name))
    row = cur.fetchone()
    return dict(row) if row else None

def get_user_referral_count(user_id: int) -> int:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 0

def get_user_charge_history(user_id: int) -> list:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT created_at, amount, type FROM transactions
        WHERE user_id = ?
          AND type LIKE '%charge%'
          AND status = 'completed'
        ORDER BY transaction_id DESC
    """, (user_id,))
    return [dict(r) for r in cur.fetchall()]

def add_charge_transaction(user_id: int, amount: float, type_: str = "charge"):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    conn.execute("""
        INSERT INTO transactions (user_id, plan_id, service_id, type, amount, status, created_at, updated_at)
        VALUES (?, NULL, NULL, ?, ?, 'completed', ?, ?)
    """, (user_id, type_, amount, now_str, now_str))
    conn.commit()