# -*- coding: utf-8 -*-

import re
import asyncio
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup
from bot.constants import (
    MANAGE_USER_ID, MANAGE_USER_ACTION, MANAGE_USER_AMOUNT, CMD_CANCEL,
    BTN_BACK_TO_ADMIN_MENU, BROADCAST_MENU, BROADCAST_MESSAGE, BROADCAST_CONFIRM,
    BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE
)
from bot.keyboards import get_admin_menu_keyboard
import database as db
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError

# -------------------- User management --------------------
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
    ban_text = "آزاد کردن کاربر" if info['is_banned'] else "مسدود کردن کاربر"
    keyboard = [["افزایش موجودی", "کاهش موجودی"], ["📜 سوابق خرید", ban_text], [BTN_BACK_TO_ADMIN_MENU]]
    text = (
        f"👤 کاربر: `{info['user_id']}`\n"
        f"یوزرنیم: @{info.get('username', 'N/A')}\n"
        f"💰 موجودی: {info['balance']:.0f} تومان\n"
        f"وضعیت: {'مسدود' if info['is_banned'] else 'فعال'}"
    )
    await update.message.reply_text(text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True), parse_mode="Markdown")
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
        update.message.text = str(target)
        return await manage_user_id_received(update, context)
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
        update.message.text = str(target)
        return await manage_user_id_received(update, context)
    except (ValueError, TypeError):
        await update.message.reply_text("لطفاً مبلغ را به صورت عدد وارد کنید.")
        return MANAGE_USER_AMOUNT

# -------------------- Admin charge review (from receipts) --------------------
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
    try:
        await q.edit_message_caption(caption=feedback, reply_markup=None, parse_mode="Markdown")
    except Exception:
        await context.bot.send_message(chat_id=q.from_user.id, text=feedback, parse_mode="Markdown")

# -------------------- Broadcast --------------------
async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["ارسال به همه کاربران", "ارسال به کاربر خاص"], [BTN_BACK_TO_ADMIN_MENU]]
    await update.message.reply_text("بخش ارسال پیام", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return BROADCAST_MENU

# ارسال همگانی
async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "متن/رسانه پیام برای ارسال به همه کاربران را ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True)
    )
    return BROADCAST_MESSAGE

async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ذخیره هر نوع پیام برای کپی
    context.user_data['broadcast_message'] = update.message
    users = db.get_all_user_ids()
    await update.message.reply_text(
        f"آیا از ارسال این پیام به {len(users)} کاربر مطمئن هستید؟",
        reply_markup=ReplyKeyboardMarkup([["بله، ارسال کن"], ["خیر، لغو کن"]], resize_keyboard=True)
    )
    return BROADCAST_CONFIRM

async def broadcast_confirm_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = (update.message.text or "").strip()
    if choice == "بله، ارسال کن":
        return await broadcast_to_all_send(update, context)
    elif choice == "خیر، لغو کن":
        context.user_data.clear()
        await update.message.reply_text("ارسال همگانی لغو شد.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END
    else:
        await update.message.reply_text("لطفاً یکی از گزینه‌ها را انتخاب کنید: «بله، ارسال کن» یا «خیر، لغو کن».")
        return BROADCAST_CONFIRM

async def broadcast_to_all_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = context.user_data.get('broadcast_message')
    if not msg:
        await update.message.reply_text("خطا: پیامی برای ارسال یافت نشد.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END

    user_ids = db.get_all_user_ids()
    sent, failed = 0, 0
    await update.message.reply_text(f"در حال ارسال پیام به {len(user_ids)} کاربر... ⏳")

    for uid in user_ids:
        try:
            # استفاده از Bot.copy_message (سازگار با PTB)
            await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            sent += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
                sent += 1
            except Exception:
                failed += 1
        except (Forbidden, BadRequest, TimedOut, NetworkError):
            failed += 1
            # کمی مکث برای خطاهای موقتی شبکه
            await asyncio.sleep(0.2)
        except Exception:
            failed += 1

        # رعایت ریت‌لیمیت
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ ارسال پیام همگانی پایان یافت.\n\nارسال موفق: {sent}\nارسال ناموفق: {failed}",
        reply_markup=get_admin_menu_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ارسال به کاربر خاص
async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("آیدی عددی کاربر هدف را وارد کنید:", reply_markup=ReplyKeyboardMarkup([[CMD_CANCEL]], resize_keyboard=True))
    return BROADCAST_TO_USER_ID

async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        if target_id <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("لطفاً یک آیدی عددی معتبر وارد کنید.")
        return BROADCAST_TO_USER_ID

    context.user_data['target_user_id'] = target_id
    await update.message.reply_text("شناسه ثبت شد. حالا پیام مورد نظر را (متن/رسانه) ارسال کنید:")
    return BROADCAST_TO_USER_MESSAGE

async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = context.user_data.get('target_user_id')
    if not target_id:
        await update.message.reply_text("خطا: کاربر هدف مشخص نیست.", reply_markup=get_admin_menu_keyboard())
        return ConversationHandler.END

    msg = update.message
    try:
        await context.bot.copy_message(chat_id=target_id, from_chat_id=msg.chat.id, message_id=msg.message_id)
        await update.message.reply_text("✅ پیام با موفقیت ارسال شد.", reply_markup=get_admin_menu_keyboard())
    except (Forbidden, BadRequest):
        await update.message.reply_text("❌ ارسال ناموفق بود. احتمالاً کاربر ربات را مسدود کرده یا آیدی اشتباه است.", reply_markup=get_admin_menu_keyboard())
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        try:
            await context.bot.copy_message(chat_id=target_id, from_chat_id=msg.chat.id, message_id=msg.message_id)
            await update.message.reply_text("✅ پیام با موفقیت ارسال شد.", reply_markup=get_admin_menu_keyboard())
        except Exception:
            await update.message.reply_text("❌ ارسال ناموفق بود.", reply_markup=get_admin_menu_keyboard())

    context.user_data.clear()
    return ConversationHandler.END