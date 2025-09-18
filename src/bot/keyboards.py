# filename: bot/keyboards.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Iterable, Set, List, Optional
from telegram import ReplyKeyboardMarkup

import re
import database as db

from config import ADMIN_ID
from bot.constants import BTN_ADMIN_PANEL, BTN_EXIT_ADMIN_PANEL

# فallback برای تریال از config (اگر تنظیم DB نبود)
try:
    from config import TRIAL_ENABLED as TRIAL_ENABLED_CFG
except Exception:
    TRIAL_ENABLED_CFG = False


def _is_on(val) -> bool:
    return str(val).strip().lower() in ("1", "true", "on", "yes")


def _trial_enabled_dynamic() -> bool:
    """
    تشخیص روشن/خاموش بودن دکمه سرویس تست:
    1) اگر کلید trial_enabled در settings موجود بود → از آن استفاده کن.
    2) اگر trial_days و trial_gb هر دو مثبت بودند → روشن در نظر بگیر.
    3) در غیر این صورت از config.TRIAL_ENABLED استفاده کن.
    """
    try:
        v = db.get_setting("trial_enabled")
        if v is not None:
            return _is_on(v)
    except Exception:
        pass

    try:
        td = int(float(db.get_setting("trial_days") or 0))
        tg = float(db.get_setting("trial_gb") or 0.0)
        if td > 0 and tg > 0:
            return True
    except Exception:
        pass

    return bool(TRIAL_ENABLED_CFG)


def _parse_admin_ids(raw) -> Set[int]:
    """
    ADMIN_ID می‌تواند:
      - عدد تکی (int)
      - رشتهٔ عدد (e.g. "123")
      - لیست/تاپل/ست از اعداد/رشته‌ها (e.g. [123, "456"])
      - رشتهٔ کاما/فاصله‌جدا (e.g. "123,456 789")
    """
    ids: Set[int] = set()
    if raw is None:
        return ids

    if isinstance(raw, (list, tuple, set)):
        for x in raw:
            try:
                ids.add(int(str(x).strip()))
            except Exception:
                continue
        return ids

    s = str(raw).strip()
    if s.isdigit():
        try:
            ids.add(int(s))
        except Exception:
            pass
        return ids

    # split by comma/space
    parts = [p for p in re.split(r"[,\s]+", s) if p]
    for p in parts:
        try:
            ids.add(int(p))
        except Exception:
            continue
    return ids


_ADMIN_IDS = _parse_admin_ids(ADMIN_ID)


def _is_admin(user_id: int) -> bool:
    if not _ADMIN_IDS:
        # اگر پیکربندی اشتباه است، به‌صورت محافظه‌کارانه فقط وقتی برابر بود نشان بده
        try:
            return user_id == int(ADMIN_ID)
        except Exception:
            return False
    return int(user_id) in _ADMIN_IDS


def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    منوی اصلی کاربر (ReplyKeyboard) — با چیدمان استاندارد
    """
    rows: List[List[str]] = [
        ["🛍️ خرید سرویس", "📋 سرویس‌های من"],
        ["💳 شارژ حساب"],
    ]

    # ردیف اطلاعات + یکی از (سرویس تست | کد هدیه)
    if _trial_enabled_dynamic():
        rows.append(["👤 اطلاعات حساب کاربری", "🧪 سرویس تست"])
    else:
        rows.append(["👤 اطلاعات حساب کاربری", "🎁 کد هدیه"])

    # ردیف راهنما/پشتیبانی
    rows.append(["📚 راهنما", "📞 پشتیبانی"])

    # دکمه پنل ادمین برای ادمین‌ها
    if _is_admin(user_id):
        rows.append([BTN_ADMIN_PANEL])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    منوی اصلی پنل ادمین (ReplyKeyboard) — چیدمان مرتب و دو ستونه
    """
    rows = [
        ["👥 مدیریت کاربران", "➕ مدیریت پلن‌ها"],
        ["📈 گزارش‌ها و آمار", "🎁 مدیریت کد هدیه"],
        ["💾 پشتیبان‌گیری", "⚙️ تنظیمات"],
        ["📩 ارسال پیام", "🛑 خاموش کردن ربات"],
        [BTN_EXIT_ADMIN_PANEL],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def get_settings_keyboard() -> ReplyKeyboardMarkup:
    """
    (اختیاری) نمونه کیبورد تنظیمات — اگر جایی استفاده شود.
    """
    rows = [
        ["⚙️ تنظیمات عمومی", "🛠️ تنظیمات پیشرفته"],
        ["🌐 تنظیمات سرور", "🧪 تنظیمات سرویس تست"],
        [BTN_EXIT_ADMIN_PANEL],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def get_yes_no_keyboard() -> ReplyKeyboardMarkup:
    """
    صفحه کلید بله/خیر برای پرسش‌های ساده.
    """
    return ReplyKeyboardMarkup([["بله", "خیر"]], resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    صفحه کلید با دکمه لغو برای عملیات‌های در حال انجام.
    """
    return ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)