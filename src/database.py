import sqlite3, datetime, uuid

DB_NAME = "vpn_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, join_date TEXT, is_banned INTEGER DEFAULT 0, has_used_trial INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS plans (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price REAL NOT NULL, days INTEGER NOT NULL, gb INTEGER NOT NULL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS active_services (service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, sub_uuid TEXT, sub_link TEXT, expiry_date TEXT, plan_id INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS sales (sale_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id INTEGER, price REAL, sale_date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS gift_codes (code TEXT PRIMARY KEY, amount REAL, usage_limit INTEGER, used_count INTEGER DEFAULT 0)')
    conn.commit()
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_holder', 'نام صاحب حساب'))
    conn.commit(); conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,)); result = cursor.fetchone()
    conn.close(); return result[0] if result else None
def set_setting(key, value):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)); conn.commit(); conn.close()

def get_or_create_user(user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance, is_banned, has_used_trial FROM users WHERE user_id = ?", (user_id,)); user = cursor.fetchone()
    if not user:
        join_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO users (user_id, join_date) VALUES (?, ?)", (user_id, join_date)); conn.commit()
        user = (user_id, 0.0, 0, 0)
    conn.close(); return {"user_id": user[0], "balance": user[1], "is_banned": bool(user[2]), "has_used_trial": bool(user[3])}
def get_user(user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance, join_date, is_banned, has_used_trial FROM users WHERE user_id = ?", (user_id,)); user = cursor.fetchone()
    conn.close(); 
    if not user: return None
    return {"user_id": user[0], "balance": user[1], "join_date": user[2], "is_banned": bool(user[3]), "has_used_trial": bool(user[4])}
def get_all_user_ids():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0"); user_ids = [item[0] for item in cursor.fetchall()]
    conn.close(); return user_ids
def set_user_ban_status(user_id, is_banned):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if is_banned else 0, user_id)); conn.commit(); conn.close()
def update_balance(user_id, amount, add=True):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    if add: cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    else: cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()
def set_user_trial_used(user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("UPDATE users SET has_used_trial = 1 WHERE user_id = ?", (user_id,)); conn.commit(); conn.close()

def add_plan(name, price, days, gb): conn = sqlite3.connect(DB_NAME); cursor = conn.cursor(); cursor.execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb)); conn.commit(); conn.close()
def list_plans(): conn = sqlite3.connect(DB_NAME); cursor = conn.cursor(); cursor.execute("SELECT plan_id, name, price, days, gb FROM plans"); plans = [{"plan_id": p[0], "name": p[1], "price": p[2], "days": p[3], "gb": p[4]} for p in cursor.fetchall()]; conn.close(); return plans
def get_plan(plan_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT plan_id, name, price, days, gb FROM plans WHERE plan_id = ?", (plan_id,)); p = cursor.fetchone()
    conn.close()
    if not p: return None
    return {"plan_id": p[0], "name": p[1], "price": p[2], "days": p[3], "gb": p[4]}
def delete_plan(plan_id): conn = sqlite3.connect(DB_NAME); cursor = conn.cursor(); cursor.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,)); conn.commit(); conn.close()

def add_active_service(user_id, sub_uuid, sub_link, plan_id, days):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    expiry_date = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO active_services (user_id, sub_uuid, sub_link, expiry_date, plan_id) VALUES (?, ?, ?, ?, ?)", (user_id, sub_uuid, sub_link, expiry_date, plan_id))
    conn.commit(); conn.close()
def get_user_services(user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT service_id, sub_uuid, sub_link, expiry_date, plan_id FROM active_services WHERE user_id = ?", (user_id,))
    services = [{"service_id": s[0], "sub_uuid": s[1], "sub_link": s[2], "expiry_date": s[3], "plan_id": s[4]} for s in cursor.fetchall()]
    conn.close(); return services
def get_services_expiring_soon(days=3):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    target_date = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("SELECT user_id, sub_link, expiry_date FROM active_services WHERE expiry_date = ?", (target_date,))
    services = cursor.fetchall()
    conn.close(); return [{"user_id": s[0], "sub_link": s[1], "expiry_date": s[2]} for s in services]
def renew_service(service_id, days):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT expiry_date FROM active_services WHERE service_id = ?", (service_id,)); current_expiry_str = cursor.fetchone()[0]
    current_expiry = datetime.datetime.strptime(current_expiry_str, "%Y-%m-%d")
    start_date = max(current_expiry, datetime.datetime.now())
    new_expiry_date = (start_date + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute("UPDATE active_services SET expiry_date = ? WHERE service_id = ?", (new_expiry_date, service_id)); conn.commit(); conn.close()
def get_service(service_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT service_id, user_id, sub_uuid, sub_link, expiry_date, plan_id FROM active_services WHERE service_id = ?", (service_id,)); s = cursor.fetchone()
    conn.close();
    if not s: return None
    return {"service_id": s[0], "user_id": s[1], "sub_uuid": s[2], "sub_link": s[3], "expiry_date": s[4], "plan_id": s[5]}

def log_sale(user_id, plan_id, price):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    sale_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO sales (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)", (user_id, plan_id, price, sale_date)); conn.commit(); conn.close()
def get_stats():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users"); user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(sale_id), SUM(price) FROM sales"); sales_data = cursor.fetchone()
    sales_count, total_revenue = (sales_data[0] or 0, sales_data[1] or 0)
    conn.close(); return {"user_count": user_count, "sales_count": sales_count, "total_revenue": total_revenue}

def create_gift_code(amount, usage_limit):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    code = str(uuid.uuid4().hex[:10]).upper()
    cursor.execute("INSERT INTO gift_codes (code, amount, usage_limit) VALUES (?, ?, ?)", (code, amount, usage_limit)); conn.commit(); conn.close()
    return code
def use_gift_code(code, user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT amount, usage_limit, used_count FROM gift_codes WHERE code = ?", (code,)); gift = cursor.fetchone()
    if gift and gift[1] > gift[2]:
        amount = gift[0]
        update_balance(user_id, amount, add=True)
        cursor.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code = ?", (code,)); conn.commit(); conn.close()
        return amount
    conn.close(); return None
def list_gift_codes():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT code, amount, usage_limit, used_count FROM gift_codes")
    codes = [{"code": g[0], "amount": g[1], "usage_limit": g[2], "used_count": g[3]} for g in cursor.fetchall()]
    conn.close(); return codes
def delete_gift_code(code): conn = sqlite3.connect(DB_NAME); cursor = conn.cursor(); cursor.execute("DELETE FROM gift_codes WHERE code = ?", (code,)); conn.commit(); conn.close()
