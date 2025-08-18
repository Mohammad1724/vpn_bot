# -*- coding: utf-8 -*-

import re
import logging
import asyncio
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.constants import ParseMode

from bot.constants import (
    USER_MANAGEMENT_MENU, BTN_BACK_TO_ADMIN_MENU,
    BROADCAST_MENU, BROADCAST_MESSAGE, BROADCAST_CONFIRM,
    BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE
)
import database as db
import hiddify_api

logger = logging.getLogger(__name__)

# -------------------------------
# منوی مدیریت کاربران (ورود)
# -------------------------------
def _user_mgmt_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)

async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text(
        "بخش مدیریت کاربران\n\n"
        "شناسه عددی کاربر را ارسال کنید.",
        reply_markup=_user_mgmt_keyboard()
    )
    return USER_MANAGEMENT_MENU

# -------------------------------
# نمایش پنل خلاصه کاربر
# -------------------------------
async def _send_user_panel(update: Update, target_id: int):
    em = update.effective_message
    info = db.get_user(target_id)
    if not info:
        await em.reply_text("❌ کاربر یافت نشد.", reply_markup=_user_mgmt_keyboard())
        return

    try:
        services = db.get_user_services(target_id) or []
    except Exception:
        services = []

    ban_state = bool(info.get('is_banned'))
    ban_text = "آزاد کردن کاربر" if ban_state else "مسدود کردن کاربر"

    text = (
        f"👤 شناسه: {target_id}\n"
        f"👥 نام کاربری: {info.get('username') or '-'}\n"
        f"💰 موجودی: {int(info.get('balance', 0)):,} تومان\n"
        f"🧪 تست: {'استفاده کرده' if info.get('has_used_trial') else 'آزاد'}\n"
        f"🚫 وضعیت: {'مسدود' if ban_state else 'آزاد'}\n"
        f"📋 تعداد سرویس‌ها: {len(services)}"
    )
    # اینجا فقط اطلاعات را نمایش می‌دهیم؛ اکشن‌ها را در صورت نیاز می‌توان به شکل اینلاین اضافه کرد
    await em.reply_text(text, reply_markup=_user_mgmt_keyboard())

# دریافت شناسه عددی و نمایش پنل
async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    text = (em.text or "").strip()
    if not re.fullmatch(r"\d+", text):
        await em.reply_text("شناسه معتبر نیست. یک عدد مثبت وارد کنید.", reply_markup=_user_mgmt_keyboard())
        return USER_MANAGEMENT_MENU

    target_id = int(text)
    if target_id <= 0:
        await em.reply_text("شناسه معتبر نیست. یک عدد مثبت وارد کنید.", reply_markup=_user_mgmt_keyboard())
        return USER_MANAGEMENT_MENU

    await _send_user_panel(update, target_id)
    return USER_MANAGEMENT_MENU

# -------------------------------
# حذف سرویس از سمت ادمین (کالبک)
# -------------------------------
async def admin_delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        service_id = int(q.data.split('_')[-1])
    except Exception:
        await q.edit_message_text("❌ شناسه سرویس نامعتبر است.")
        return

    svc = db.get_service(service_id)
    if not svc:
        await q.edit_message_text("❌ سرویس یافت نشد.")
        return

    await q.edit_message_text("در حال حذف سرویس از پنل...")
    success = await hiddify_api.delete_user_from_panel(svc['sub_uuid'])
    if success:
        db.delete_service(service_id)
        await q.edit_message_text(f"✅ سرویس {svc.get('name') or service_id} با موفقیت از پنل و ربات حذف شد.")
    else:
        await q.edit_message_text("❌ حذف سرویس از پنل ناموفق بود.")

# -------------------------------
# ارسال پیام (Broadcast)
# -------------------------------
def _broadcast_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["ارسال به همه کاربران", "ارسال به کاربر خاص"], [BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text("بخش ارسال پیام", reply_markup=_broadcast_menu_keyboard())
    return BROADCAST_MENU

async def broadcast_to_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["broadcast_mode"] = "all"
    await update.effective_message.reply_text(
        "متن/رسانه پیام همگانی را بفرستید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return BROADCAST_MESSAGE

async def broadcast_to_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['broadcast_message'] = update.effective_message
    total_users = db.get_all_user_ids()
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تایید ارسال", callback_data="broadcast_confirm_yes"),
        InlineKeyboardButton("❌ انصراف", callback_data="broadcast_confirm_no")
    ]])
    await update.effective_message.reply_text(
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
        try:
            await q.edit_message_text("خطا: پیامی برای ارسال یافت نشد.", reply_markup=None)
        except Exception:
            pass
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

async def broadcast_to_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["broadcast_mode"] = "single"
    await update.effective_message.reply_text(
        "شناسه عددی کاربر را بفرستید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return BROADCAST_TO_USER_ID

async def broadcast_to_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int((update.effective_message.text or "").strip())
        assert uid > 0
    except Exception:
        await update.effective_message.reply_text("شناسه معتبر نیست. یک عدد مثبت بفرستید.")
        return BROADCAST_TO_USER_ID

    context.user_data["target_user_id"] = uid
    await update.effective_message.reply_text(
        "متن/رسانه پیام را بفرستید:",
        reply_markup=ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)
    )
    return BROADCAST_TO_USER_MESSAGE

async def broadcast_to_user_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = context.user_data.get("target_user_id")
    if not uid:
        await update.effective_message.reply_text("شناسه کاربر مشخص نیست.")
        context.user_data.clear()
        return ConversationHandler.END

    msg = update.effective_message
    try:
        await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat.id, message_id=msg.message_id)
        await update.effective_message.reply_text("✅ پیام برای کاربر ارسال شد.")
    except Exception:
        await update.effective_message.reply_text("❌ ارسال ناموفق بود. احتمالاً کاربر بات را مسدود کرده یا آیدی اشتباه است.")
    context.user_data.clear()
    return ConversationHandler.END

# -------------------------------
# Callbacks تایید/رد شارژ (در صورت استفاده در پروژه)
# -------------------------------
async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید شارژ کاربر (در صورت وجود این فلو در پروژه)"""
    q = update.callback_query
    await q.answer()
    try:
        charge_id = int(q.data.split('_')[-1])
    except Exception:
        await q.edit_message_text("❌ شناسه شارژ نامعتبر است.")
        return
    # تلاش برای فراخوانی توابع دیتابیس اگر موجود باشند
    try:
        if hasattr(db, "confirm_charge_request"):
            ok = db.confirm_charge_request(charge_id)
        elif hasattr(db, "admin_confirm_charge"):
            ok = db.admin_confirm_charge(charge_id)
        else:
            ok = False
    except Exception:
        ok = False
    if ok:
        await q.edit_message_text("✅ شارژ تایید شد.")
    else:
        await q.edit_message_text("❌ تایید شارژ ناموفق بود یا قبلاً پردازش شده است.")

async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رد شارژ کاربر (در صورت وجود این فلو در پروژه)"""
    q = update.callback_query
    await q.answer()
    try:
        charge_id = int(q.data.split('_')[-1])
    except Exception:
        await q.edit_message_text("❌ شناسه شارژ نامعتبر است.")
        return
    try:
        if hasattr(db, "reject_charge_request"):
            ok = db.reject_charge_request(charge_id)
        elif hasattr(db, "admin_reject_charge"):
            ok = db.admin_reject_charge(charge_id)
        else:
            ok = False
    except Exception:
        ok = False
    if ok:
        await q.edit_message_text("✅ شارژ رد شد.")
    else:
        await q.edit_message_text("❌ رد شارژ ناموفق بود یا قبلاً پردازش شده است.")