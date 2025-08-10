# -*- coding: utf-8 -*-

import random
import string
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from bot.constants import (
    TRANSFER_RECIPIENT_ID, TRANSFER_AMOUNT, TRANSFER_CONFIRM,
    GIFT_FROM_BALANCE_AMOUNT, GIFT_FROM_BALANCE_CONFIRM, CMD_CANCEL
)
from bot.handlers.start import show_account_info
import database as db

# ===== Transfer Balance Conversation =====

async def transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "💸 **انتقال موجودی**\n\n"
        "لطفاً شناسه عددی (user ID) کاربری که می‌خواهید به او موجودی منتقل کنید را ارسال نمایید.\n\n"
        f"برای لغو، {CMD_CANCEL} را ارسال کنید.",
        parse_mode="Markdown"
    )
    return TRANSFER_RECIPIENT_ID

async def transfer_recipient_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        recipient_id = int(update.message.text.strip())
        if recipient_id == update.effective_user.id:
            await update.message.reply_text("❌ نمی‌توانید به خودتان موجودی منتقل کنید.")
            return TRANSFER_RECIPIENT_ID
        recipient = db.get_user(recipient_id)
        if not recipient:
            await update.message.reply_text("❌ کاربری با این شناسه یافت نشد.")
            return TRANSFER_RECIPIENT_ID
        context.user_data['transfer_recipient_id'] = recipient_id
        await update.message.reply_text(f"گیرنده: {recipient.get('username') or recipient_id}\n\nمبلغ (تومان) را وارد کنید:")
        return TRANSFER_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ لطفاً شناسه عددی معتبر وارد کنید.")
        return TRANSFER_RECIPIENT_ID

async def transfer_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        sender = db.get_user(update.effective_user.id)
        if amount <= 0:
            await update.message.reply_text("❌ مبلغ باید بزرگ‌تر از صفر باشد.")
            return TRANSFER_AMOUNT
        if sender['balance'] < amount:
            await update.message.reply_text(f"❌ موجودی شما کافی نیست (موجودی: {sender['balance']:.0f} تومان).")
            return TRANSFER_AMOUNT

        context.user_data['transfer_amount'] = amount
        recipient_id = context.user_data['transfer_recipient_id']
        recipient = db.get_user(recipient_id)
        kb = [[InlineKeyboardButton("✅ تایید", callback_data="transfer_confirm_yes"),
               InlineKeyboardButton("❌ لغو", callback_data="transfer_confirm_no")]]
        await update.message.reply_text(
            f"آیا از انتقال **{amount:,.0f} تومان** به کاربر **{recipient.get('username') or recipient_id}** مطمئن هستید؟",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        return TRANSFER_CONFIRM
    except ValueError:
        await update.message.reply_text("❌ لطفاً مبلغ را به صورت عدد وارد کنید.")
        return TRANSFER_AMOUNT

async def transfer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "transfer_confirm_no":
        await q.edit_message_text("انتقال لغو شد.")
        return ConversationHandler.END

    amount = context.user_data['transfer_amount']
    recipient_id = context.user_data['transfer_recipient_id']
    sender_id = q.from_user.id

    db.update_balance(sender_id, -amount)
    db.update_balance(recipient_id, amount)

    await q.edit_message_text("✅ انتقال با موفقیت انجام شد.")
    try:
        await context.bot.send_message(recipient_id, f"🎁 مبلغ {amount:,.0f} تومان از طرف یک کاربر به حساب شما منتقل شد.")
    except Exception:
        pass
    return ConversationHandler.END

async def transfer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات انتقال لغو شد.")
    await show_account_info(update, context)  # بازگشت به منوی حساب
    return ConversationHandler.END


# ===== Create Gift Code from Balance Conversation =====

async def create_gift_from_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "🎁 **ساخت کد هدیه از موجودی**\n\n"
        "مبلغ کد هدیه (تومان) را وارد کنید. این مبلغ از کیف پول شما کسر خواهد شد.\n\n"
        f"برای لغو، {CMD_CANCEL} را ارسال کنید.",
        parse_mode="Markdown"
    )
    return GIFT_FROM_BALANCE_AMOUNT

async def create_gift_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        user = db.get_user(update.effective_user.id)
        if amount <= 0:
            await update.message.reply_text("❌ مبلغ باید بزرگ‌تر از صفر باشد.")
            return GIFT_FROM_BALANCE_AMOUNT
        if user['balance'] < amount:
            await update.message.reply_text(f"❌ موجودی شما کافی نیست (موجودی: {user['balance']:.0f} تومان).")
            return GIFT_FROM_BALANCE_AMOUNT

        context.user_data['gift_amount'] = amount
        kb = [[InlineKeyboardButton("✅ تایید", callback_data="gift_confirm_yes"),
               InlineKeyboardButton("❌ لغو", callback_data="gift_confirm_no")]]
        await update.message.reply_text(
            f"آیا از ساخت کد هدیه به مبلغ **{amount:,.0f} تومان** مطمئن هستید؟",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        return GIFT_FROM_BALANCE_CONFIRM
    except ValueError:
        await update.message.reply_text("❌ لطفاً مبلغ را به صورت عدد وارد کنید.")
        return GIFT_FROM_BALANCE_AMOUNT

async def create_gift_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "gift_confirm_no":
        await q.edit_message_text("ساخت کد هدیه لغو شد.")
        return ConversationHandler.END

    amount = context.user_data['gift_amount']
    user_id = q.from_user.id
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

    db.update_balance(user_id, -amount)
    db.create_gift_code(code, amount)

    await q.edit_message_text(f"✅ کد هدیه با موفقیت ساخته شد:\n\n`{code}`\n\nاین کد را برای دوستان خود ارسال کنید.", parse_mode="Markdown")
    return ConversationHandler.END

async def create_gift_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات ساخت کد هدیه لغو شد.")
    await show_account_info(update, context)  # بازگشت به منوی حساب
    return ConversationHandler.END