# filename: bot/handlers/common_handlers.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import logging
from functools import wraps
from typing import Callable, Awaitable, Optional, Tuple

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.error import BadRequest, Forbidden
from telegram.constants import ChatMemberStatus

import database as db

logger = logging.getLogger(__name__)


def _get_bool_setting(key: str, default: bool = False) -> bool:
    v = db.get_setting(key)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "on", "yes")


def _parse_force_join_target(raw: str | None) -> Tuple[Optional[str], Optional[str]]:
    """
    ورودی: مقدار تنظیم force_join_channel
    پشتیبانی:
      - @username
      - -100XXXXXXXXXX (شناسه عددی)
      - t.me/username یا https://t.me/username
      - t.me/+inviteCode (فقط برای دکمه Join؛ برای چک عضویت باید Bot ادمین باشد و chat_id درست ست شود)
    خروجی:
      (chat_id, join_url)
      - chat_id: یکی از @username یا -100... ، اگر نتوانستیم تشخیص دهیم: None
      - join_url: لینکی که در دکمه «عضویت» استفاده می‌شود
    """
    if not raw:
        return None, None

    s = raw.strip()
    # numeric chat id
    if re.match(r"^-100\d{10,}$", s):
        return s, None  # برای دکمه join نمی‌توان URL ساخت؛ باید admin لینکش را بدهد

    # @username
    if s.startswith("@"):
        uname = s[1:]
        return s, f"https://t.me/{uname}"

    # t.me/...
    if s.startswith("http://") or s.startswith("https://") or s.startswith("t.me/"):
        # normalize
        if s.startswith("t.me/"):
            join_url = "https://" + s
        else:
            join_url = s
        try:
            # t.me/username
            m = re.search(r"t\.me/(@?)([A-Za-z0-9_]{5,})", join_url)
            if m:
                uname = m.group(2)
                return f"@{uname}", join_url
            # t.me/+inviteCode → chat_id نامشخص؛ فقط join_url
            if "t.me/+" in join_url or "/joinchat/" in join_url:
                return None, join_url
        except Exception:
            pass
        return None, join_url

    # fallback: شاید فقط username بدون @ وارد شده
    if re.match(r"^[A-Za-z0-9_]{5,}$", s):
        return f"@{s}", f"https://t.me/{s}"

    return None, None


async def _is_user_member(context: ContextTypes.DEFAULT_TYPE, chat_id: str | int, user_id: int) -> bool:
    """
    چک عضویت کاربر:
      - True اگر status در {creator, administrator, member} یا ChatMemberRestricted با is_member=True
      - False در غیر این صورت
    نکات:
      - برای کانال خصوصی، Bot باید ادمین باشد؛ در غیر این صورت ممکن است Forbidden/BadRequest بدهد.
    """
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        status = getattr(member, "status", None)
        # PTB v20: status رشته است؛ ChatMemberRestricted دارای is_member
        if status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER):
            return True
        # Restricted ولی عضو است
        if status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False):
            return True
        return False
    except Forbidden as e:
        # Bot دسترسی ندارد (برای کانال خصوصی باید ادمین شود)
        logger.warning("get_chat_member Forbidden for chat_id=%s: %s", chat_id, e)
        return False
    except BadRequest as e:
        # مثال: chat not found یا user not found
        logger.warning("get_chat_member BadRequest for chat_id=%s: %s", chat_id, e)
        return False
    except Exception as e:
        logger.error("get_chat_member unexpected for chat_id=%s: %s", chat_id, e, exc_info=True)
        return False


def _join_prompt_markup(join_url: Optional[str] = None) -> InlineKeyboardMarkup:
    rows = []
    if join_url:
        rows.append([InlineKeyboardButton("🔗 عضویت در کانال", url=join_url)])
    rows.append([InlineKeyboardButton("✅ بررسی مجدد عضویت", callback_data="check_membership")])
    return InlineKeyboardMarkup(rows)


async def _send_force_join_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, join_url: Optional[str]):
    text = (
        "برای استفاده از ربات، باید عضو کانال شوید.\n\n"
        "1) روی «عضویت در کانال» بزنید و عضو شوید.\n"
        "2) چند ثانیه صبر کنید، سپس «بررسی مجدد عضویت» را بزنید.\n\n"
        "اگر کانال خصوصی است، مطمئن شوید ربات در کانال ادمین است."
    )
    kb = _join_prompt_markup(join_url)
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text=text, reply_markup=kb)
        except BadRequest:
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb)
    else:
        await update.effective_message.reply_text(text=text, reply_markup=kb)


def check_channel_membership(handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]):
    """
    دکوراتور چک عضویت کانال.
    - اگر force_join_enabled خاموش بود: عبور.
    - اگر روشن بود: عضویت کاربر در کانال config/setting چک می‌شود.
      پشتیبانی از @username، -100..., یا t.me/username (برای دکمه Join).
    """
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            # خاموش؟
            if not _get_bool_setting("force_join_enabled", False):
                return await handler(update, context)

            # کانال تنظیم نشده؟
            raw = db.get_setting("force_join_channel")
            chat_id, join_url = _parse_force_join_target(raw)
            if not raw:
                # چیزی تنظیم نشده؛ اجازه ورود بده ولی لاگ کن
                logger.warning("force_join_enabled is ON but force_join_channel is empty.")
                return await handler(update, context)

            # بدون chat_id نمی‌توان چک کرد (مثلا invite link خصوصی) → دکمه Join بده
            if chat_id is None:
                await _send_force_join_prompt(update, context, join_url)
                return

            user_id = update.effective_user.id if update.effective_user else None
            if not user_id:
                return  # آپدیت نامعتبر

            is_member = await _is_user_member(context, chat_id, user_id)
            if is_member:
                return await handler(update, context)

            # عضو نیست → پیام راهنما
            await _send_force_join_prompt(update, context, join_url)

        except Exception as e:
            logger.error("check_channel_membership failed: %s", e, exc_info=True)
            # در صورت خطا، بهتر است کاربر را بلاک نکنیم
            return await handler(update, context)

    return wrapper