import sqlite3
import datetime
import uuid

DB_NAME = "vpn_bot.db"

def _execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    """A helper function to manage database connections and execution."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row  # Makes the output dict-like
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if commit:
                conn.commit()
                return True
                
            if fetchone:
                return cursor.fetchone()
                
            if fetchall:
                return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error: {e}") # This should be logged properly in a real app
        return None if fetchone or fetchall else False


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Use TEXT for dates to keep it simple and human-readable.
    # Use INTEGER for boolean flags (0 for False, 1 for True).
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY, 
                        balance REAL DEFAULT 0.0, 
                        join_date TEXT, 
                        is_banned INTEGER DEFAULT 0, 
                        has_used_trial INTEGER DEFAULT 0
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans (
                        plan_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        name TEXT NOT NULL, 
                        price REAL NOT NULL, 
                        days INTEGER NOT NULL, 
                        gb INTEGER NOT NULL
                    )''')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS active_services (
                        service_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        user_id INTEGER NOT NULL, 
                        sub_uuid TEXT NOT NULL, 
                        sub_link TEXT NOT NULL, 
                        expiry_date TEXT NOT NULL, 
                        plan_id INTEGER
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales (
                        sale_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        user_id INTEGER NOT NULL, 
                        plan_id INTEGER NOT NULL, 
                        price REAL NOT NULL, 
                        sale_date TEXT NOT NULL
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS gift_codes (
                        code TEXT PRIMARY KEY, 
                        amount REAL NOT NULL, 
                        usage_limit INTEGER NOT NULL, 
                        used_count INTEGER DEFAULT 0
                    )''')
    conn.commit()
    # --- Initial Settings ---
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_number', '0000-0000-0000-0000'))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('card_holder', 'نام صاحب حساب'))
    conn.commit()
    conn.close()

# --- Settings ---
def get_setting(key):
    result = _execute("SELECT value FROM settings WHERE key = ?", (key,), fetchone=True)
    return result['value'] if result else None

def set_setting(key, value):
    _execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value), commit=True)

# --- User Management ---
def get_or_create_user(user_id):
    user = _execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if not user:
        join_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _execute("INSERT INTO users (user_id, join_date) VALUES (?, ?)", (user_id, join_date), commit=True)
        return get_user(user_id) # Recursively call to get the newly created user as a dict
    # Convert Row object to a dictionary for easier use in bot.py
    return dict(user)

def get_user(user_id):
    user = _execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return dict(user) if user else None

def get_all_user_ids():
    users = _execute("SELECT user_id FROM users WHERE is_banned = 0", fetchall=True)
    return [user['user_id'] for user in users] if users else []

def set_user_ban_status(user_id, is_banned):
    _execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if is_banned else 0, user_id), commit=True)

def update_balance(user_id, amount):
    # Use a single parameter for amount, positive to add, negative to subtract
    _execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id), commit=True)

def set_user_trial_used(user_id):
    _execute("UPDATE users SET has_used_trial = 1 WHERE user_id = ?", (user_id,), commit=True)

# --- Plan Management ---
def add_plan(name, price, days, gb):
    _execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb), commit=True)

def list_plans():
    plans = _execute("SELECT * FROM plans", fetchall=True)
    return [dict(plan) for plan in plans] if plans else []

def get_plan(plan_id):
    plan = _execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,), fetchone=True)
    return dict(plan) if plan else None

def delete_plan(plan_id):
    _execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,), commit=True)

# --- Service Management ---
def add_active_service(user_id, sub_uuid, sub_link, plan_id, days):
    expiry_date = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    _execute("INSERT INTO active_services (user_id, sub_uuid, sub_link, expiry_date, plan_id) VALUES (?, ?, ?, ?, ?)",
             (user_id, sub_uuid, sub_link, expiry_date, plan_id), commit=True)

def get_user_services(user_id):
    services = _execute("SELECT * FROM active_services WHERE user_id = ?", (user_id,), fetchall=True)
    return [dict(service) for service in services] if services else []

def get_services_expiring_soon(days=3):
    target_date = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    # Using LIKE to only match the date part
    services = _execute("SELECT user_id, sub_link, expiry_date FROM active_services WHERE expiry_date LIKE ?", (f"{target_date}%",), fetchall=True)
    return [dict(service) for service in services] if services else []

def renew_service(service_id, days_to_add):
    service = get_service(service_id)
    if not service:
        return False
        
    current_expiry = datetime.datetime.strptime(service['expiry_date'], "%Y-%m-%d %H:%M:%S")
    
    # If the service has already expired, start the new period from today.
    # Otherwise, add to the existing expiry date. This is a business logic choice.
    start_date = max(current_expiry, datetime.datetime.now())
    
    new_expiry_date = (start_date + datetime.timedelta(days=days_to_add)).strftime("%Y-%m-%d %H:%M:%S")
    return _execute("UPDATE active_services SET expiry_date = ? WHERE service_id = ?", (new_expiry_date, service_id), commit=True)

def get_service(service_id):
    service = _execute("SELECT * FROM active_services WHERE service_id = ?", (service_id,), fetchone=True)
    return dict(service) if service else None

# --- Analytics & Sales ---
def log_sale(user_id, plan_id, price):
    sale_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _execute("INSERT INTO sales (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)",
             (user_id, plan_id, price, sale_date), commit=True)

def get_stats():
    user_count_row = _execute("SELECT COUNT(user_id) as count FROM users", fetchone=True)
    sales_data_row = _execute("SELECT COUNT(sale_id) as count, SUM(price) as total FROM sales", fetchone=True)
    
    user_count = user_count_row['count'] if user_count_row else 0
    sales_count = sales_data_row['count'] or 0
    total_revenue = sales_data_row['total'] or 0.0
    
    return {"user_count": user_count, "sales_count": sales_count, "total_revenue": total_revenue}

def get_buyers_list():
    buyers = _execute("SELECT DISTINCT user_id FROM sales", fetchall=True)
    return [buyer['user_id'] for buyer in buyers] if buyers else []

# --- Gift Code Management ---
def create_gift_code(amount, usage_limit):
    code = str(uuid.uuid4().hex[:10]).upper()
    if _execute("INSERT INTO gift_codes (code, amount, usage_limit) VALUES (?, ?, ?)", (code, amount, usage_limit), commit=True):
        return code
    return None

def use_gift_code(code, user_id):
    gift = _execute("SELECT amount, usage_limit, used_count FROM gift_codes WHERE code = ?", (code,), fetchone=True)
    
    if gift:
        # Check if the gift code is valid for use
        # usage_limit = 0 means infinite
        if gift['usage_limit'] == 0 or gift['used_count'] < gift['usage_limit']:
            amount = gift['amount']
            # Use a transaction to ensure both operations succeed or fail together
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
                cursor.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
                conn.commit()
            return amount
    return None

def list_gift_codes():
    codes = _execute("SELECT * FROM gift_codes", fetchall=True)
    return [dict(code) for code in codes] if codes else []

def delete_gift_code(code):
    _execute("DELETE FROM gift_codes WHERE code = ?", (code,), commit=True)