# filename: database.py
# -*- coding: utf-8 -*-

import sqlite3
import logging
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

# NEW: for admin notifications
import httpx
try:
    from config import BOT_TOKEN, ADMIN_ID
except Exception:
    BOT_TOKEN, ADMIN_ID = "", ""

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
                    server_name TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(plan_id) REFERENCES plans(plan_id) ON DELETE SET NULL
                )
            ''')
            cur.execute('''
                INSERT INTO active_services_new (
                    service_id, user_id, name, sub_uuid, sub_link, plan_id, created_at, low_usage_alert_sent, server_name
                )
                SELECT service_id, user_id, name, sub_uuid, sub_link, plan_id, created_at, low_usage_alert_sent, NULL
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

# ===== Admin notifications (helpers) =====
def _escape_html(s) -> str:
    try:
        t = str(s)
    except Exception:
        t = ""
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _iter_admin_chat_ids():
    ids = []
    raw = ADMIN_ID
    if raw is None:
        return ids
    if isinstance(raw, (list, tuple, set)):
        seq = list(raw)
    else:
        s = str(raw).strip()
        if not s:
            seq = []
        else:
            # allow comma/semicolon separated
            seq = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
    for item in seq:
        try:
            ids.append(int(item))
        except Exception:
            ids.append(item)
    return ids

def _send_admin_message(text: str):
    """
    Sends a message to configured ADMIN_ID(s) via Telegram Bot API.
    Safe: ignores errors and never raises.
    """
    if not BOT_TOKEN:
        return
    admin_ids = _iter_admin_chat_ids()
    if not admin_ids:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload_base = {"parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        with httpx.Client(timeout=7.0, follow_redirects=True) as client:
            for chat_id in admin_ids:
                data = {"chat_id": chat_id, "text": text}
                data.update(payload_base)
                try:
                    client.post(url, json=data)
                except Exception as e:
                    logger.warning("Admin notify failed for chat_id=%s: %s", chat_id, e)
    except Exception as e:
        logger.warning("Admin notify batch failed: %s", e)

def _notify_purchase(user_id: int, plan_name: str, amount: float, custom_name: str, sub_uuid: str):
    ulink = f'<a href="tg://user?id={user_id}">{user_id}</a>'
    amt = 0
    try:
        amt = int(round(float(amount or 0)))
    except Exception:
        pass
    text = (
        "✅ <b>خرید جدید انجام شد</b>\n"
        f"• کاربر: {ulink}\n"
        f"• پلن: {_escape_html(plan_name) if plan_name else '-'}\n"
        f"• مبلغ: {amt:,} تومان\n"
        f"• نام سرویس: {_escape_html(custom_name)}\n"
        f"• UUID: <code>{_escape_html(sub_uuid)}</code>\n"
        f"• زمان: {_escape_html(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
    )
    _send_admin_message(text)

def _notify_renewal(user_id: int, service_id: int, plan_name: str, amount: float):
    ulink = f'<a href="tg://user?id={user_id}">{user_id}</a>'
    amt = 0
    try:
        amt = int(round(float(amount or 0)))
    except Exception:
        pass
    text = (
        "🔁 <b>تمدید سرویس انجام شد</b>\n"
        f"• کاربر: {ulink}\n"
        f"• سرویس: #{service_id}\n"
        f"• پلن: {_escape_html(plan_name) if plan_name else '-'}\n"
        f"• مبلغ: {amt:,} تومان\n"
        f"• زمان: {_escape_html(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
    )
    _send_admin_message(text)

def _notify_trial_used(user_id: int):
    days = (get_setting("trial_days") or "-")
    gb = (get_setting("trial_gb") or "-")
    ulink = f'<a href="tg://user?id={user_id}">{user_id}</a>'
    text = (
        "🧪 <b>سرویس تست فعال شد</b>\n"
        f"• کاربر: {ulink}\n"
        f"• شرایط: {gb} GB | {days} روز\n"
        f"• زمان: {_escape_html(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
    )
    _send_admin_message(text)
# =========================================


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
            server_name TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(plan_id) REFERENCES plans(plan_id) ON DELETE SET NULL
        )
    ''')

    # Ensure server_name column exists
    _add_column_if_not_exists(conn, "active_services", "server_name", "TEXT")

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

    # Aggregated user traffic per server (snapshot)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_traffic (
            user_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            traffic_used REAL NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL,
            PRIMARY KEY (user_id, server_name)
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_traffic_user ON user_traffic(user_id)")

    # service_endpoints
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS service_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            server_name TEXT,
            sub_uuid TEXT,
            sub_link TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(service_id) REFERENCES active_services(service_id) ON DELETE CASCADE
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_endpoints_service ON service_endpoints(service_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_endpoints_uuid ON service_endpoints(sub_uuid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_endpoints_server ON service_endpoints(server_name)")

    # Default settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))

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

def _resolve_server_name_from_link(sub_link: str) -> str | None:
    try:
        parsed = urlparse(sub_link)
        host = (parsed.hostname or "").lower()
        return host or None
    except Exception:
        return None

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
    """
    علامت‌گذاری استفاده از سرویس تست.
    تنها در صورتی که قبلاً 0 بوده به 1 تغییر می‌دهیم و سپس به ادمین اطلاع می‌دهیم.
    """
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT has_used_trial FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row and int(row[0] or 0) == 1:
        return
    conn.execute("UPDATE users SET has_used_trial = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    try:
        _notify_trial_used(user_id)
    except Exception as e:
        logger.warning("Failed to notify trial used for user %s: %s", user_id, e)

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

def add_active_service(user_id: int, name: str, sub_uuid: str, sub_link: str, plan_id: int | None, server_name: str | None = None):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    if server_name is None:
        server_name = _resolve_server_name_from_link(sub_link)
    conn.execute(
        "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at, server_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, name, sub_uuid, sub_link, plan_id, now_str, server_name)
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
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user_balance = cursor.fetchone()
        if not user_balance or user_balance['balance'] < final_price:
            conn.rollback()
            return None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO transactions (user_id, plan_id, type, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, 'purchase', final_price, 'pending', now_str, now_str)
        )
        txn_id = cursor.lastrowid
        conn.commit()
        return txn_id
    except sqlite3.Error as e:
        logger.error(f"Error initiating purchase: {e}", exc_info=True)
        conn.rollback()
        return None

def finalize_purchase_transaction(transaction_id: int, sub_uuid: str, sub_link: str, custom_name: str):
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending' AND type = 'purchase'", (transaction_id,))
        txn = cursor.fetchone()
        if not txn:
            conn.rollback()
            raise ValueError("Transaction not found or not pending (purchase).")
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (txn['amount'], txn['user_id']))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        server_name = _resolve_server_name_from_link(sub_link)
        cursor.execute(
            "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, created_at, server_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (txn['user_id'], custom_name, sub_uuid, sub_link, txn['plan_id'], now_str, server_name)
        )
        cursor.execute(
            "INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)",
            (txn['user_id'], txn['plan_id'], txn['amount'], now_str)
        )
        cursor.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()
        logger.info(f"Purchase transaction {transaction_id} successfully finalized")
        # Admin notify (safe, post-commit)
        try:
            plan_row = get_plan(int(txn['plan_id'])) if txn['plan_id'] is not None else None
            plan_name = plan_row.get('name') if plan_row else None
            _notify_purchase(int(txn['user_id']), plan_name or "", float(txn['amount']), str(custom_name or ""), str(sub_uuid or ""))
        except Exception as e:
            logger.warning("Notify purchase failed for txn %s: %s", transaction_id, e)
    except Exception as e:
        logger.error(f"Error finalizing purchase {transaction_id}: {e}", exc_info=True)
        conn.rollback()
        raise

def cancel_purchase_transaction(transaction_id: int):
    conn = _connect_db()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("BEGIN TRANSACTION")
        conn.execute("UPDATE transactions SET status = 'failed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()
        logger.info(f"Purchase transaction {transaction_id} cancelled")
    except sqlite3.Error as e:
        logger.error(f"Error cancelling transaction {transaction_id}: {e}")
        conn.rollback()

def initiate_renewal_transaction(user_id: int, service_id: int, plan_id: int) -> int | None:
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")
        plan = get_plan(plan_id)
        service = get_service(service_id)
        if not plan or not service:
            conn.rollback()
            return None
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user_balance = cursor.fetchone()
        if not user_balance or user_balance['balance'] < plan['price']:
            conn.rollback()
            return None
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO transactions (user_id, plan_id, service_id, type, amount, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan_id, service_id, 'renewal', plan['price'], 'pending', now_str, now_str)
        )
        txn_id = cursor.lastrowid
        conn.commit()
        return txn_id
    except sqlite3.Error as e:
        logger.error(f"Error initiating renewal: {e}", exc_info=True)
        conn.rollback()
        return None

def finalize_renewal_transaction(transaction_id: int, new_plan_id: int):
    """
    تمدید: مبلغ کسر می‌شود، سرویس به پلن جدید/فعلی ست می‌شود،
    هشدار مصرف کم ریست و created_at به اکنون تغییر می‌کند تا روزها ریست شوند.
    """
    conn = _connect_db()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")
        cursor.execute("SELECT * FROM transactions WHERE transaction_id = ? AND status = 'pending' AND type = 'renewal'", (transaction_id,))
        txn = cursor.fetchone()
        if not txn:
            conn.rollback()
            raise ValueError("Renewal transaction not found or not pending.")
        # تطبیق plan_id
        plan_to_apply = int(new_plan_id or 0) or int(txn['plan_id'])
        if plan_to_apply != int(txn['plan_id']):
            cursor.execute("UPDATE transactions SET plan_id = ? WHERE transaction_id = ?", (plan_to_apply, transaction_id))
        # کسر مبلغ
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (txn['amount'], txn['user_id']))
        # به‌روزرسانی سرویس: plan + created_at + reset low_usage_alert_sent
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE active_services SET plan_id = ?, low_usage_alert_sent = 0, created_at = ? WHERE service_id = ?",
            (plan_to_apply, now_str, txn['service_id'])
        )
        # ثبت فروش
        cursor.execute("INSERT INTO sales_log (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)",
                       (txn['user_id'], plan_to_apply, txn['amount'], now_str))
        # وضعیت تراکنش
        cursor.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()
        logger.info(f"Renewal transaction {transaction_id} successfully finalized (plan {plan_to_apply})")
        # Admin notify (safe, post-commit)
        try:
            plan_row = get_plan(int(plan_to_apply)) if plan_to_apply else None
            plan_name = plan_row.get('name') if plan_row else None
            _notify_renewal(int(txn['user_id']), int(txn['service_id']), plan_name or "", float(txn['amount']))
        except Exception as e:
            logger.warning("Notify renewal failed for txn %s: %s", transaction_id, e)
    except Exception as e:
        logger.error(f"Error finalizing renewal {transaction_id}: {e}", exc_info=True)
        conn.rollback()
        raise

def cancel_renewal_transaction(transaction_id: int):
    conn = _connect_db()
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("BEGIN TRANSACTION")
        conn.execute("UPDATE transactions SET status = 'failed', updated_at = ? WHERE transaction_id = ?", (now_str, transaction_id))
        conn.commit()
        logger.info(f"Renewal transaction {transaction_id} cancelled")
    except sqlite3.Error as e:
        logger.error(f"Error cancelling renewal transaction {transaction_id}: {e}")
        conn.rollback()

def use_gift_code(code: str, user_id: int) -> float | None:
    conn = _connect_db()
    cur = conn.cursor()
    try:
        code_up = (code or "").strip().upper()
        conn.execute("BEGIN")
        cur.execute("SELECT * FROM gift_codes WHERE code = ? AND is_used = 0", (code_up,))
        gift = cur.fetchone()
        if not gift:
            conn.rollback()
            return None
        amount = gift['amount']
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE gift_codes SET is_used = 1, used_by = ?, used_date = ? WHERE code = ?", (user_id, now_str, code_up))
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
    code_up = (code or "").strip().upper()
    cursor.execute("DELETE FROM gift_codes WHERE code = ?", (code_up,))
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
        SELECT t.created_at as sale_date, t.amount as price, p.name as plan_name
        FROM transactions t
        LEFT JOIN plans p ON t.plan_id = p.plan_id
        WHERE t.user_id = ? AND t.type IN ('purchase', 'renewal') AND t.status = 'completed'
        ORDER BY t.transaction_id DESC
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

# --- Promo Codes ---
def add_promo_code(code, percent, max_uses, expires_at, first_purchase_only):
    with _connect_db() as conn:
        conn.execute(
            "INSERT INTO promo_codes (code, percent, max_uses, used_count, expires_at, first_purchase_only, is_active) VALUES (?, ?, ?, 0, ?, ?, 1)",
            (code.upper(), percent, max_uses, expires_at, 1 if first_purchase_only else 0)
        )

def get_promo_code(code):
    with _connect_db() as conn:
        return conn.execute("SELECT * FROM promo_codes WHERE code = ?", (code.upper(),)).fetchone()

def get_all_promo_codes():
    with _connect_db() as conn:
        return conn.execute("SELECT * FROM promo_codes ORDER BY is_active DESC, expires_at DESC").fetchall()

def delete_promo_code(code: str) -> bool:
    with _connect_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM promo_codes WHERE code = ?", (code.upper(),))
        conn.commit()
        return cur.rowcount > 0

def get_user_purchase_count(user_id):
    with _connect_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM sales_log WHERE user_id = ?", (user_id,)).fetchone()[0]

def did_user_use_promo_code(user_id, code):
    with _connect_db() as conn:
        return conn.execute("SELECT 1 FROM promo_code_usages WHERE user_id = ? AND code = ?", (user_id, code.upper())).fetchone() is not None

def mark_promo_code_as_used(user_id, code):
    with _connect_db() as conn:
        conn.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (code.upper(),))
        conn.execute("INSERT INTO promo_code_usages (code, user_id) VALUES (?, ?)", (code.upper(), user_id))
        conn.commit()

# --- Charge Requests ---
def create_charge_request(user_id: int, amount: float, note: str = "") -> int | None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO transactions (user_id, type, amount, status, created_at, updated_at, note) VALUES (?, 'charge', ?, 'pending', ?, ?, ?)",
            (user_id, amount, now_str, now_str, note)
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Failed to create charge request for user {user_id}: {e}")
        return None

def get_charge_request(charge_id: int) -> dict | None:
    conn = _connect_db()
    row = conn.execute("SELECT * FROM transactions WHERE transaction_id = ? AND type = 'charge'", (charge_id,)).fetchone()
    return dict(row) if row else None

def confirm_charge_request(charge_id: int) -> bool:
    conn = _connect_db()
    try:
        with conn:
            req = conn.execute(
                "SELECT * FROM transactions WHERE transaction_id = ? AND type = 'charge' AND status = 'pending'",
                (charge_id,)
            ).fetchone()
            if not req:
                return False
            user_id = req['user_id']
            amount = req['amount']
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            conn.execute("UPDATE transactions SET status = 'completed', updated_at = ? WHERE transaction_id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), charge_id))
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to confirm charge request {charge_id}: {e}")
        return False

def reject_charge_request(charge_id: int) -> bool:
    conn = _connect_db()
    try:
        with conn:
            res = conn.execute(
                "UPDATE transactions SET status = 'rejected', updated_at = ? WHERE transaction_id = ? AND type = 'charge' AND status = 'pending'",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), charge_id)
            )
            return res.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Failed to reject charge request {charge_id}: {e}")
        return False

def get_user_charge_count(user_id: int) -> int:
    conn = _connect_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM transactions 
            WHERE user_id = ? AND type = 'charge' AND status = 'completed'
        """, (user_id,))
        return cur.fetchone()[0] or 0
    except Exception as e:
        logger.error(f"Error getting charge count for user {user_id}: {e}")
        return 0

# --- Aggregated user traffic helpers ---
def upsert_user_traffic(user_id: int, server_name: str, traffic_used_gb: float):
    conn = _connect_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO user_traffic (user_id, server_name, traffic_used, last_updated)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, server_name) DO UPDATE SET
            traffic_used = excluded.traffic_used,
            last_updated = excluded.last_updated
    """, (user_id, server_name or "Unknown", float(traffic_used_gb or 0), now_str))
    conn.commit()

def get_total_user_traffic(user_id: int) -> float:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT SUM(traffic_used) FROM user_traffic WHERE user_id = ?", (user_id,))
    val = cur.fetchone()[0]
    return float(val or 0.0)

def backfill_active_services_server_names() -> int:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT service_id, sub_link FROM active_services WHERE server_name IS NULL OR TRIM(server_name) = ''")
    rows = cur.fetchall()
    if not rows:
        return 0
    updated = 0
    for r in rows:
        sid = r["service_id"]
        link = r["sub_link"]
        name = _resolve_server_name_from_link(link)
        if name:
            conn.execute("UPDATE active_services SET server_name = ? WHERE service_id = ?", (name, sid))
            updated += 1
    conn.commit()
    if updated:
        logger.info("Backfilled server_name for %d active services.", updated)
    return updated

def delete_user_traffic_not_in_and_older(user_id: int, allowed_servers: list[str], older_than_minutes: int, also_delete_unknown: bool = True):
    try:
        conn = _connect_db()
        cur = conn.cursor()
        threshold_dt = datetime.now() - timedelta(minutes=int(older_than_minutes or 0))
        threshold_str = threshold_dt.strftime("%Y-%m-%d %H:%M:%S")
        if not allowed_servers:
            if also_delete_unknown:
                conn.execute(
                    "DELETE FROM user_traffic WHERE user_id = ? AND server_name = 'Unknown' AND last_updated < ?",
                    (user_id, threshold_str)
                )
                conn.commit()
            return
        placeholders = ",".join(["?"] * len(allowed_servers))
        params = [user_id, threshold_str] + allowed_servers
        conn.execute(
            f"DELETE FROM user_traffic WHERE user_id = ? AND last_updated < ? AND server_name NOT IN ({placeholders})",
            tuple(params)
        )
        if also_delete_unknown:
            conn.execute(
                "DELETE FROM user_traffic WHERE user_id = ? AND server_name = 'Unknown' AND last_updated < ?",
                (user_id, threshold_str)
            )
        conn.commit()
    except Exception as e:
        logger.error("delete_user_traffic_not_in_and_older failed for user %s: %s", user_id, e, exc_info=True)

# ===================== Service Endpoints (optional) =====================
def add_service_endpoint(service_id: int, server_name: str | None, sub_uuid: str | None, sub_link: str) -> int:
    conn = _connect_db()
    cur = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO service_endpoints (service_id, server_name, sub_uuid, sub_link, created_at) VALUES (?, ?, ?, ?, ?)",
        (service_id, server_name, sub_uuid, sub_link, now_str)
    )
    conn.commit()
    return cur.lastrowid

def list_service_endpoints(service_id: int) -> list:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM service_endpoints WHERE service_id = ? ORDER BY id ASC", (service_id,))
    return [dict(r) for r in cur.fetchall()]

def delete_service_endpoints(service_id: int):
    conn = _connect_db()
    conn.execute("DELETE FROM service_endpoints WHERE service_id = ?", (service_id,))
    conn.commit()

def list_all_endpoints_with_user() -> list:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT se.id, se.service_id, se.server_name, se.sub_uuid, se.sub_link, s.user_id
        FROM service_endpoints se
        JOIN active_services s ON s.service_id = se.service_id
        ORDER BY se.id ASC
    """)
    return [dict(r) for r in cur.fetchall()]

# ========== Users list and segmentation ==========
def get_users_with_no_orders() -> list[int]:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.user_id FROM users u
        LEFT JOIN sales_log s ON u.user_id = s.user_id
        WHERE s.sale_id IS NULL
    """)
    return [row['user_id'] for row in cur.fetchall()]

def get_expired_user_ids(min_weeks_ago: int = 0) -> list[int]:
    conn = _connect_db()
    cur = conn.cursor()
    query = """
        SELECT
            s.user_id
        FROM active_services s
        JOIN plans p ON s.plan_id = p.plan_id
        GROUP BY s.user_id
        HAVING MAX(STRFTIME('%s', s.created_at) + (p.days * 86400)) < STRFTIME('%s', 'now', ?)
    """
    offset_str = f'-{min_weeks_ago * 7} days'
    cur.execute(query, (offset_str,))
    return [row['user_id'] for row in cur.fetchall()]

def get_users_with_no_orders_count() -> int:
    return len(get_users_with_no_orders())

def get_expired_users_count(min_weeks_ago: int = 0) -> int:
    return len(get_expired_user_ids(min_weeks_ago))

def get_total_users_count() -> int:
    conn = _connect_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(user_id) FROM users")
    count = cur.fetchone()[0]
    return count or 0

def get_all_users_paginated(page: int = 1, page_size: int = 15) -> list[dict]:
    conn = _connect_db()
    cur = conn.cursor()
    offset = (page - 1) * page_size
    cur.execute("SELECT * FROM users ORDER BY user_id DESC LIMIT ? OFFSET ?", (page_size, offset))
    return [dict(row) for row in cur.fetchall()]

def is_user_active(user_id: int) -> bool:
    conn = _connect_db()
    cur = conn.cursor()
    query = """
        SELECT 1
        FROM active_services s
        JOIN plans p ON s.plan_id = p.plan_id
        WHERE s.user_id = ?
        AND STRFTIME('%s', s.created_at) + (p.days * 86400) > STRFTIME('%s', 'now')
        LIMIT 1
    """
    cur.execute(query, (user_id,))
    return cur.fetchone() is not None