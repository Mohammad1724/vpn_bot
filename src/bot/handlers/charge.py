# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
from config import ADMIN_ID
from bot import constants

logger = logging.getLogger(__name__)

async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except BadRequest:
        pass

    await context.bot.send_message(
        chat_id=q.from_user.id,
        text="مبلغ شارژ مورد نظر (تومان) را وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([[ "انصراف /cancel" ]], resize_keyboard=True)
    )
    return constants.CHARGE_AMOUNT

async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip().replace(",", "")
    try:
        amount = int(float(txt))
        if amount <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("❌ مبلغ نامعتبر است. یک عدد مثبت وارد کنید.")
        return constants.CHARGE_AMOUNT

    context.user_data['charge_amount'] = amount

    text = f"""
⚠️ تایید شارژ حساب

- مبلغ: {amount:,} تومان

با تایید، باید رسید پرداخت را ارسال کنید.
آیا ادامه می‌دهید؟
    """.strip()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ادامه", callback_data="charge_amount_confirm")],
        [InlineKeyboardButton("❌ لغو", callback_data="charge_amount_cancel")]
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    # در همین استیت منتظر تایید می‌مانیم
    return constants.CHARGE_AMOUNT

async def charge_amount_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data.endswith("cancel"):
        context.user_data.pop('charge_amount', None)
        try:
            await q.edit_message_text("❌ عملیات شارژ لغو شد.")
        except BadRequest:
            pass
        return ConversationHandler.END

    # تایید شد -> درخواست رسید
    try:
        await q.edit_message_text("لطفاً تصویر رسید پرداخت را ارسال کنید.", parse_mode=ParseMode.MARKDOWN)
    except BadRequest:
        await context.bot.send_message(chat_id=q.from_user.id, text="لطفاً تصویر رسید پرداخت را ارسال کنید.")
    return constants.CHARGE_RECEIPT

async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photos = update.message.photo or []
    if not photos:
        await update.message.reply_text("❌ لطفاً تصویر رسید را ارسال کنید.")
        return constants.CHARGE_RECEIPT

    amount = context.user_data.get('charge_amount', 0)
    if amount <= 0:
        await update.message.reply_text("❌ مبلغ شارژ مشخص نیست. لطفاً از ابتدا شروع کنید: /cancel")
        return ConversationHandler.END

    # ارسال برای ادمین جهت تایید
    file_id = photos[-1].file_id
    caption = f"درخواست شارژ جدید:\n- کاربر: `{user_id}`\n- مبلغ: {amount:,} تومان"
    kb_admin = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید شارژ", callback_data=f"admin_confirm_charge_{user_id}_{amount}")],
        [InlineKeyboardButton("❌ رد شارژ", callback_data=f"admin_reject_charge_{user_id}")]
    ])
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=file_id,
            caption=caption,
            reply_markup=kb_admin,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error("Failed to send charge request to admin: %s", e, exc_info=True)

    # پیام به کاربر
    await update.message.reply_text(
        "✅ رسید شما دریافت شد. پس از بررسی ادمین نتیجه اعلام می‌شود.",
        reply_markup=ReplyKeyboardMarkup([[ "بازگشت به منو /start" ]], resize_keyboard=True)
    )

    # پاکسازی
    context.user_data.pop('charge_amount', None)
    return ConversationHandler.END