# -*- coding: utf-8 -*-

from functools import wraps
import logging
import re
from datetime import datetime, timedelta
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
import database as db
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# کش ساده برای کاهش فراخوانی‌های get_chat_member
_MEMBERSHIP_CACHE: dict[tuple[int, str], tuple[bool, datetime]] = {}
_CACHE_TTL = timedelta(minutes=10)

def _cache_get(user_id: int, channel_key: str) -> tuple[bool, bool]:
    key = (user_id, channel_key)
    data = _MEMBERSHIP_CACHE.get(key)
    if not data:
        return False, False
    ok, exp = data
    if datetime.now() > exp:
        _MEMBERSHIP_CACHE.pop(key, None)
        return False, False
    return True, ok

def _cache_set(user_id: int, channel_key: str, is_member: bool, ttl: timedelta = _CACHE_TTL):
    _MEMBERSHIP_CACHE[(user_id, channel_key)] = (is_member, datetime.now() + ttl)

def _is_enabled() -> bool:
    # پشتیبانی از هر دو کلید: جدید (force_join_enabled) و قدیمی (force_channel_enabled)
    v = db.get_setting("force_join_enabled")
    if v is None:
        v = db.get_setting("force_channel_enabled")
    return str(v or "0").lower() in ("1", "true", "on", "yes")

def _parse_single_channel_token(token: str):
    """
    یک توکن کانال را به یکی از این‌ها تبدیل می‌کند:
      - chat_id عددی (int) مثل -1001234567890
      - نام کاربری با @ (str) مثل @mychannel
    از قالب‌های زیر پشتیبانی می‌کند:
      - -1001234567890
      - @username
      - username
      - https://t.me/username
      - t.me/username
      - https://t.me/c/1234567890  -> -1001234567890
      - t.me/c/1234567890          -> -1001234567890
    """
    t = (token or "").strip()
    if not t:
        return None

    # اگر عددی است
    try:
        return int(t)
    except ValueError:
        pass

    # اگر با @ شروع شده
    if t.startswith("@"):
        uname = t[1:].strip()
        if re.fullmatch(r"[A-Za-z0-9_]{4,}", uname):
            return f"@{uname}"
        return None

    # اگر لینک t.me است
    if "t.me/" in t:
        # استخراج بخش بعد از t.me/
        m = re.search(r"(?:https?://)?t\.me/([^/\s]+)", t)
        if m:
            rest = m.group(1)  # ممکن است c/123456789 یا username باشد
            # حالت /c/ID
            if rest.startswith("c/"):
                inner = rest[2:]
                # ممکن است انتها / یا پارامتر داشته باشد
                inner = re.split(r"[/?#]", inner)[0]
                if inner.isdigit():
                    return int(f"-100{inner}")
                return None
            # حالت username
            uname = re.split(r"[/?#]", rest)[0]
            if re.fullmatch(r"[A-Za-z0-9_]{4,}", uname):
                return f"@{uname}"
            return None

    # اگر فقط username بدون @ است
    if re.fullmatch(r"[A-Za-z0-9_]{4,}", t):
        return f"@{t}"

    return None

def _get_channels() -> list[object]:
    """
    خروجی لیستی از آیتم‌ها:
      - اعداد (chat_id های عددی)
      - رشته‌های شروع‌شده با @ برای username
    پشتیبانی از هر دو کلید: جدید (force_join_channel) و قدیمی (force_channel_id)
    چند مقدار با کاما جدا می‌شوند.
    """
    raw = db.get_setting("force_join_channel") or db.get_setting("force_channel_id") or ""
    items = [s.strip() for s in raw.split(",") if s.strip()]
    result = []
    invalid = []
    for it in items:
        parsed = _parse_single_channel_token(it)
        if parsed is None:
            invalid.append(it)
        else:
            result.append(parsed)
    if invalid:
        # یک بار به‌صورت مجتمع هشدار بدهیم نه برای هر بار
        logger.warning("Invalid channel identifiers in settings ignored: %s", ", ".join(repr(i) for i in invalid))
    return result

# مجوزهای معتبر عضویت (سازگار با نسخه‌های مختلف PTB)
_ALLOWED_STATUSES = set(
    x for x in (
        getattr(ChatMemberStatus, "MEMBER", "member"),
        getattr(ChatMemberStatus, "ADMINISTRATOR", "administrator"),
        getattr(ChatMemberStatus, "OWNER", "owner"),      # PTB 20+
        getattr(ChatMemberStatus, "CREATOR", None),       # سازگاری با قدیمی‌ها
    )
    if x
)

async def _is_member(bot, channel: object, user_id: int) -> bool:
    channel_key = str(channel).lstrip()
    found, cached_val = _cache_get(user_id, channel_key)
    if found:
        return cached_val
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        is_ok = member.status in _ALLOWED_STATUSES
        _cache_set(user_id, channel_key, is_ok)
        return is_ok
    except Exception as e:
        logger.warning("Could not check membership for user %s in channel %s: %s", user_id, channel, e)
        _cache_set(user_id, channel_key, False, ttl=timedelta(minutes=1))
        return False

def check_channel_membership(func):
    """
    قبل از اجرای تابع، عضویت کاربر در کانال‌های اجباری را چک می‌کند.
    - ادمین از بررسی معاف است.
    - از هر دو فرمت کانال (@username و chat_id عددی) و لینک t.me پشتیبانی می‌کند.
    - از OWNER به‌جای CREATOR استفاده می‌کند (سازگار با نسخه‌های جدید PTB).
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id

        # ادمین را معاف کن
        try:
            admin_id_int = int(ADMIN_ID)
        except Exception:
            admin_id_int = ADMIN_ID
        if user_id == admin_id_int:
            return await func(update, context, *args, **kwargs)

        if not _is_enabled():
            return await func(update, context, *args, **kwargs)

        channels = _get_channels()
        if not channels:
            return await func(update, context, *args, **kwargs)

        not_joined = []
        for ch in channels:
            if not await _is_member(context.bot, ch, user_id):
                not_joined.append(ch)

        if not not_joined:
            return await func(update, context, *args, **kwargs)

        # ساخت دکمه‌های عضویت
        keyboard = []
        for ch in not_joined:
            try:
                chat = await context.bot.get_chat(ch)
                url = None
                if getattr(chat, "invite_link", None):
                    url = chat.invite_link
                elif getattr(chat, "username", None):
                    url = f"https://t.me/{chat.username}"
                elif isinstance(ch, int):
                    url = f"https://t.me/c/{str(ch).replace('-100', '')}"
                else:
                    url = "https://t.me/"
                title = getattr(chat, "title", str(ch))
                keyboard.append([InlineKeyboardButton(f"📢 عضویت در کانال {title}", url=url)])
            except Exception:
                if isinstance(ch, int):
                    url = f"https://t.me/c/{str(ch).replace('-100','')}"
                    label = f"📢 عضویت در کانال ({ch})"
                else:
                    url = f"https://t.me/{str(ch).lstrip('@')}"
                    label = f"📢 عضویت در کانال {ch}"
                keyboard.append([InlineKeyboardButton(label, url=url)])

        keyboard.append([InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership")])

        text = "لطفاً برای استفاده از ربات، ابتدا در کانال(های) زیر عضو شوید و سپس دکمه «بررسی عضویت» را بزنید:"

        if update.callback_query:
            await update.callback_query.answer("شما هنوز عضو کانال نشده‌اید.", show_alert=True)
            try:
                await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    return wrapper