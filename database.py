# -*- coding: utf-8 -*-
import aiosqlite
import logging
from datetime import datetime
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)
DB_NAME = "bot_database.db"
_db_connection = None

# A helper to convert row objects to dictionaries
def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

async def get_db_connection():
    global _db_connection
    if _db_connection is None:
        _db_connection = await aiosqlite.connect(DB_NAME)
        _db_connection.row_factory = _dict_factory
    return _db_connection

async def close_db():
    global _db_connection
    if _db_connection:
        await _db_connection.close()
        _db_connection = None
        logger.info("Database connection closed.")

async def init_db():
    # Use a separate connection for initialization
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, join_date TEXT,
                balance REAL DEFAULT 0, is_banned INTEGER DEFAULT 0,
                has_used_trial INTEGER DEFAULT 0, referrer_id INTEGER,
                referral_bonus_applied INTEGER DEFAULT 0 )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS plans (
                plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL,
                days INTEGER, gb INTEGER, is_visible INTEGER DEFAULT 1 )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS active_services (
                service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_id INTEGER,
                name TEXT, sub_uuid TEXT UNIQUE, sub_link TEXT, purchase_date TEXT,
                low_usage_alert_sent INTEGER DEFAULT 0 )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sales_history (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                plan_id INTEGER, price REAL, sale_date TEXT )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS gift_codes (
                code TEXT PRIMARY KEY, amount REAL, is_used INTEGER DEFAULT 0,
                used_by_user_id INTEGER, used_date TEXT )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings ( key TEXT PRIMARY KEY, value TEXT )
        ''')
        await db.commit()
    logger.info("Database initialized successfully.")

# --- User Management ---
async def get_or_create_user(user_id: int, username: str = None) -> Dict[str, Any]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
        user = await cursor.fetchone()
    if not user:
        join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "INSERT INTO users (user_id, username, join_date) VALUES (?, ?, ?)",
            (user_id, username, join_date)
        )
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
    return user

async def get_user(user_id: int) -> Union[Dict[str, Any], None]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
        return await cursor.fetchone()

async def get_user_by_username(username: str) -> Union[Dict[str, Any], None]:
    db = await get_db_connection()
    username = username.lstrip('@')
    async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cursor:
        return await cursor.fetchone()

async def update_balance(user_id: int, amount_change: float):
    db = await get_db_connection()
    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount_change, user_id))
    await db.commit()

async def set_user_ban_status(user_id: int, is_banned: bool):
    db = await get_db_connection()
    await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if is_banned else 0, user_id))
    await db.commit()
    
async def set_user_trial_used(user_id: int):
    db = await get_db_connection()
    await db.execute("UPDATE users SET has_used_trial = 1 WHERE user_id = ?", (user_id,))
    await db.commit()

async def get_all_user_ids() -> List[int]:
    db = await get_db_connection()
    async with db.execute("SELECT user_id FROM users WHERE is_banned = 0") as cursor:
        rows = await cursor.fetchall()
    return [row['user_id'] for row in rows]
    
async def set_referrer(user_id: int, referrer_id: int):
    db = await get_db_connection()
    # Only set referrer if the user doesn't have one and hasn't made a purchase
    # (This logic might need adjustment based on exact requirements)
    user = await get_user(user_id)
    if user and not user.get('referrer_id'):
        await db.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, user_id))
        await db.commit()

async def apply_referral_bonus(user_id: int) -> Tuple[Union[int, None], float]:
    from config import REFERRAL_BONUS_AMOUNT
    db = await get_db_connection()
    user = await get_user(user_id)
    
    if not user or user.get('referral_bonus_applied') or not user.get('referrer_id'):
        return None, 0

    referrer_id = user['referrer_id']
    bonus_amount = float((await get_setting('referral_bonus_amount')) or REFERRAL_BONUS_AMOUNT)

    # Apply bonus to new user and referrer
    await update_balance(user_id, bonus_amount)
    await update_balance(referrer_id, bonus_amount)

    # Mark as applied for the new user
    await db.execute("UPDATE users SET referral_bonus_applied = 1 WHERE user_id = ?", (user_id,))
    await db.commit()
    
    return referrer_id, bonus_amount

# --- Plan Management ---
async def add_plan(name: str, price: float, days: int, gb: int):
    db = await get_db_connection()
    await db.execute("INSERT INTO plans (name, price, days, gb) VALUES (?, ?, ?, ?)", (name, price, days, gb))
    await db.commit()

async def list_plans(only_visible: bool = False) -> List[Dict[str, Any]]:
    db = await get_db_connection()
    query = "SELECT * FROM plans ORDER BY price"
    if only_visible:
        query = "SELECT * FROM plans WHERE is_visible = 1 ORDER BY price"
    async with db.execute(query) as cursor:
        return await cursor.fetchall()

async def get_plan(plan_id: int) -> Union[Dict[str, Any], None]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,)) as cursor:
        return await cursor.fetchone()

async def update_plan(plan_id: int, new_data: Dict[str, Any]):
    db = await get_db_connection()
    fields = []
    values = []
    for key, value in new_data.items():
        if key in ['name', 'price', 'days', 'gb']:
            fields.append(f"{key} = ?")
            values.append(value)
    if not fields:
        return
    values.append(plan_id)
    query = f"UPDATE plans SET {', '.join(fields)} WHERE plan_id = ?"
    await db.execute(query, tuple(values))
    await db.commit()

async def delete_plan(plan_id: int):
    db = await get_db_connection()
    await db.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
    await db.commit()

async def toggle_plan_visibility(plan_id: int):
    db = await get_db_connection()
    await db.execute("UPDATE plans SET is_visible = 1 - is_visible WHERE plan_id = ?", (plan_id,))
    await db.commit()

# --- Service & Sales Management ---
async def get_user_services(user_id: int) -> List[Dict[str, Any]]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM active_services WHERE user_id = ? ORDER BY service_id DESC", (user_id,)) as cursor:
        return await cursor.fetchall()

async def get_service(service_id: int) -> Union[Dict[str, Any], None]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM active_services WHERE service_id = ?", (service_id,)) as cursor:
        return await cursor.fetchone()
        
async def get_service_by_uuid(uuid: str) -> Union[Dict[str, Any], None]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM active_services WHERE sub_uuid = ?", (uuid,)) as cursor:
        return await cursor.fetchone()

async def add_active_service(user_id: int, name: str, sub_uuid: str, sub_link: str, plan_id: int) -> Dict[str, Any]:
    db = await get_db_connection()
    purchase_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = await db.execute(
        "INSERT INTO active_services (user_id, name, sub_uuid, sub_link, plan_id, purchase_date) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name, sub_uuid, sub_link, plan_id, purchase_date)
    )
    await db.commit()
    service_id = cursor.lastrowid
    return await get_service(service_id)

async def get_user_purchase_stats(user_id: int) -> Dict[str, Any]:
    db = await get_db_connection()
    async with db.execute("SELECT COUNT(*) as total_purchases, SUM(price) as total_spent FROM sales_history WHERE user_id = ?", (user_id,)) as cursor:
        stats = await cursor.fetchone()
    return stats or {'total_purchases': 0, 'total_spent': 0}

async def get_user_sales_history(user_id: int) -> List[Dict[str, Any]]:
    db = await get_db_connection()
    query = """
        SELECT sh.*, p.name as plan_name FROM sales_history sh
        LEFT JOIN plans p ON sh.plan_id = p.plan_id
        WHERE sh.user_id = ? ORDER BY sh.sale_date DESC
    """
    async with db.execute(query, (user_id,)) as cursor:
        return await cursor.fetchall()

# --- Transaction Management ---
async def initiate_purchase_transaction(user_id: int, plan_id: int) -> Union[int, None]:
    db = await get_db_connection()
    user = await get_user(user_id)
    plan = await get_plan(plan_id)
    if not user or not plan or user['balance'] < plan['price']:
        return None
    
    sale_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await update_balance(user_id, -plan['price'])
    cursor = await db.execute("INSERT INTO sales_history (user_id, plan_id, price, sale_date) VALUES (?, ?, ?, ?)",
                      (user_id, plan_id, plan['price'], sale_date))
    await db.commit()
    return cursor.lastrowid

async def finalize_purchase_transaction(sale_id: int, sub_uuid: str, sub_link: str, custom_name: str) -> Dict[str, Any]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM sales_history WHERE sale_id = ?", (sale_id,)) as cursor:
        sale = await cursor.fetchone()
    return await add_active_service(sale['user_id'], custom_name, sub_uuid, sub_link, sale['plan_id'])

async def cancel_purchase_transaction(sale_id: int):
    db = await get_db_connection()
    async with db.execute("SELECT * FROM sales_history WHERE sale_id = ?", (sale_id,)) as cursor:
        sale = await cursor.fetchone()
    if sale:
        await update_balance(sale['user_id'], sale['price'])
        await db.execute("DELETE FROM sales_history WHERE sale_id = ?", (sale_id,))
        await db.commit()
        
async def initiate_renewal_transaction(user_id: int, service_id: int, plan_id: int) -> Union[int, None]:
    # This is identical to a new purchase transaction in terms of finance
    return await initiate_purchase_transaction(user_id, plan_id)

async def finalize_renewal_transaction(sale_id: int, new_plan_id: int):
    # We only need to mark low_usage_alert as not sent for the renewed service
    db = await get_db_connection()
    async with db.execute("SELECT * FROM sales_history WHERE sale_id = ?", (sale_id,)) as cursor:
        sale = await cursor.fetchone()
    async with db.execute("SELECT * FROM active_services WHERE user_id = ? AND plan_id = ?", (sale['user_id'], sale['plan_id'])) as cursor:
        service = await cursor.fetchone() # This logic may need to be more robust if user has multiple identical services
    if service:
        await db.execute("UPDATE active_services SET low_usage_alert_sent = 0, plan_id = ? WHERE service_id = ?", (new_plan_id, service['service_id']))
        await db.commit()

async def cancel_renewal_transaction(sale_id: int):
    await cancel_purchase_transaction(sale_id)

# --- Gift Codes ---
async def use_gift_code(code: str, user_id: int) -> Union[float, None]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM gift_codes WHERE code = ? AND is_used = 0", (code.upper(),)) as cursor:
        gift = await cursor.fetchone()
    if not gift:
        return None
    
    amount = gift['amount']
    await update_balance(user_id, amount)
    
    used_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute("UPDATE gift_codes SET is_used = 1, used_by_user_id = ?, used_date = ? WHERE code = ?",
                   (user_id, used_date, code.upper()))
    await db.commit()
    return amount
    
# --- Settings ---
async def get_setting(key: str) -> Union[str, None]:
    db = await get_db_connection()
    async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
    return row['value'] if row else None

async def set_setting(key: str, value: str):
    db = await get_db_connection()
    await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    await db.commit()

# --- Reports & Stats ---
async def get_stats() -> Dict[str, Any]:
    db = await get_db_connection()
    async with db.execute("SELECT COUNT(*) as cnt FROM users") as c: total_users = (await c.fetchone())['cnt']
    async with db.execute("SELECT COUNT(*) as cnt FROM active_services") as c: active_services = (await c.fetchone())['cnt']
    async with db.execute("SELECT SUM(price) as total FROM sales_history") as c: total_revenue = (await c.fetchone())['total']
    async with db.execute("SELECT COUNT(*) as cnt FROM users WHERE is_banned = 1") as c: banned_users = (await c.fetchone())['cnt']
    return {
        'total_users': total_users, 'active_services': active_services,
        'total_revenue': total_revenue or 0, 'banned_users': banned_users
    }

async def get_sales_report(days: int) -> List[Dict[str, Any]]:
    db = await get_db_connection()
    date_threshold = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    async with db.execute("SELECT * FROM sales_history WHERE sale_date >= ?", (date_threshold,)) as cursor:
        return await cursor.fetchall()

async def get_popular_plans(limit: int = 5) -> List[Dict[str, Any]]:
    db = await get_db_connection()
    query = """
        SELECT p.name, COUNT(sh.plan_id) as sales_count
        FROM sales_history sh
        JOIN plans p ON sh.plan_id = p.plan_id
        GROUP BY sh.plan_id
        ORDER BY sales_count DESC
        LIMIT ?
    """
    async with db.execute(query, (limit,)) as cursor:
        return await cursor.fetchall()

# --- Background Jobs related ---
async def get_all_active_services() -> List[Dict[str, Any]]:
    db = await get_db_connection()
    async with db.execute("SELECT * FROM active_services") as cursor:
        return await cursor.fetchall()

async def set_low_usage_alert_sent(service_id: int):
    db = await get_db_connection()
    await db.execute("UPDATE active_services SET low_usage_alert_sent = 1 WHERE service_id = ?", (service_id,))
    await db.commit()
