import sqlite3
import datetime
import uuid

DB_NAME = "vpn_bot.db"

def _execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            if commit: conn.commit(); return True
            if fetchone: return cursor.fetchone()
            if fetchall: return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error: {e}"); return None if fetchone or fetchall else False

def init_db():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, join_date TEXT, is_banned INTEGER DEFAULT 0, has_used_trial INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price REAL NOT NULL, days INTEGER NOT NULL, gb INTEGER NOT NULL, is_visible INTEGER DEFAULT 1)''')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS active_services (service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT, sub_uuid TEXT NOT NULL, sub_link TEXT NOT NULL, last_api_update TEXT, plan_id INTEGER, low_usage_alert_sent INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales (sale_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan_id INTEGER NOT NULL, price REAL NOT NULL, sale_date TEXT NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS gift_codes (code TEXT PRIMARY KEY, amount REAL NOT NULL, usage_limit INTEGER NOT NULL, used_count INTEGER DEFAULT 0)''')
    
    try: cursor.execute('ALTER TABLE users ADD COLUMN username TEXT;')
    except sqlite3.OperationalError: pass
    try: cursor.execute('ALTER TABLE plans ADD COLUMN is_visible INTEGER DEFAULT 1;')
    except sqlite3.OperationalError: pass
    try: cursor.execute('ALTER TABLE active_services ADD COLUMN name TEXT;')
    except sqlite3.OperationalError: pass
    try: cursor.execute('ALTER TABLE active_services ADD COLUMN low_usage_alert_sent INTEGER DEFAULT 0;')
    except sqlite3.OperationalError: pass
    try: cursor.execute('ALTER TABLE active_services RENAME COLUMN expiry_date TO last_api_update;')
    except sqlite3.OperationalError: pass
    
    conn.commit()
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000')); cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_holder', 'نام صاحب حساب')); conn.commit(); conn.close()
    
# --- New Reporting and Stats Functions ---
def get_sales_report_for_period(days=1):
    """Generates a sales report for a given period (e.g., 1 for today, 7 for last week)."""
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    report = _execute(
        "SELECT COUNT(sale_id) as count, SUM(price) as total FROM sales WHERE sale_date >= ?",
        (start_date,), fetchone=True
    )
    return {
        "sales_count": report['count'] or 0,
        "total_revenue": report['total'] or 0.0
    }

def get_most_popular_plans():
    """Returns a list of plans ordered by their sales count."""
    query = """
        SELECT p.name, p.price, COUNT(s.sale_id) as sales_count
        FROM plans p
        LEFT JOIN sales s ON p.plan_id = s.plan_id
        GROUP BY p.plan_id
        ORDER BY sales_count DESC
        LIMIT 5
    """
    plans = _execute(query, fetchall=True)
    return [dict(plan) for plan in plans] if plans else []


# --- All other functions remain unchanged ---
def list_plans(): return [dict(plan) for plan in _execute("SELECT * FROM plans WHERE is_visible = 1", fetchall=True) or []]
def list_all_plans_admin(): return [dict(plan) for plan in _execute("SELECT * FROM plans", fetchall=True) or []]
def update_plan(plan_id, name, price, days, gb): return _execute("UPDATE plans SET name = ?, price = ?, days = ?, gb = ? WHERE plan_id = ?", (name, price, days, gb, plan_id), commit=True)
def toggle_plan_visibility(plan_id): return _execute("UPDATE plans SET is_visible = 1 - is_visible WHERE plan_id = ?", (plan_id,), commit=True)
def get_or_create_user(user_id, username=None):
    user = _execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        join_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _execute("INSERT INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, username, join_date), commit=True); return get_user(user_id)
    else:
        if user['username'] != username: _execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id), commit=True)
    return dict(user)
def get_user_by_username(username):
    if username.startswith('@'): username = username[1:]
    user = _execute("SELECT * FROM users WHERE username LIKE ?", (username,), fetchone=True); return dict(user) if user else None
def get_user_sales_history(user_id):
    query = "SELECT s.sale_date, s.price, p.name as plan_name FROM sales s LEFT JOIN plans p ON s.plan_id = p.plan_id WHERE s.user_id = ? ORDER BY s.sale_id DESC"
    history = _execute(query, (user_id,), fetchall=True); return [dict(row) for row in history] if history else []
def get_all_active_services(): return [dict(service) for service in _execute("SELECT * FROM active_services", fetchall=True) or []]
def set_low_usage_alert_sent(service_id, status=True): _execute("UPDATE active_services SET low_usage_alert_sent = ? WHERE service_id = ?", (1 if status else 0, service_id), commit=True)
def update_service_after_renewal(service_id, new_plan_id): now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"); return _execute("UPDATE active_services SET plan_id = ?, last_api_update = ?, low_usage_alert_sent = 0 WHERE service_id = ?", (new_plan_id, now_str, service_id), commit=True)
def add_active_service(user_id, name, sub_uuid, sub_link, plan_id): now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"); _execute("INSERT INTO active_services (user_id, name, sub_uuid, sub_link, last_api_update, plan_id) VALUES (?, ?, ?, ?, ?, ?)", (user_id, name, sub_uuid, sub_link, now_str, plan_id), commit=True)
def get_setting(key): result = _execute("SELECT value FROM settings WHERE key = ?", (key,), fetchone=True); return result['value'] if result else None
def set_setting(key, value): _execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value), commit=True)
def get_user(user_id): user = _execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True); return dict(user) if user else None
def get_all_user_ids(): users = _execute("SELECT user_id FROM users WHERE is_banned = 0", fetchall=True); return [user['user_id'] for user in users] if users else []
def set_user_ban_status(user_id, is_banned): _execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if is_banned else 0, user_id), commit=True)
def update_balance(user_id, amount): _execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id), commit=True)
def set_user_trial_used(user_id): _execute("UPDATE users SET has_used_trial = 1 WHERE user_id = ?", (user_id,), commit=True)
def add_plan(name, price, days, gb): _execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb), commit=True)
def get_plan(plan_id): plan = _execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,), fetchone=True); return dict(plan) if plan else None
def get_plan_by_gb_and_days(gb, days): plan = _execute("SELECT * FROM plans WHERE gb = ? AND days = ?", (gb, days), fetchone=True); return dict(plan) if plan else None
def delete_plan(plan_id): _execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,), commit=True)
def get_user_services(user_id): services = _execute("SELECT * FROM active_services WHERE user_id = ?", (user_id,), fetchall=True); return [dict(service) for service in services] if services else []
def get_service(service_id): service = _execute("SELECT * FROM active_services WHERE service_id = ?", (service_id,), fetchone=True); return dict(service) if service else None
def log_sale(user_id, plan_id, price): sale_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"); _execute("INSERT INTO sales (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)", (user_id, plan_id, price, sale_date), commit=True)
def get_stats():
    user_count_row = _execute("SELECT COUNT(user_id) as count FROM users", fetchone=True); sales_data_row = _execute("SELECT COUNT(sale_id) as count, SUM(price) as total FROM sales", fetchone=True)
    user_count = user_count_row['count'] if user_count_row else 0; sales_count = sales_data_row['count'] or 0; total_revenue = sales_data_row['total'] or 0.0
    return {"user_count": user_count, "sales_count": sales_count, "total_revenue": total_revenue}
def get_buyers_list(): buyers = _execute("SELECT DISTINCT user_id FROM sales", fetchall=True); return [buyer['user_id'] for buyer in buyers] if buyers else []
def create_gift_code(amount, usage_limit):
    code = str(uuid.uuid4().hex[:10]).upper()
    if _execute("INSERT INTO gift_codes (code, amount, usage_limit) VALUES (?, ?, ?)", (code, amount, usage_limit), commit=True): return code
    return None
def use_gift_code(code, user_id):
    gift = _execute("SELECT amount, usage_limit, used_count FROM gift_codes WHERE code = ?", (code,), fetchone=True)
    if gift and (gift['usage_limit'] == 0 or gift['used_count'] < gift['usage_limit']):
        amount = gift['amount']
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            cursor.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
            conn.commit()
        return amount
    return None
def list_gift_codes(): codes = _execute("SELECT * FROM gift_codes", fetchall=True); return [dict(code) for code in codes] if codes else []
def delete_gift_code(code): _execute("DELETE FROM gift_codes WHERE code = ?", (code,), commit=True)