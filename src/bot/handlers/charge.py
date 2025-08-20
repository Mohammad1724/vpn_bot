# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

import database as db
from config import ADMIN_ID
from bot import constants
from bot.utils import format_toman

logger = logging.getLogger(__name__)

def _get_payment_info_text():
    """متن راهنمای پرداخت را از دیتابیس می‌سازد."""
    instr = db.get_setting("payment_instruction_text") or "لطفاً مبلغ را به یکی از شماره کارت‌های زیر واریز کرده و از رسید اسکرین‌شات بگیرید."
    
    lines = [f"**راهنمای شارژ حساب**\n\n{instr}\n"]
    has_cards = False
    for i in range(1, 4):
        num = db.get_setting(f"payment_card_{i}_number")
        name = db.get_setting(f"payment_card_{i}_name")
        bank = db.get_setting(f"payment_card_{i}_bank")
        if num and name:
            has_cards = True
            bank_info = f" ({bank})" if bank else ""
            lines.append(f"💳 شماره کارت: `{num}`\n👤 صاحب حساب: {name}{bank_info}\n")

    if not has_cards:
        return "در حال حاضر اطلاعات پرداختی ثبت نشده است. لطفاً با پشتیبانی تماس بگیرید."
        
    return "\n".join(lines)

# -----------------
# شروع و دریافت مبلغ
# -----------------
async def charge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.message.delete()
        except BadRequest:
            pass

    if em:
        await em.reply_text(
            "مبلغ شارژ مورد نظر (تومان) را وارد کنید:",
            reply_markup=ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)
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
    amount_str = format_toman(amount, persian_digits=True)

    text = f"""
⚠️ تایید شارژ حساب

- مبلغ: {amount_str}

با تایید، اطلاعات پرداخت به شما نمایش داده می‌شود.
ادامه می‌دهید؟
    """.strip()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید و ادامه", callback_data="charge_amount_confirm")],
        [InlineKeyboardButton("❌ لغو", callback_data="charge_amount_cancel")]
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    return constants.CHARGE_AMOUNT

# -----------------
# نمایش اطلاعات پرداخت و درخواست رسید
# -----------------
async def charge_amount_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data.endswith("cancel"):
        context.user_data.clear()
        try:
            await q.edit_message_text("❌ عملیات شارژ لغو شد.")
        except BadRequest:
            pass
        return ConversationHandler.END

    payment_info = _get_payment_info_text()
    try:
        await q.edit_message_text(
            payment_info,
            reply_markup=ReplyKeyboardMarkup([['/cancel']], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        await q.message.reply_text("لطفاً تصویر رسید پرداخت را ارسال کنید.")
    except BadRequest:
        await context.bot.send_message(
            chat_id=q.from_user.id,
            text=payment_info,
            reply_markup=ReplyKeyboardMarkup([['/cancel']], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        await context.bot.send_message(
            chat_id=q.from_user.id,
            text="لطفاً تصویر رسید پرداخت را ارسال کنید."
        )
    return constants.CHARGE_RECEIPT

async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    photos = update.message.photo or []
    if not photos:
        await update.message.reply_text("❌ لطفاً تصویر رسید را ارسال کنید.")
        return constants.CHARGE_RECEIPT

    amount = context.user_data.get('charge_amount', 0)
    if amount <= 0:
        await update.message.reply_text("❌ مبلغ شارژ مشخص نیست. لطفاً از ابتدا شروع کنید: /cancel")
        return ConversationHandler.END

    promo_code = ""
    if context.user_data.get('first_charge_promo_applied'):
        promo_code = db.get_setting('first_charge_code') or ""

    charge_id = None
    try:
        if hasattr(db, "create_charge_request"):
            charge_id = db.create_charge_request(user_id, amount, note=promo_code)
    except Exception as e:
        logger.error("Failed to save charge request to DB: %s", e)

    if charge_id is None:
        await update.message.reply_text("❌ خطا در ثبت درخواست. لطفاً به پشتیبانی اطلاع دهید.")
        return ConversationHandler.END

    file_id = photos[-1].file_id
    caption = (
        f"درخواست شارژ جدید (ID: {charge_id}):\n"
        f"- کاربر: `{user_id}` (@{username or '—'})\n"
        f"- مبلغ: {amount:,} تومان"
    )
    if promo_code:
        caption += f"\n- کد شارژ اول: `{promo_code}`"

    callback_data_confirm = f"admin_confirm_charge_{charge_id}"
    callback_data_reject = f"admin_reject_charge_{charge_id}_{user_id}"

    kb_admin = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید شارژ", callback_data=callback_data_confirm)],
        [InlineKeyboardButton("❌ رد شارژ", callback_data=callback_data_reject)]
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
        logger.error("Failed to send charge request to admin: %s", e)

    from bot.keyboards import get_main_menu_keyboard
    await update.message.reply_text(
        "✅ رسید شما دریافت شد. پس از بررسی ادمین نتیجه اعلام می‌شود.",
        reply_markup=get_main_menu_keyboard(user_id)
    )

    context.user_data.clear()
    return ConversationHandler.END