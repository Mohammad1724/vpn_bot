# -*- coding: utf-8 -*-

import re
import logging
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup
from telegram.error import Forbidden, BadRequest

from bot.constants import (
    MANAGE_USER_ID, MANAGE_USER_ACTION, MANAGE_USER_AMOUNT, CMD_CANCEL,
    BTN_BACK_TO_ADMIN_MENU
)
from bot.keyboards import get_admin_menu_keyboard
import database as db


async def _send_user_panel(update: Update, target_id: int):
    info = db.get_user(target_id)
    if not info:
        await update.message.reply_text("کاربر یافت نشد.")
        return
    ban_text = "آزاد کردن کاربر" if info['is_banned'] else "مسدود کردن کاربر"
    keyboard = [["افزایش موجودی", "کاهش موجودی"], ["📜 سوابق خرید", ban_text], [BTN_BACK_TO_ADMIN_MENU]]
    text = (
        f"👤 کاربر: `{info['user_id']}`\n"
        f"یوزرنیم: @{info.get('username', 'N/A')}\n"
        f"💰 موجودی: {info['balance']:.0f} تومان\n"
        f"وضعیت: {'مسدود' if info['is_banned'] else 'فعال'}"
    )
    await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown")


async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "آیدی عددی یا یوزرنیم تلگرام (با یا بدون @) کاربر مورد نظر را وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return MANAGE_USER_ID


async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    info = None
    if user_input.isdigit():
        info = db.get_user(int(user_input))
    elif re.fullmatch(r'@?[A-Za-z0-9_]{5,32}', user_input):
        info = db.get_user_by_username(user_input)
    else:
        await update.message.reply_text("ورودی نامعتبر است. یک آیدی عددی یا یوزرنیم صحیح وارد کنید.")
        return MANAGE_USER_ID

    if not info:
        await update.message.reply_text("کاربری با این مشخصات یافت نشد.")
        return MANAGE_USER_ID

    context.user_data['target_user_id'] = info['user_id']
    await _send_user_panel(update, info['user_id'])
    return MANAGE_USER_ACTION


async def manage_user_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    target = context.user_data.get('target_user_id')
    if not target:
        await update.message.reply_text("خطا: کاربر هدف مشخص نیست.")
        return await user_management_menu(update, context)

    if action in ["افزایش موجودی", "کاهش موجودی"]:
        context.user_data['manage_action'] = action
        await update.message.reply_text("مبلغ (تومان) را وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
        return MANAGE_USER_AMOUNT

    elif "مسدود" in action or "آزاد" in action:
        info = db.get_user(target)
        new_status = not info['is_banned']
        db.set_user_ban_status(target, new_status)
        await update.message.reply_text(f"✅ وضعیت کاربر به {'مسدود' if new_status else 'فعال'} تغییر کرد.")
        await _send_user_panel(update, target)
        return MANAGE_USER_ACTION

    elif action == "📜 سوابق خرید":
        history = db.get_user_sales_history(target)
        if not history:
            await update.message.reply_text("این کاربر تاکنون خریدی نداشته است.")
            return MANAGE_USER_ACTION
        msg = "📜 سوابق خرید کاربر:\n\n"
        from datetime import datetime
        for sale in history:
            sale_date = datetime.strptime(sale['sale_date'], '%Y-%m-%d %H:%M:%S').strftime('%Y/%m/%d - %H:%M')
            msg += f"🔹 {sale['plan_name'] or 'پلن حذف شده'} | قیمت: {sale['price']:.0f} تومان | تاریخ: {sale_date}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return MANAGE_USER_ACTION

    else:
        await update.message.reply_text("دستور نامعتبر است. از دکمه‌ها استفاده کنید.")
        return MANAGE_USER_ACTION


async def manage_user_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        action = context.user_data['manage_action']
        target = context.user_data['target_user_id']
        is_add = action == "افزایش موجودی"
        db.update_balance(target, amount if is_add else -amount)
        await update.message.reply_text(f"✅ مبلغ {amount:.0f} تومان از حساب کاربر {'کسر' if not is_add else 'افزوده'} شد.")

        # ارسال اطلاعیه به کاربر
        try:
            if is_add:
                await context.bot.send_message(
                    chat_id=target,
                    text=f"💳 حساب شما به مبلغ **{amount:,.0f} تومان** توسط ادمین شارژ شد.",
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=target,
                    text=f"💳 مبلغ **{amount:,.0f} تومان** توسط ادمین از حساب شما کسر شد.",
                    parse_mode="Markdown"
                )
        except (Forbidden, BadRequest) as e:
            logger = logging.getLogger(__name__)
            logger.warning("Failed to send charge notification to user %s: %s", target, e)
            await update.message.reply_text("⚠️ کاربر ربات را مسدود کرده و پیام را دریافت نکرد.")

        await _send_user_panel(update, target)
        return MANAGE_USER_ACTION
    except (ValueError, TypeError):
        await update.message.reply_text("لطفاً مبلغ را به صورت عدد وارد کنید.")
        return MANAGE_USER_AMOUNT


async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    prefix = "admin_confirm_charge_"
    try:
        data_part = q.data[len(prefix):]
        user_id_str, amount_str = data_part.split('_', 1)
        target_user_id = int(user_id_str)
        amount = int(float(amount_str))
    except Exception:
        if q.message:
            try:
                if q.message.photo:
                    await q.edit_message_caption(caption=f"{q.message.caption}\n\n---\n❌ خطا در پردازش داده دکمه.")
                else:
                    await q.edit_message_text("❌ خطا در پردازش داده دکمه.")
            except Exception:
                pass
        return

    db.update_balance(target_user_id, amount)
    original_caption = q.message.caption or ""
    feedback = f"{original_caption}\n\n---\n✅ مبلغ {amount:,} تومان به حساب کاربر `{target_user_id}` اضافه شد."
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"حساب شما به مبلغ **{amount:,} تومان** شارژ شد!", parse_mode="Markdown")
    except (Forbidden, BadRequest):
        feedback += "\n\n⚠️ کاربر ربات را بلاک کرده و پیام تایید را دریافت نکرد."
    if q.message:
        try:
            await q.edit_message_caption(caption=feedback, reply_markup=None, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=q.from_user.id, text=feedback, parse_mode="Markdown")


async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        target_user_id = int(q.data.split('_')[-1])
    except Exception:
        if q.message:
            try:
                if q.message.photo:
                    await q.edit_message_caption(caption=f"{q.message.caption}\n\n---\n❌ خطا در پردازش داده دکمه.")
                else:
                    await q.edit_message_text("❌ خطا در پردازش داده دکمه.")
            except Exception:
                pass
        return

    original_caption = q.message.caption or ""
    feedback = f"{original_caption}\n\n---\n❌ درخواست شارژ کاربر `{target_user_id}` رد شد."
    try:
        await context.bot.send_message(chat_id=target_user_id, text="متاسفانه درخواست شارژ حساب شما توسط ادمین رد شد.")
    except (Forbidden, BadRequest):
        feedback += "\n\n⚠️ کاربر ربات را بلاک کرده است."
    if q.message:
        try:
            await q.edit_message_caption(caption=feedback, reply_markup=None, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=q.from_user.id, text=feedback, parse_mode="Markdown")