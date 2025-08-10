# -*- coding: utf-8 -*-

from functools import wraps
import logging
from telegram.ext import ContextTypes
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
import database as db

logger = logging.getLogger(__name__)

def check_channel_membership(func):
    """
    یک دکوراتور که قبل از اجرای تابع، عضویت کاربر در کانال‌های اجباری را چک می‌کند.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        is_enabled = str(db.get_setting("force_channel_enabled") or "0").lower() in ("1", "true", "on")
        if not is_enabled:
            return await func(update, context, *args, **kwargs)

        channel_ids_str = db.get_setting("force_channel_id") or ""
        if not channel_ids_str:
            return await func(update, context, *args, **kwargs)

        user_id = update.effective_user.id
        channel_ids = [int(cid.strip()) for cid in channel_ids_str.split(',') if cid.strip()]
        
        not_joined_channels = []
        for channel_id in channel_ids:
            try:
                member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                    not_joined_channels.append(channel_id)
            except Exception as e:
                logger.warning(f"Could not check membership for user {user_id} in channel {channel_id}: {e}")
                not_joined_channels.append(channel_id)

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
                except Exception:
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