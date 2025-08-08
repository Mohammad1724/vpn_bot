# -*- coding: utf-8 -*-

# database.py (نسخه کامل بازنویسی شده برای محیط ناهمزمان)

import logging
from datetime import datetime, timedelta
import aiosqlite  # <--- FIX: Using the async library

# --- Setup ---
DB_NAME = "vpn_bot.db"
logger = logging.getLogger(__name__)

# --- Async Helper for DB Connection ---
_db_connection = None

async def get_db_connection():
    """
    Creates and returns a single, shared async database connection.
    """
    global _db_connection
    if _db_connection is None:
        _db_connection = await aiosqlite.connect(DB_NAME)
        # Use Row factory to access columns by name (like a dictionary)
        _db_connection.row_factory = aiosqlite.Row
        logger.info("Database connection established.")
    return _db_connection

async def close_db():
    """Closes the database connection if it exists."""
    global _db_connection
    if _db_connection is not None:
        await _db_connection.close()
        _db_connection = None
        logger.info("Database connection closed.")

# --- Initialization ---
async def init_db():
    """Initializes the database schema."""
    conn = await get_db_connection()
    # Use 'async with' for automatic cursor management
    async with conn.cursor() as cursor:
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0, 
                join_date TEXT NOT NULL, is_banned INTEGER DEFAULT 0, 
                has_used_trial INTEGER DEFAULT 0, referred_by INTEGER,
                has_received_referral_bonus INTEGER DEFAULT 0
            )''')
        
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS plans (
                plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price REAL NOT NULL, 
                days INTEGER NOT NULL, gb INTEGER NOT NULL, is_visible INTEGER DEFAULT 1
            )''')

        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_services (
                service_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, 
                name TEXT, sub_uuid TEXT NOT NULL UNIQUE, sub_link TEXT NOT NULL, 
                plan_id INTEGER, created_at TEXT NOT NULL,
                low_usage_alert_sent INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(plan_id) REFERENCES plans(plan_id)
            )''')
        
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)
            ''')

    await conn.commit()
    logger.info("Database initialized successfully.")

# --- User Management ---
async def get_or_create_user(user_id: int, username: str = None) -> dict:
    conn = await get_db_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()

        if not user:
            join_date = 