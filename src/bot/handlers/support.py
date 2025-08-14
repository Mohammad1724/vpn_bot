# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from bot.constants import SUPPORT_TICKET_OPEN, CMD_CANCEL
from bot.keyboards import get_main_menu_keyboard
from config import ADMIN_ID

logger = logging.getLogger(__name__)

async def support_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    آغاز کانورسیشن پشتیبانی برای کاربر.
    """
    await update.message.reply_text(
        "شما به پشتیبانی متصل شدید. لطفاً پیام خود را ارسال کنید.\n"
        f"برای پایان گفتگو، دستور {CMD_CANCEL} را بفرستید.",
        reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)
    )
    return SUPPORT_TICKET_OPEN

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پیام کاربر را دریافت و برای ادمین ارسال می‌کند و مکالمه را باز نگه می‌دارد.
    """
    user = update.effective_user
    
    # اگر این اولین پیام در این مکالمه است، اطلاعات کاربر را هم بفرست
    if not context.user_data.get('ticket_active'):
        context.user_data['ticket_active'] = True
        user_info = (
            f" Ticket from: {user.full_name}\n"
            f"Username: @{user.username}\n"
            f"ID: `{user.id}`\n"
            f"---"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=user_info, parse_mode="Markdown")

    # فروارد پیام کاربر به ادمین
    fwd_msg = await update.message.forward(chat_id=ADMIN_ID)
    
    # ایجاد یک لینک دو طرفه بین پیام اصلی کاربر و پیام فروارد شده
    # این به ما اجازه می‌دهد در هر دو جهت پاسخ‌ها را ردیابی کنیم
    if 'ticket_mappings' not in context.bot_data:
        context.bot_data['ticket_mappings'] = {}
    
    # user_id -> message_id in admin chat
    # message_id in admin_chat -> user_id
    context.bot_data['ticket_mappings'][f"user_{user.id}"] = fwd_msg.message_id
    context.bot_data['ticket_mappings'][f"admin_{fwd_msg.message_id}"] = user.id

    # فقط زیر اولین پیام دکمه بستن تیکت را قرار بده
    if not context.user_data.get('close_button_sent'):
        context.user_data['close_button_sent'] = True
        kb = [[InlineKeyboardButton("🔒 بستن تیکت", callback_data=f"close_ticket_{user.id}")]]
        await fwd_msg.reply_text("برای بستن این مکالمه از دکمه زیر استفاده کنید:", reply_markup=InlineKeyboardMarkup(kb))
        
    return SUPPORT_TICKET_OPEN

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پاسخ ادمین (که با ریپلای ارسال شده) را برای کاربر اصلی می‌فرستد.
    """
    if not update.message.reply_to_message:
        return

    replied_msg_id = update.message.reply_to_message.message_id
    
    # پیدا کردن کاربر مقصد از طریق دیکشنری
    user_to_reply_id = context.bot_data.get('ticket_mappings', {}).get(f"admin_{replied_msg_id}")
    
    if user_to_reply_id:
        try:
            await context.bot.copy_message(
                chat_id=user_to_reply_id,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id
            )
            await update.message.reply_text("✅ پاسخ شما برای کاربر ارسال شد.")
        except Exception:
            await update.message.reply_text("❌ ارسال پاسخ ناموفق بود (احتمالاً کاربر ربات را بلاک کرده).")

async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تیکت را می‌بندد و به هر دو طرف اطلاع می‌دهد.
    """
    q = update.callback_query
    await q.answer()
    
    user_id_to_close = int(q.data.split('_')[-1])
    
    # پاک کردن لینک‌ها از دیکشنری
    if 'ticket_mappings' in context.bot_data:
        admin_msg_id = context.bot_data['ticket_mappings'].pop(f"user_{user_id_to_close}", None)
        if admin_msg_id:
            context.bot_data['ticket_mappings'].pop(f"admin_{admin_msg_id}", None)
            
    # اطلاع به ادمین و کاربر
    await q.edit_message_text("✅ تیکت با موفقیت بسته شد.")
    try:
        await context.bot.send_message(
            chat_id=user_id_to_close,
            text="مکالمه پشتیبانی توسط ادمین بسته شد. در صورت نیاز می‌توانید دوباره پیام دهید.",
            reply_markup=get_main_menu_keyboard(user_id_to_close)
        )
    except Exception:
        pass # User may have blocked the bot

async def support_ticket_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    وقتی کاربر /cancel می‌زند، مکالمه را تمام می‌کند.
    """
    user_id = update.effective_user.id
    if 'ticket_mappings' in context.bot_data:
        admin_msg_id = context.bot_data['ticket_mappings'].pop(f"user_{user_id}", None)
        if admin_msg_id:
            context.bot_data['ticket_mappings'].pop(f"admin_{admin_msg_id}", None)
            try:
                await context.bot.send_message(ADMIN_ID, f"کاربر با شناسه {user_id} گفتگوی پشتیبانی را بست.")
            except Exception:
                pass

    context.user_data.clear()
    await update.message.reply_text(
        "شما از حالت چت با پشتیبانی خارج شدید.",
        reply_markup=get_main_menu_keyboard(user_id)
    )
    return ConversationHandler.END