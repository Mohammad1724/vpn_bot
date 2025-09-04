# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Sequence, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# متن‌های یکسان و شیک
BACK_TEXT = "↩️ بازگشت"
HOME_TEXT = "☰ منوی اصلی"
YES_TEXT = "✅ تایید"
NO_TEXT = "❌ انصراف"

def btn(text: str, cb_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=cb_data)

def row(*buttons: InlineKeyboardButton) -> List[InlineKeyboardButton]:
    return list(buttons)

def markup(rows: Sequence[Sequence[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)

def nav_row(back_cb: str | None = None, home_cb: str = "home_menu") -> List[InlineKeyboardButton]:
    """
    دکمه‌های ناوبری استاندارد:
    - اگر back_cb داده شود: «↩️ بازگشت»
    - همیشه: «☰ منوی اصلی» (به callback 'home_menu')
    """
    r: List[InlineKeyboardButton] = []
    if back_cb:
        r.append(btn(BACK_TEXT, back_cb))
    r.append(btn(HOME_TEXT, home_cb))
    return r

def confirm_row(yes_cb: str, no_cb: str) -> List[InlineKeyboardButton]:
    return [btn(YES_TEXT, yes_cb), btn(NO_TEXT, no_cb)]

def chunk(buttons: Sequence[InlineKeyboardButton], cols: int = 2) -> List[List[InlineKeyboardButton]]:
    """
    چیدن دکمه‌ها بصورت شبکه‌ای یکدست (۲ ستونه پیش‌فرض)
    """
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