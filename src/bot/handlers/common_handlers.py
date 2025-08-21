# -*- coding: utf-8 -*-

from functools import wraps
import logging
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
import database as db
from config import ADMIN_ID
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# کش برای نگهداری وضعیت عضویت کاربران
# کلید: (user_id, channel_id), مقدار: (وضعیت عضویت, زمان انقضای کش)
MEMBERSHIP_CACHE = {}
# مدت اعتبار کش (به ثانیه)
CACHE_EXPIRY = 600  # 10 دقیقه

def check_channel_membership(func):
    """
    یک دکوراتور که قبل از اجرای تابع، عضویت کاربر در کانال‌های اجباری را چک می‌کند.
    ادمین‌ها از این چک معاف هستند. از سیستم کش برای کاهش درخواست‌ها استفاده می‌کند.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id

        # اگر کاربر ادمین است، از چک عبور کن
        if user_id == ADMIN_ID:
            return await func(update, context, *args, **kwargs)

        is_enabled = str(db.get_setting("force_channel_enabled") or "0").lower() in ("1", "true", "on")
        if not is_enabled:
            return await func(update, context, *args, **kwargs)

        channel_ids_str = db.get_setting("force_channel_id") or ""
        if not channel_ids_str:
            return await func(update, context, *args, **kwargs)

        try:
            channel_ids = [int(cid.strip()) for cid in channel_ids_str.split(',') if cid.strip()]
        except ValueError:
            logger.error(f"Invalid channel IDs in settings: {channel_ids_str}")
            return await func(update, context, *args, **kwargs)

        # بررسی کش برای محدود کردن درخواست‌ها
        current_time = datetime.now()
        not_joined_channels = []
        
        for channel_id in channel_ids:
            cache_key = (user_id, channel_id)
            
            # بررسی کش
            if cache_key in MEMBERSHIP_CACHE:
                is_member, expiry_time = MEMBERSHIP_CACHE[cache_key]
                # اگر کش هنوز معتبر است
                if current_time < expiry_time:
                    if not is_member:
                        not_joined_channels.append(channel_id)
                    continue
            
            # بررسی عضویت و به‌روزرسانی کش
            try:
                member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                is_member = member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
                
                # ذخیره در کش با زمان انقضا
                MEMBERSHIP_CACHE[cache_key] = (is_member, current_time + timedelta(seconds=CACHE_EXPIRY))
                
                if not is_member:
                    not_joined_channels.append(channel_id)
            except Exception as e:
                logger.warning(f"Could not check membership for user {user_id} in channel {channel_id}: {e}")
                not_joined_channels.append(channel_id)
                # ذخیره خطا در کش با مدت کوتاه‌تر
                MEMBERSHIP_CACHE[cache_key] = (False, current_time + timedelta(seconds=60))

        # مدیریت کش (حذف موارد منقضی)
        _cleanup_cache()

        if not not_joined_channels:
            # اگر عضو بود، تابع اصلی را اجرا کن
            return await func(update, context, *args, **kwargs)
        else:
            # اگر عضو نبود، پیام عضویت را بفرست
            keyboard = []
            for channel_id in not_joined_channels:
                try:
                    chat = await context.bot.get_chat(channel_id)
                    if chat.invite_link:
                        keyboard.append([InlineKeyboardButton(f"📢 عضویت در کانال {chat.title}", url=chat.invite_link)])
                except Exception as e:
                    logger.warning(f"Could not get chat info for {channel_id}: {e}")
                    keyboard.append([InlineKeyboardButton(f"📢 عضویت در کانال ({channel_id})", url=f"https://t.me/c/{str(channel_id).replace('-100', '')}")])

            keyboard.append([InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_membership")])

            text = "لطفاً برای استفاده از ربات، ابتدا در کانال(های) زیر عضو شوید و سپس دکمه «بررسی عضویت» را بزنید:"

            if update.callback_query:
                await update.callback_query.answer("شما هنوز عضو کانال نشده‌اید.", show_alert=True)
                try:
                    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                except Exception:
                    await context.bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

    return wrapper

def _cleanup_cache():
    """پاکسازی موارد منقضی از کش"""
    current_time = datetime.now()
    expired_keys = [k for k, (_, expiry_time) in MEMBERSHIP_CACHE.items() if current_time > expiry_time]
    for key in expired_keys:
        MEMBERSHIP_CACHE.pop(key, None)