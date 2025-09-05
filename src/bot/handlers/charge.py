# -*- coding: utf-8 -*-

import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

import database as db
from config import ADMIN_ID, SUPPORT_USERNAME, REFERRAL_BONUS_AMOUNT
from bot.constants import CHARGE_AMOUNT, CHARGE_RECEIPT
from bot.ui import nav_row, btn, markup  # UI helpers
from bot.keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)


def _get_payment_info_text() -> str:
    """متن راهنمای پرداخت را از دیتابیس می‌خواند."""
    text = db.get_setting("payment_instruction_text")
    if not text:
        text = "راهنمای پرداخت هنوز تنظیم نشده است."

    # اضافه کردن شماره کارت‌ها
    card_lines = []
    for i in range(1, 4):
        num = db.get_setting(f"payment_card_{i}_number")
        name = db.get_setting(f"payment_card_{i}_name")
        bank = db.get_setting(f"payment_card_{i}_bank")
        if num and name:
            card_lines.append(f"💳 `{num}`\n({name} - {bank or 'نامشخص'})")

    if card_lines:
        text += "\n\n" + "\n".join(card_lines)

    return text


# --- Handlers ---
async def charge_menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش منوی اصلی شارژ با دو گزینه: شارژ رایگان و شارژ حساب
    """
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()

    keyboard = [
        [btn("💰 شارژ رایگان (معرفی دوستان)", "acc_referral")],
        [btn("💳 شارژ حساب (واریز)", "charge_start_payment")],
        nav_row(home_cb="home_menu")
    ]

    text = "**💳 شارژ حساب**\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:"

    if q:
        try:
            await q.edit_message_text(text, reply_markup=markup(keyboard), parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=markup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup(keyboard), parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END


async def charge_start_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    شروع فرآیند پرداخت پس از انتخاب «شارژ حساب»
    """
    q = update.callback_query
    await q.answer()

    keyboard = [
        [btn("۵۰,۰۰۰ تومان", "charge_amount_50000"), btn("۱۰۰,۰۰۰ تومان", "charge_amount_100000")],
        [btn("۲۰۰,۰۰۰ تومان", "charge_amount_200000"), btn("۵۰۰,۰۰۰ تومان", "charge_amount_500000")],
        nav_row(back_cb="charge_menu_main", home_cb="home_menu")
    ]

    text = (
        "**💳 شارژ حساب**\n\n"
        "لطفاً یکی از مبالغ زیر را انتخاب کنید، یا مبلغ دلخواه خود را (به تومان) وارد نمایید."
    )

    await q.edit_message_text(text, reply_markup=markup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return CHARGE_AMOUNT


async def show_referral_info_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش اطلاعات معرفی دوستان
    """
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    bonus_str = db.get_setting('referral_bonus_amount')
    try:
        bonus = int(float(bonus_str)) if bonus_str is not None else REFERRAL_BONUS_AMOUNT
    except (ValueError, TypeError):
        bonus = REFERRAL_BONUS_AMOUNT

    text = (
        f"**💰 شارژ رایگان**\n\n"
        f"با لینک اختصاصی زیر دوستان خود را دعوت کنید:\n"
        f"`{referral_link}`\n\n"
        f"با اولین خرید دوست شما، مبلغ **{bonus:,.0f} تومان** به کیف پول شما و **{bonus:,.0f} تومان** به کیف پول دوستتان اضافه می‌شود."
    )

    kb = [nav_row(back_cb="charge_menu_main", home_cb="home_menu")]
    await q.edit_message_text(text, reply_markup=markup(kb), parse_mode=ParseMode.MARKDOWN)


async def charge_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(float(update.message.text.replace(',', '')))
        if amount < 1000:
            await update.message.reply_text("مبلغ باید حداقل ۱,۰۰۰ تومان باشد.")
            return CHARGE_AMOUNT
        context.user_data['charge_amount'] = amount
        return await _confirm_amount(update, context, amount)
    except (ValueError, TypeError):
        await update.message.reply_text("لطفاً مبلغ را به صورت عدد (تومان) وارد کنید.")
        return CHARGE_AMOUNT


async def charge_amount_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    amount_str = q.data.split('_')[-1]
    amount = int(amount_str)
    context.user_data['charge_amount'] = amount
    return await _confirm_amount(update, context, amount)


async def _confirm_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
    q = getattr(update, "callback_query", None)

    payment_info = _get_payment_info_text()
    text = (
        f"شما درخواست شارژ به مبلغ **{amount:,.0f} تومان** را دارید.\n\n"
        f"{payment_info}\n\n"
        "لطفاً پس از واریز، **عکس رسید** را ارسال نمایید."
    )

    if q:
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    return CHARGE_RECEIPT


async def charge_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get('charge_amount')
    if not amount:
        await update.message.reply_text("خطا: مبلغ شارژ یافت نشد. لطفاً از ابتدا شروع کنید.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
        return ConversationHandler.END

    user = update.effective_user
    username = f"@{user.username}" if user.username else "ندارد"
    charge_id = db.create_charge_request(user.id, amount, note=f"From user: {user.id}")

    if not charge_id:
        await update.message.reply_text("❌ خطایی در ثبت درخواست شما رخ داد. لطفاً به پشتیبانی اطلاع دهید.", reply_markup=get_main_menu_keyboard(user.effective_user.id))
        return ConversationHandler.END

    caption = (
        f"💰 درخواست شارژ جدید\n\n"
        f"کاربر: {user.full_name}\n"
        f"آیدی: `{user.id}`\n"
        f"یوزرنیم: {username}\n"
        f"مبلغ: **{amount:,.0f} تومان**"
    )

    kb = InlineKeyboardMarkup([
        [
            btn("✅ تایید شارژ", f"admin_confirm_charge_{charge_id}_{user.id}_{amount}"),
            btn("❌ رد درخواست", f"admin_reject_charge_{charge_id}_{user.id}")
        ]
    ])

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=caption,
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )

    await update.message.reply_text(
        "✅ رسید شما دریافت شد. پس از تایید توسط ادمین، حساب شما شارژ خواهد شد.\n"
        "می‌توانید از طریق پشتیبانی پیگیری کنید.",
        reply_markup=get_main_menu_keyboard(user.id)
    )
    context.user_data.clear()
    return ConversationHandler.END