# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from bot.constants import SUPPORT_TICKET_OPEN
from bot.keyboards import get_main_menu_keyboard
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# --- Inline Keyboards (user side) ---
def _user_support_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 پایان گفتگو", callback_data="support_end")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="support_back_main")]
    ])

async def support_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    آغاز کانورسیشن پشتیبانی برای کاربر (شیشه‌ای).
    """
    user_id = update.effective_user.id

    # اطمینان از وجود دیکشنری تیکت‌ها و پاک‌کردن وضعیت قبلی
    tickets = context.bot_data.setdefault('tickets', {})
    tickets.pop(user_id, None)

    await update.message.reply_text(
        "📞 شما به پشتیبانی متصل شدید.\n"
        "لطفاً پیام خود را ارسال کنید. می‌توانید در هر زمان با دکمه‌های زیر گفتگو را پایان دهید یا به منوی اصلی برگردید.",
        reply_markup=_user_support_kb()
    )
    return SUPPORT_TICKET_OPEN

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پیام کاربر را دریافت و برای ادمین ارسال می‌کند.
    """
    user = update.effective_user

    # اگر ادمین تیکت را بسته باشد، گفتگو را خاتمه بده
    if context.bot_data.get('tickets', {}).get(user.id, {}).get('closed'):
        await update.message.reply_text(
            "این مکالمه توسط ادمین بسته شده است. برای شروع مکالمه جدید، دوباره دکمه «📞 پشتیبانی» را بزنید.",
            reply_markup=get_main_menu_keyboard(user.id)
        )
        return ConversationHandler.END

    # اگر اولین پیام است، اطلاعات کاربر را برای ادمین بفرست
    if not context.user_data.get('ticket_active'):
        context.user_data['ticket_active'] = True
        user_info = (
            f" Ticket from: {user.full_name}\n"
            f"Username: @{user.username}\n"
            f"ID: `{user.id}`\n"
            f"---"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=user_info, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Failed sending user info to admin: %s", e)

    # پیام را فوروارد کن
    fwd_msg = await update.message.forward(chat_id=ADMIN_ID)

    tickets = context.bot_data.setdefault('tickets', {})
    # نگهداری اطلاعات تیکت
    tickets[user.id] = {'admin_msg_id': fwd_msg.message_id, 'closed': False}
    tickets[f"admin_{fwd_msg.message_id}"] = user.id

    # فقط زیر اولین پیام ادمین، دکمه بستن تیکت را قرار بده
    if not context.user_data.get('close_button_sent'):
        context.user_data['close_button_sent'] = True
        kb = [[InlineKeyboardButton("🔒 بستن تیکت", callback_data=f"close_ticket_{user.id}")]]
        try:
            await fwd_msg.reply_text("برای بستن این مکالمه از دکمه زیر استفاده کنید:", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            logger.warning("Failed to add close button under admin message: %s", e)

    return SUPPORT_TICKET_OPEN

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پاسخ ادمین را برای کاربر می‌فرستد (باید روی ریپلای به پیام فورواردشده باشد).
    """
    if not update.message.reply_to_message:
        return

    replied_msg = update.message.reply_to_message

    # پیدا کردن کاربر مقصد
    user_to_reply_id = context.bot_data.get('tickets', {}).get(f"admin_{replied_msg.message_id}")
    # fallback: از forward_origin استفاده کن اگر موجود است
    if not user_to_reply_id and getattr(replied_msg, "forward_origin", None) and getattr(replied_msg.forward_origin, "type", None) == 'user':
        user_to_reply_id = replied_msg.forward_origin.sender_user.id

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
    بستن تیکت توسط ادمین (از طریق دکمه شیشه‌ای زیر پیام فورواردشده).
    """
    q = update.callback_query
    await q.answer()

    user_id_to_close = int(q.data.split('_')[-1])

    tickets = context.bot_data.setdefault('tickets', {})
    # تنظیم فلگ "بسته شده" برای کاربر
    if user_id_to_close in tickets:
        tickets[user_id_to_close]['closed'] = True

    try:
        await q.edit_message_text("✅ تیکت با موفقیت بسته شد.")
    except Exception:
        pass
    try:
        await context.bot.send_message(
            chat_id=user_id_to_close,
            text="مکالمه پشتیبانی توسط ادمین بسته شد. در صورت نیاز می‌توانید دوباره پیام دهید.",
            reply_markup=get_main_menu_keyboard(user_id_to_close)
        )
    except Exception:
        pass

# --- User inline callbacks (end/back) ---
async def support_end_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    کاربر با دکمه شیشه‌ای «پایان گفتگو» گفتگو را می‌بندد.
    """
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    tickets = context.bot_data.setdefault('tickets', {})
    if user_id in tickets:
        tickets[user_id]['closed'] = True

    try:
        await q.edit_message_text("🔒 گفتگو با پشتیبانی پایان یافت.")
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=user_id,
        text="شما از حالت چت با پشتیبانی خارج شدید.",
        reply_markup=get_main_menu_keyboard(user_id)
    )
    context.user_data.clear()
    return ConversationHandler.END

async def support_back_to_main_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    کاربر با دکمه شیشه‌ای «منوی اصلی» برگردد و کانورسیشن بسته شود.
    """
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    # گفتگو را همزمان ببند تا state از SUPPORT_TICKET_OPEN خارج شود
    tickets = context.bot_data.setdefault('tickets', {})
    if user_id in tickets:
        tickets[user_id]['closed'] = True

    try:
        await q.edit_message_text("🏠 بازگشت به منوی اصلی.")
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=user_id,
        text="به منوی اصلی برگشتید.",
        reply_markup=get_main_menu_keyboard(user_id)
    )
    context.user_data.clear()
    return ConversationHandler.END

async def support_ticket_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    وقتی کاربر /cancel می‌زند، مکالمه را تمام می‌کند.
    """
    user_id = update.effective_user.id
    tickets = context.bot_data.setdefault('tickets', {})
    if user_id in tickets:
        tickets[user_id]['closed'] = True

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