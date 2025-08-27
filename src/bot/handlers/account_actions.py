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
from bot import utils


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
        recipient_id = int(str(update.message.text).strip())
        if recipient_id == update.effective_user.id:
            await update.message.reply_text("❌ نمی‌توانید به خودتان موجودی منتقل کنید.")
            return TRANSFER_RECIPIENT_ID

        recipient = db.get_user(recipient_id)
        if not recipient:
            await update.message.reply_text("❌ کاربری با این شناسه یافت نشد.")
            return TRANSFER_RECIPIENT_ID

        context.user_data['transfer_recipient_id'] = recipient_id
        await update.message.reply_text(
            f"گیرنده: {recipient.get('username') or recipient_id}\n\n"
            "مبلغ (تومان) را وارد کنید:"
        )
        return TRANSFER_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ لطفاً شناسه عددی معتبر وارد کنید.")
        return TRANSFER_RECIPIENT_ID


async def transfer_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw = str(update.message.text).strip().replace(",", "").replace("٬", "")
        amount = float(raw)
        sender = db.get_user(update.effective_user.id)
        if not sender:
            await update.message.reply_text("❌ خطا در بازیابی اطلاعات شما. لطفاً مجدداً تلاش کنید.")
            return ConversationHandler.END

        if amount <= 0:
            await update.message.reply_text("❌ مبلغ باید بزرگ‌تر از صفر باشد.")
            return TRANSFER_AMOUNT
        if sender['balance'] < amount:
            await update.message.reply_text(
                f"❌ موجودی شما کافی نیست (موجودی: {utils.format_toman(sender['balance'], persian_digits=True)})."
            )
            return TRANSFER_AMOUNT

        context.user_data['transfer_amount'] = amount
        recipient_id = context.user_data['transfer_recipient_id']
        recipient = db.get_user(recipient_id) or {}
        kb = [[
            InlineKeyboardButton("✅ تایید", callback_data="transfer_confirm_yes"),
            InlineKeyboardButton("❌ لغو", callback_data="transfer_confirm_no")
        ]]
        await update.message.reply_text(
            f"آیا از انتقال **{utils.format_toman(amount, persian_digits=True)}** "
            f"به کاربر **{recipient.get('username') or recipient_id}** مطمئن هستید؟",
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

    amount = float(context.user_data.get('transfer_amount', 0))
    recipient_id = int(context.user_data.get('transfer_recipient_id'))
    sender_id = q.from_user.id

    # بروزرسانی موجودی‌ها
    db.update_balance(sender_id, -amount)
    db.update_balance(recipient_id, amount)

    await q.edit_message_text("✅ انتقال با موفقیت انجام شد.")
    try:
        await context.bot.send_message(
            recipient_id,
            f"🎁 مبلغ {utils.format_toman(amount, persian_digits=True)} به حساب شما واریز شد."
        )
    except Exception:
        pass
    return ConversationHandler.END


async def transfer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات انتقال لغو شد.")
    await show_account_info(update, context)
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
        raw = str(update.message.text).strip().replace(",", "").replace("٬", "")
        amount = float(raw)
        user = db.get_user(update.effective_user.id)
        if not user:
            await update.message.reply_text("❌ خطا در بازیابی اطلاعات شما. لطفاً مجدداً تلاش کنید.")
            return ConversationHandler.END

        if amount <= 0:
            await update.message.reply_text("❌ مبلغ باید بزرگ‌تر از صفر باشد.")
            return GIFT_FROM_BALANCE_AMOUNT
        if user['balance'] < amount:
            await update.message.reply_text(
                f"❌ موجودی شما کافی نیست (موجودی: {utils.format_toman(user['balance'], persian_digits=True)})."
            )
            return GIFT_FROM_BALANCE_AMOUNT

        context.user_data['gift_amount'] = amount
        kb = [[
            InlineKeyboardButton("✅ تایید", callback_data="gift_confirm_yes"),
            InlineKeyboardButton("❌ لغو", callback_data="gift_confirm_no")
        ]]
        await update.message.reply_text(
            f"آیا از ساخت کد هدیه به مبلغ **{utils.format_toman(amount, persian_digits=True)}** مطمئن هستید؟",
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

    amount = float(context.user_data.get('gift_amount', 0))
    user_id = q.from_user.id

    # کسر مبلغ از کیف‌پول
    db.update_balance(user_id, -amount)

    # تلاش برای ساخت کد یکتا
    code = None
    for _ in range(5):
        candidate = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        if db.create_gift_code(candidate, amount):
            code = candidate
            break

    if not code:
        # بازگشت مبلغ در صورت شکست در ساخت کد
        db.update_balance(user_id, amount)
        await q.edit_message_text("❌ ساخت کد هدیه ناموفق بود. لطفاً بعداً تلاش کنید.")
        return ConversationHandler.END

    await q.edit_message_text(
        f"✅ کد هدیه با موفقیت ساخته شد:\n\n`{code}`\n\nاین کد را برای دوستان خود ارسال کنید.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def create_gift_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات ساخت کد هدیه لغو شد.")
    await show_account_info(update, context)
    return ConversationHandler.END