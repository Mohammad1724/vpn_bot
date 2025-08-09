# -*- coding: utf-8 -*-

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from bot.keyboards import get_admin_menu_keyboard
from bot.constants import AWAIT_SETTING_VALUE, CMD_CANCEL
import database as db
from config import REFERRAL_BONUS_AMOUNT

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number = db.get_setting('card_number') or "تنظیم نشده"
    card_holder = db.get_setting('card_holder') or "تنظیم نشده"
    referral_bonus = db.get_setting('referral_bonus_amount') or str(REFERRAL_BONUS_AMOUNT)
    text = (
        f"⚙️ تنظیمات ربات\n\n"
        f"شماره کارت: `{card_number}`\n"
        f"صاحب حساب: `{card_holder}`\n"
        f"هدیه معرفی (تومان): `{referral_bonus}`\n\n"
        "برای تغییر هر مورد، از دکمه‌ها استفاده کنید."
    )
    kb = [
        [InlineKeyboardButton("ویرایش شماره کارت", callback_data="admin_edit_setting_card_number"),
         InlineKeyboardButton("ویرایش نام صاحب حساب", callback_data="admin_edit_setting_card_holder")],
        [InlineKeyboardButton("ویرایش مبلغ هدیه معرفی", callback_data="admin_edit_setting_referral_bonus_amount")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return ConversationHandler.END

async def edit_setting_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key = q.data.split('admin_edit_setting_')[-1]
    context.user_data['setting_to_edit'] = key
    prompts = {
        'card_number': "شماره کارت جدید را وارد کنید:",
        'card_holder': "نام جدید صاحب حساب را وارد کنید:",
        'referral_bonus_amount': "مبلغ هدیه معرفی (تومان) را وارد کنید:"
    }
    text = prompts.get(key)
    if not text:
        await q.message.edit_text("تنظیمات ناشناخته.")
        return ConversationHandler.END
    await q.message.reply_text(text, reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return AWAIT_SETTING_VALUE

async def setting_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get('setting_to_edit')
    if not key:
        await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END
    value = update.message.text.strip()
    if key == 'referral_bonus_amount':
        try:
            value = str(int(float(value)))
        except (ValueError, TypeError):
            await update.message.reply_text("لطفاً مبلغ را به صورت عدد صحیح وارد کنید (مثلاً 5000).")
            return AWAIT_SETTING_VALUE
    db.set_setting(key, value)
    await update.message.reply_text("✅ تنظیمات با موفقیت به‌روزرسانی شد.", reply_markup=get_admin_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END