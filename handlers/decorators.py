# -*- coding: utf-8 -*-
import logging
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus
from telegram.error import Forbidden, BadRequest

from config import FORCE_JOIN_CHANNELS, ADMIN_ID

logger = logging.getLogger(__name__)

def check_channel_membership(func):
    """
    A decorator that checks if a user is a member of all required channels.
    """
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not FORCE_JOIN_CHANNELS:
            return await func(update, context, *args, **kwargs)

        user = update.effective_user
        if not user or user.id == ADMIN_ID:
            return await func(update, context, *args, **kwargs)

        not_joined_channels = []
        for channel in FORCE_JOIN_CHANNELS:
            try:
                # Use a cached result if available to reduce API calls
                chat_id_str = str(channel).replace('@', '')
                cache_key = f"join_check_{user.id}_{chat_id_str}"
                
                if context.user_data.get(cache_key, False):
                    continue

                member = await context.bot.get_chat_member(chat_id=channel, user_id=user.id)
                if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.CREATOR]:
                    context.user_data[cache_key] = True # Cache the positive result
                else:
                    not_joined_channels.append(channel)
            except (BadRequest, Forbidden) as e:
                logger.error(f"Error checking membership for channel {channel} and user {user.id}: {e}")
                not_joined_channels.append(channel) # Assume not joined if error

        if not_joined_channels:
            keyboard = []
            text = "کاربر گرامی، برای استفاده از ربات لازم است ابتدا در کانال‌های زیر عضو شوید:\n\n"
            for i, channel_id in enumerate(not_joined_channels, 1):
                try:
                    chat = await context.bot.get_chat(channel_id)
                    invite_link = chat.invite_link
                    if not invite_link:
                        # Fallback for public channels without a specific invite link
                         invite_link = f"https://t.me/{chat.username}"
                    text += f"{i}- {chat.title}\n"
                    keyboard.append([InlineKeyboardButton(f"عضویت در کانال {i}", url=invite_link)])
                except Exception as e:
                    logger.error(f"Could not get info for channel {channel_id}: {e}")
                    text += f"{i}- کانال (خطا در دریافت اطلاعات)\n"


            keyboard.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            if update.callback_query:
                await update.callback_query.answer("لطفا ابتدا در کانال(های) مشخص شده عضو شوید.", show_alert=True)
                # It's better to send a new message than to edit, especially if the original message had media
                await update.effective_message.reply_text(text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)
            return

        return await func(update, context, *args, **kwargs)
    return wrapped
