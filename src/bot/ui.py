# filename: bot/ui.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Sequence, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# متن‌های یکسان و شیک (سراسری)
BACK_TEXT = "↩️ بازگشت"
HOME_TEXT = "☰ منوی اصلی"
YES_TEXT = "✅ تایید"
NO_TEXT   = "❌ انصراف"

# ------------- ساخت دکمه/مارکاپ -------------

def btn(text: str, cb_data: Optional[str] = None, url: Optional[str] = None) -> InlineKeyboardButton:
    """
    سازنده دکمه اینلاین یکدست.
    - یا callback_data بده (cb_data) یا url
    """
    if cb_data is not None:
        return InlineKeyboardButton(text, callback_data=cb_data)
    if url is not None:
        return InlineKeyboardButton(text, url=url)
    raise ValueError("btn requires either cb_data or url")

def row(*buttons: InlineKeyboardButton) -> List[InlineKeyboardButton]:
    return list(buttons)

def markup(rows: Sequence[Sequence[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)

def chunk(buttons: Sequence[InlineKeyboardButton], cols: int = 2) -> List[List[InlineKeyboardButton]]:
    """
    چیدن دکمه‌ها بصورت شبکه‌ای یکدست (۲ ستونه پیش‌فرض)
    """
    cols = max(1, int(cols or 1))
    rows: List[List[InlineKeyboardButton]] = []
    cur: List[InlineKeyboardButton] = []
    for b in buttons:
        cur.append(b)
        if len(cur) == cols:
            rows.append(cur)
            cur = []
    if cur:
        rows.append(cur)
    return rows

# ------------- دکمه‌های ناوبری استاندارد -------------

def back_button(callback_data: str, text: Optional[str] = None) -> InlineKeyboardButton:
    return btn(text or BACK_TEXT, cb_data=callback_data)

def home_button(callback_data: str = "home_menu", text: Optional[str] = None) -> InlineKeyboardButton:
    return btn(text or HOME_TEXT, cb_data=callback_data)

def back_row(back_cb: str, back_text: Optional[str] = None) -> List[InlineKeyboardButton]:
    return [back_button(back_cb, text=back_text)]

def home_row(home_cb: str = "home_menu", home_text: Optional[str] = None) -> List[InlineKeyboardButton]:
    return [home_button(home_cb, text=home_text)]

def back_home_row(back_cb: str, home_cb: str = "home_menu",
                  back_text: Optional[str] = None, home_text: Optional[str] = None) -> List[InlineKeyboardButton]:
    return [back_button(back_cb, text=back_text), home_button(home_cb, text=home_text)]

def nav_row(back_cb: Optional[str] = None, home_cb: str = "home_menu",
            back_text: Optional[str] = None, home_text: Optional[str] = None) -> List[InlineKeyboardButton]:
    """
    ردیف ناوبری یکدست:
    - اگر back_cb داده شود: ↩️ بازگشت
    - همیشه: ☰ منوی اصلی (home_cb)
    نکته: می‌تونی متن‌ها رو سفارشی هم بدی، ولی برای یکدستی بهتره پیش‌فرض‌ها رو نگه داری.
    """
    if back_cb:
        return [back_button(back_cb, text=back_text), home_button(home_cb, text=home_text)]
    return [home_button(home_cb, text=home_text)]

# ------------- تایید/انصراف یکدست -------------

def confirm_row(yes_cb: str, no_cb: str,
                yes_text: str = YES_TEXT, no_text: str = NO_TEXT) -> List[InlineKeyboardButton]:
    return [btn(yes_text, cb_data=yes_cb), btn(no_text, cb_data=no_cb)]