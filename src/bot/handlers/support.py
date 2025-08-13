# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup
from bot.constants import SUPPORT_TICKET_MESSAGE, CMD_CANCEL
from config import ADMIN_ID

async def support_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    آغاز کانورسیشن پشتیبانی برای کاربر.
    """
    await update.message.reply_text(
        "لطفاً پیام خود را برای تیم پشتیبانی ارسال کنید.\n"
        f"برای لغو، دستور {CMD_CANCEL} را بفرستید.",
        reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)
    )
    return SUPPORT_TICKET_MESSAGE

async def support_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پیام کاربر را دریافت و برای ادمین ارسال می‌کند.
    """
    user = update.effective_user
    user_info = (
        f" Ticket from: {user.full_name}\n"
        f"Username: @{user.username}\n"
        f"ID: `{user.id}`\n"
        f"---"
    )
    
    # فروارد پیام کاربر به ادمین به همراه اطلاعاتش
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=user_info, parse_mode="Markdown")
        # پیام اصلی کاربر را فروارد می‌کنیم تا ادمین بتواند روی آن ریپلای کند
        await update.message.forward(chat_id=ADMIN_ID)
        
        await update.message.reply_text(
            "✅ پیام شما با موفقیت برای پشتیبانی ارسال شد. لطفاً منتظر پاسخ بمانید.",
            reply_markup=context.bot_data['main_menu_keyboard']
        )
    except Exception as e:
        await update.message.reply_text(
            "❌ متاسفانه در ارسال پیام به پشتیبانی خطایی رخ داد. لطفاً بعداً تلاش کنید.",
            reply_markup=context.bot_data['main_menu_keyboard']
        )
        
    return ConversationHandler.END

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پاسخ ادمین (که با ریپلای ارسال شده) را برای کاربر اصلی می‌فرستد.
    """
    # مطمئن می‌شویم که پیام یک ریپلای است
    if not update.message.reply_to_message:
        return

    replied_msg = update.message.reply_to_message
    
    # اگر پیام فروارد شده بود، اطلاعات کاربر اصلی در آن است
    if replied_msg.forward_from:
        user_to_reply_id = replied_msg.forward_from.id
        
        try:
            # پیام ادمین را برای کاربر ارسال می‌کنیم
            await context.bot.send_message(
                chat_id=user_to_reply_id,
                text=f"✉️ **پاسخ پشتیبانی:**\n\n{update.message.text}"
            )
            # به خود ادمین هم تایید ارسال را می‌دهیم
            await update.message.reply_text("✅ پاسخ شما برای کاربر ارسال شد.")
        except Exception:
            await update.message.reply_text("❌ ارسال پاسخ ناموفق بود (احتمالاً کاربر ربات را بلاک کرده).")