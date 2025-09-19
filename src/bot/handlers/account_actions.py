# filename: bot/handlers/account_actions.py
# -*- coding: utf-8 -*-

import random
import string
import re
import sqlite3

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import (
    TRANSFER_RECIPIENT_ID, TRANSFER_AMOUNT, TRANSFER_CONFIRM,
    GIFT_FROM_BALANCE_AMOUNT, GIFT_FROM_BALANCE_CONFIRM, CMD_CANCEL
)
from bot.handlers.start import show_account_info
import database as db
from bot import utils


# -------- Helpers --------

_PERSIAN_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _normalize_amount_text(t: str) -> str:
    """
    تبدیل ارقام فارسی به انگلیسی و حذف جداکننده‌ها/متن‌های اضافی
    خروجی فقط شامل ارقام و نقطه اعشار است.
    """
    s = str(t or "").strip().translate(_PERSIAN_TO_EN)
    s = s.replace(",", "").replace("٬", "").replace("،", "").replace(" ", "")
    # فقط رقم و نقطه را نگه داریم
    s = re.sub(r"[^\d.]", "", s)
    return s


def _cleanup_transfer_state(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('transfer_recipient_id', None)
    context.user_data.pop('transfer_amount', None)


def _cleanup_gift_state(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('gift_amount', None)


def _transfer_balance_atomic(sender_id: int, recipient_id: int, amount: float) -> tuple[bool, str]:
    """
    انتقال موجودی به‌صورت اتمیک داخل یک تراکنش.
    خروجی: (موفق؟, کد دلیل)
      codes: ok | insufficient | not_found | error
    """
    conn = db._connect_db()
    cur = conn.cursor()
    try:
        conn.execute("BEGIN")
        # وجود فرستنده/گیرنده
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,))
        srow = cur.fetchone()
        cur.execute("SELECT 1 FROM users WHERE user_id = ?", (recipient_id,))
        rrow = cur.fetchone()
        if not srow or not rrow:
            conn.rollback()
            return False, "not_found"

        # کسر از فرستنده فقط در صورت کفایت
        cur.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, sender_id, amount)
        )
        if cur.rowcount != 1:
            conn.rollback()
            return False, "insufficient"

        # افزودن به گیرنده
        cur.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, recipient_id)
        )

        conn.commit()
        return True, "ok"
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False, "error"


def _create_gift_code_from_balance(user_id: int, amount: float, tries: int = 6) -> str | None:
    """
    ساخت کد هدیه به‌صورت اتمیک: درج کد + کسر موجودی در یک تراکنش.
    در صورت موفقیت، کد را برمی‌گرداند؛ در غیر این صورت None.
    """
    conn = db._connect_db()
    cur = conn.cursor()
    try:
        conn.execute("BEGIN")
        # کفایت موجودی
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if not row or float(row["balance"] or 0) < float(amount):
            conn.rollback()
            return None

        code = None
        for _ in range(max(1, int(tries))):
            candidate = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            try:
                cur.execute("INSERT INTO gift_codes (code, amount, is_used) VALUES (?, ?, 0)", (candidate, amount))
                code = candidate
                break
            except sqlite3.IntegrityError:
                continue  # تصادم کد؛ دوباره امتحان کن

        if not code:
            conn.rollback()
            return None

        # کسر موجودی با گارد کفایت
        cur.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, user_id, amount)
        )
        if cur.rowcount != 1:
            conn.rollback()
            return None

        conn.commit()
        return code
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None


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
        recipient_id = int(str(update.message.text).strip().translate(_PERSIAN_TO_EN))
        if recipient_id == update.effective_user.id:
            await update.message.reply_text("❌ نمی‌توانید به خودتان موجودی منتقل کنید.")
            return TRANSFER_RECIPIENT_ID

        recipient = db.get_user(recipient_id)
        if not recipient:
            await update.message.reply_text("❌ کاربری با این شناسه یافت نشد.")
            return TRANSFER_RECIPIENT_ID

        context.user_data['transfer_recipient_id'] = recipient_id
        uname = recipient.get('username') or str(recipient_id)
        await update.message.reply_text(
            f"گیرنده: `{uname}`\n\n"
            "مبلغ (تومان) را وارد کنید:",
            parse_mode="Markdown"
        )
        return TRANSFER_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ لطفاً شناسه عددی معتبر وارد کنید.")
        return TRANSFER_RECIPIENT_ID


async def transfer_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw = _normalize_amount_text(update.message.text)
        amount = float(raw)
        sender = db.get_user(update.effective_user.id)
        if not sender:
            await update.message.reply_text("❌ خطا در بازیابی اطلاعات شما. لطفاً مجدداً تلاش کنید.")
            return ConversationHandler.END

        if amount <= 0:
            await update.message.reply_text("❌ مبلغ باید بزرگ‌تر از صفر باشد.")
            return TRANSFER_AMOUNT
        if float(sender['balance'] or 0) < amount:
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
        uname = recipient.get('username') or str(recipient_id)
        await update.message.reply_text(
            f"آیا از انتقال **{utils.format_toman(amount, persian_digits=True)}** "
            f"به کاربر `{uname}` مطمئن هستید؟",
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
        _cleanup_transfer_state(context)
        return ConversationHandler.END

    amount = float(context.user_data.get('transfer_amount', 0))
    recipient_id = int(context.user_data.get('transfer_recipient_id'))
    sender_id = q.from_user.id

    ok, reason = _transfer_balance_atomic(sender_id, recipient_id, amount)
    if not ok:
        if reason == "insufficient":
            await q.edit_message_text("❌ موجودی شما کافی نیست یا هم‌زمان تغییر کرده است. لطفاً دوباره تلاش کنید.")
        elif reason == "not_found":
            await q.edit_message_text("❌ کاربر مقصد یافت نشد.")
        else:
            await q.edit_message_text("❌ انتقال با خطا مواجه شد. لطفاً بعداً دوباره تلاش کنید.")
        _cleanup_transfer_state(context)
        return ConversationHandler.END

    await q.edit_message_text("✅ انتقال با موفقیت انجام شد.")
    try:
        await context.bot.send_message(
            recipient_id,
            f"🎁 مبلغ {utils.format_toman(amount, persian_digits=True)} به حساب شما واریز شد."
        )
    except Exception:
        pass

    _cleanup_transfer_state(context)
    return ConversationHandler.END


async def transfer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _cleanup_transfer_state(context)
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
        raw = _normalize_amount_text(update.message.text)
        amount = float(raw)
        user = db.get_user(update.effective_user.id)
        if not user:
            await update.message.reply_text("❌ خطا در بازیابی اطلاعات شما. لطفاً مجدداً تلاش کنید.")
            return ConversationHandler.END

        if amount <= 0:
            await update.message.reply_text("❌ مبلغ باید بزرگ‌تر از صفر باشد.")
            return GIFT_FROM_BALANCE_AMOUNT
        if float(user['balance'] or 0) < amount:
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
        _cleanup_gift_state(context)
        return ConversationHandler.END

    amount = float(context.user_data.get('gift_amount', 0))
    user_id = q.from_user.id

    code = _create_gift_code_from_balance(user_id, amount)
    if not code:
        await q.edit_message_text("❌ ساخت کد هدیه ناموفق بود. لطفاً بعداً تلاش کنید.")
        _cleanup_gift_state(context)
        return ConversationHandler.END

    await q.edit_message_text(
        f"✅ کد هدیه با موفقیت ساخته شد:\n\n`{code}`\n\nاین کد را برای دوستان خود ارسال کنید.",
        parse_mode="Markdown"
    )
    _cleanup_gift_state(context)
    return ConversationHandler.END


async def create_gift_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _cleanup_gift_state(context)
    await update.message.reply_text("عملیات ساخت کد هدیه لغو شد.")
    await show_account_info(update, context)
    return ConversationHandler.END