# -*- coding: utf-8 -*-

import re
import logging
import asyncio
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError

from bot.constants import (
    MANAGE_USER_ID, MANAGE_USER_ACTION, MANAGE_USER_AMOUNT, CMD_CANCEL,
    BTN_BACK_TO_ADMIN_MENU,
    BROADCAST_MENU, BROADCAST_MESSAGE, BROADCAST_CONFIRM,
    BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE
)
from bot.keyboards import get_admin_menu_keyboard
import database as db

logger = logging.getLogger(__name__)

# =============== User Management (Admin) ===============

async def _send_user_panel(update: Update, target_id: int):
    """ساخت و ارسال پنل کاربر (برای ادمین)"""
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
    """ورود به بخش مدیریت کاربران: گرفتن آیدی یا یوزرنیم"""
    await update.message.reply_text(
        "آیدی عددی یا یوزرنیم تلگرام (با یا بدون @) کاربر مورد نظر را وارد کنید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return MANAGE_USER_ID


async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت آیدی یا یوزرنیم و نمایش پنل کاربر"""
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
    """هندل‌کننده اکشن‌های ادمین روی کاربر"""
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
    """دریافت مبلغ و اعمال شارژ/کسر برای کاربر"""
    try:
        amount = float(update.message.text)
        action = context.user_data['manage_action']
        target = context.user_data['target_user_id']
        is_add = action == "افزایش موجودی"

        # ثبت تراکنش برای تاریخچه شارژ
        if is_add:
            db.add_charge_transaction(target, amount, type_="manual_charge_add")
        else:
            db.add_charge_transaction(target, -amount, type_="manual_charge_sub")

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
            logger.warning("Failed to send charge notification to user %s: %s", target, e)
            await update.message.reply_text("⚠️ کاربر ربات را مسدود کرده و پیام را دریافت نکرد.")

        await _send_user_panel(update, target)
        return MANAGE_USER_ACTION
    except (ValueError, TypeError):
        await update.message.reply_text("لطفاً مبلغ را به صورت عدد وارد کنید.")
        return MANAGE_USER_AMOUNT


async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید شارژ رسید کاربر از سوی ادمین (دکمه اینلاین)"""
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

    # ثبت تراکنش برای تاریخچه شارژ
    db.add_charge_transaction(target_user_id, amount, type_="charge")
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
    """رد شارژ رسید کاربر از سوی ادمین (دکمه اینلاین)"""
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


# =============== Broadcast (Admin) ===============

def _broadcast_menu_keyboard():
    return ReplyKeyboardMarkup(
        [["ارسال به همه کاربران", "ارسال به کاربر خاص"], [BTN_BACK_TO_ADMIN_MENU]],
        resize_keyboard=True
    )

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("بخش ارسال پیام", reply_markup=_broadcast_menu_keyboard())
    return BROADCAST_MENU

# --- Broadcast to all users ---
async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["broadcast_mode"] = "all"
    await update.message.reply_text(
        "متن/رسانه پیام همگانی را بفرستید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return BROADCAST_MESSAGE

async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.message
    total_users = db.get_all_user_ids()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید ارسال", callback_data="broadcast_confirm_yes"),
         InlineKeyboardButton("❌ انصراف", callback_data="broadcast_confirm_no")]
    ])
    await update.message.reply_text(
        f"پیش‌نمایش ثبت شد. ارسال به {len(total_users)} کاربر انجام شود؟",
        reply_markup=keyboard
    )
    return BROADCAST_CONFIRM

async def broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.endswith("no"):
        try:
            await q.edit_message_text("ارسال همگانی لغو شد.", reply_markup=None)
        except Exception:
            pass
        context.user_data.clear()
        return ConversationHandler.END

    msg = context.user_data.get("broadcast_message")
    if not msg:
        await q.edit_message_text("خطا: پیامی برای ارسال یافت نشد.", reply_markup=None)
        context.user_data.clear()
        return ConversationHandler.END

    user_ids = db.get_all_user_ids()
    ok = fail = 0
    try:
        await q.edit_message_text(f"در حال ارسال به {len(user_ids)} کاربر... ⏳", reply_markup=None)
    except Exception:
        pass

    for uid in user_ids:
        try:
            await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
            ok += 1
        except RetryAfter as e:
            await asyncio.sleep(getattr(e, "retry_after", 1) + 1)
            try:
                await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
                ok += 1
            except Exception:
                fail += 1
        except (Forbidden, BadRequest, TimedOut, NetworkError):
            fail += 1
        except Exception as e:
            logger.warning("Broadcast send failed to %s: %s", uid, e)
            fail += 1
        await asyncio.sleep(0.05)

    summary = f"ارسال همگانی تمام شد.\nموفق: {ok}\nناموفق: {fail}\nکل: {len(user_ids)}"
    try:
        await q.edit_message_text(summary, reply_markup=None)
    except Exception:
        await q.from_user.send_message(summary)

    context.user_data.clear()
    return ConversationHandler.END

# --- Broadcast to a specific user ---
async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["broadcast_mode"] = "single"
    await update.message.reply_text(
        "شناسه عددی کاربر را بفرستید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return BROADCAST_TO_USER_ID

async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        if uid <= 0:
            raise ValueError()
    except Exception:
        await update.message.reply_text("شناسه معتبر نیست. یک عدد مثبت بفرستید.")
        return BROADCAST_TO_USER_ID

    context.user_data["target_user_id"] = uid
    await update.message.reply_text("متن/رسانه پیام را بفرستید:", reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True))
    return BROADCAST_TO_USER_MESSAGE

async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = context.user_data.get("target_user_id")
    if not uid:
        await update.message.reply_text("شناسه کاربر مشخص نیست.")
        context.user_data.clear()
        return ConversationHandler.END

    msg = update.message
    try:
        await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
        await update.message.reply_text("✅ پیام برای کاربر ارسال شد.")
    except Exception as e:
        await update.message.reply_text("❌ ارسال ناموفق بود. احتمالاً کاربر بات را مسدود کرده یا آیدی اشتباه است.")
    context.user_data.clear()
    return ConversationHandler.END