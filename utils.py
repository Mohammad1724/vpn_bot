# -*- coding: utf-8 -*-
import logging
import sqlite3
import jdatetime
from datetime import datetime, timedelta
from typing import Union, Tuple

logger = logging.getLogger(__name__)

def parse_date_flexible(date_str: str) -> Union[datetime.date, None]:
    """
    Parses a date string with multiple possible formats.
    """
    if not date_str:
        return None
    date_part = date_str.split('T')[0]
    formats_to_try = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
    for fmt in formats_to_try:
        try:
            return datetime.strptime(date_part, fmt).date()
        except (ValueError, TypeError):
            continue
    logger.error(f"Could not parse date string '{date_str}' with any known format.")
    return None

async def get_service_status_and_expiry(hiddify_info: dict) -> Tuple[str, str, bool]:
    """
    Calculates the service status, expiry date, and whether it's expired
    based on Hiddify user info.
    Returns: (status_str, expiry_date_str, is_expired_bool)
    """
    date_keys = ['start_date', 'last_reset_time', 'created_at']
    start_date_str = next((hiddify_info.get(key) for key in date_keys if hiddify_info.get(key)), None)
    package_days = hiddify_info.get('package_days', 0)

    if not start_date_str:
        logger.warning(f"Could not find a valid date key in Hiddify info: {hiddify_info}")
        return "⚠️ وضعیت نامشخص", "N/A", True

    start_date_obj = parse_date_flexible(start_date_str)
    if not start_date_obj:
        return "⚠️ وضعیت نامشخص", "N/A", True

    expiry_date_obj = start_date_obj + timedelta(days=package_days)
    jalali_expiry_date = jdatetime.date.fromgregorian(date=expiry_date_obj)
    jalali_display_str = jalali_expiry_date.strftime("%Y/%m/%d")

    is_expired = expiry_date_obj < datetime.now().date()
    status = "🔴 منقضی شده" if is_expired else "🟢 فعال"

    return status, jalali_display_str, is_expired

def is_valid_sqlite(filepath: str) -> bool:
    """
    Checks if a given file is a valid SQLite3 database.
    """
    # This function remains synchronous as it's a quick check
    # and not suitable for asyncio.to_thread in this context.
    try:
        with sqlite3.connect(filepath) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
        return result[0] == 'ok'
    except sqlite3.DatabaseError:
        return False
