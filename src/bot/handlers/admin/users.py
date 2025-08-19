# -*- coding: utf-8 -*-

import re
import logging
import asyncio
from datetime import datetime
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, BadRequest, RetryAfter, TimedOut, NetworkError
from telegram.constants import ParseMode

from bot.constants import (
    USER_MANAGEMENT_MENU, BTN_BACK_TO_ADMIN_MENU,
    BROADCAST_MENU, BROADCAST_MESSAGE, BROADCAST_CONFIRM,
    BROADCAST_TO_USER_ID, BROADCAST_TO_USER_MESSAGE,
    MANAGE_USER_AMOUNT
)
from bot import utils
import database as db
import hiddify_api

logger = logging.getLogger(__name__)

# -------------------------------
# Helpers
# -------------------------------
def _user_mgmt_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[BTN_BACK_TO_ADMIN_MENU]], resize_keyboard=True)

def _action_kb(target_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("➕ افزایش موجودی", callback_data=f"admin_user_addbal_{target_id}"),
            InlineKeyboardButton("➖ کاهش موجودی", callback_data=f"admin_user_subbal_{target_id}"),
        ],
        [
            InlineKeyboardButton("📋 سرویس‌های فعال", callback_data=f"admin_user_services_{target_id}"),
            InlineKeyboardButton("🧾 سوابق خرید", callback_data=f"admin_user_purchases_{target_id}"),
        ],
        [
            InlineKeyboardButton("🧪 ریست سرویس تست", callback_data=f"admin_user_trial_reset_{target_id}"),
            InlineKeyboardButton("🔓 آزاد کردن" if is_banned else "🚫 مسدود کردن", callback_data=f"admin_user_toggle_ban_{target_id}"),
        ],
        [InlineKeyboardButton("🔄 بروزرسانی پنل", callback_data=f"admin_user_refresh_{target_id}")]
    ]
    return InlineKeyboardMarkup(rows)

def _amount_prompt_kb(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data=f"admin_user_amount_cancel_{target_id}")]])

def _sanitize_for_code(s: str) -> str:
    return (s or "").replace("`", "")

async def _render_user_panel_text(target_id: int) -> tuple[str, bool]:
    info = db.get_user(target_id)
    if not info:
        return "❌ کاربر یافت نشد.", False
    try:
        services = db.get_user_services(target_id) or []
    except Exception:
        services = []

    ban_state = bool(info.get('is_banned'))

    username = info.get('username') or "-"
    if username != "-" and not username.startswith("@"):
        username = f"@{username}"
    username = _sanitize_for_code(username)

    text = (
        f"👤 شناسه: `{_sanitize_for_code(str(target_id))}`\n"
        f"👥 نام کاربری: `{username}`\n"
        f"💰 موجودی: {int(info.get('balance', 0)):,} تومان\n"
        f"🧪 تست: {'استفاده کرده' if info.get('has_used_trial') else 'آزاد'}\n"
        f"🚫 وضعیت: {'مسدود' if ban_state else 'آزاد'}\n"
        f"📋 تعداد سرویس‌ها: {len(services)}"
    )
    return text, ban_state

def _ensure_user_exists(user_id: int):
    try:
        if hasattr(db, "get_or_create_user"):
            db.get_or_create_user(user_id)
    except Exception:
        pass

def _update_balance(user_id: int, delta: int) -> bool:
    _ensure_user_exists(user_id)
    try:
        if hasattr(db, "change_balance"):
            db.change_balance(user_id, delta); return True
        if hasattr(db, "update_balance"):
            db.update_balance(user_id, delta); return True
        if delta >= 0 and hasattr(db, "increase_balance"):
            db.increase_balance(user_id, delta); return True
        if delta < 0 and hasattr(db, "decrease_balance"):
            db.decrease_balance(user_id, -delta); return True
        if delta >= 0 and hasattr(db, "add_balance"):
            db.add_balance(user_id, delta); return True
        if hasattr(db, "get_user") and hasattr(db, "set_balance"):
            info = db.get_user(user_id)
            cur = int(info.get("balance", 0)) if info else 0
            new_bal = max(cur + delta, 0)
            db.set_balance(user_id, new_bal); return True
    except Exception as e:
        logger.warning("Balance update failed: %s", e, exc_info=True)
    return False

# -------------------------------
# ورود به منوی مدیریت کاربران
# -------------------------------
async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    await em.reply_text(
        "بخش مدیریت کاربران\n\n"
        "شناسه عددی کاربر را ارسال کنید.",
        reply_markup=_user_mgmt_keyboard()
    )
    return USER_MANAGEMENT_MENU

# نمایش پنل خلاصه کاربر
async def _send_user_panel(update: Update, target_id: int):
    q = getattr(update, "callback_query", None)
    text, ban_state = await _render_user_panel_text(target_id)
    kb = _action_kb(target_id, ban_state)
    if q:
        await q.answer()
        try:
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await q.from_user.send_message(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

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
# اکشن‌های پنل کاربر (کال‌بک‌ها)
# -------------------------------
async def admin_user_refresh_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    await _send_user_panel(update, target_id)

async def admin_user_services_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    target_id = int(q.data.split('_')[-1])
    # فقط لودینگ را ببند، پیام پنل را دست نزن
    await q.answer()

    services = db.get_user_services(target_id) or []
    if not services:
        try:
            await q.from_user.send_message("این کاربر سرویس فعالی ندارد.")
        except Exception:
            pass
        return

    for s in services:
        name = s.get('name') or f"سرویس {s.get('service_id')}"
        sid = s.get('service_id')
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ حذف سرویس", callback_data=f"admin_delete_service_{sid}_{target_id}")]])
        try:
            await q.from_user.send_message(f"- {name} (ID: {sid})", reply_markup=kb)
        except Exception:
            pass

async def admin_user_purchases_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    target_id = int(q.data.split('_')[-1])
    await q.answer()

    purchases = None
    try:
        if hasattr(db, "get_user_purchase_history"):
            purchases = db.get_user_purchase_history(target_id)
        elif hasattr(db, "get_purchases_for_user"):
            purchases = db.get_purchases_for_user(target_id)
    except Exception as e:
        logger.warning("Fetching purchases failed: %s", e)

    if not purchases:
        try:
            await q.from_user.send_message("هیچ سابقه خریدی یافت نشد یا این قابلیت در پایگاه‌داده شما پیاده‌سازی نشده است.")
        except Exception:
            pass
        return

    for p in purchases[:30]:
        try:
            price = int(float(p.get('price', 0)))
        except Exception:
            price = 0
        ts = p.get('created_at') or p.get('timestamp', '-')
        txt = f"- پلن: {p.get('plan_name') or '-'} | مبلغ: {price:,} تومان | تاریخ: {ts}"
        try:
            await q.from_user.send_message(txt)
        except Exception:
            pass

async def admin_user_trial_reset_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    target_id = int(q.data.split('_')[-1])
    ok = False
    try:
        await q.answer()
        if hasattr(db, "reset_user_trial"):
            db.reset_user_trial(target_id); ok = True
        elif hasattr(db, "set_user_trial_used"):
            try:
                db.set_user_trial_used(target_id, False); ok = True
            except TypeError:
                if hasattr(db, "clear_user_trial"):
                    db.clear_user_trial(target_id); ok = True
    except Exception as e:
        logger.warning("Trial reset failed: %s", e)
        ok = False

    if ok:
        await _send_user_panel(update, target_id)
    else:
        try:
            await q.answer("❌ ریست تست ناموفق بود یا در DB پشتیبانی نشده است.", show_alert=True)
        except Exception:
            pass

async def admin_user_toggle_ban_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    info = db.get_user(target_id)
    if not info:
        await q.edit_message_text("❌ کاربر یافت نشد.")
        return

    ban_state = bool(info.get('is_banned'))
    ok = False
    try:
        if hasattr(db, "set_user_banned"):
            db.set_user_banned(target_id, not ban_state); ok = True
        elif ban_state and hasattr(db, "unban_user"):
            db.unban_user(target_id); ok = True
        elif not ban_state and hasattr(db, "ban_user"):
            db.ban_user(target_id); ok = True
    except Exception as e:
        logger.warning("Toggle ban failed: %s", e)
        ok = False

    if ok:
        await _send_user_panel(update, target_id)
    else:
        await q.edit_message_text("❌ تغییر وضعیت مسدودی ناموفق بود یا در DB پشتیبانی نشده است.")

# افزایش/کاهش موجودی → دریافت مبلغ
async def admin_user_addbal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    context.user_data["muid"] = target_id
    context.user_data["mop"] = "add"
    await q.edit_message_text(f"مبلغ افزایش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    return MANAGE_USER_AMOUNT

async def admin_user_subbal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    context.user_data["muid"] = target_id
    context.user_data["mop"] = "sub"
    await q.edit_message_text(f"مبلغ کاهش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    return MANAGE_USER_AMOUNT

async def admin_user_amount_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        target_id = int(q.data.split('_')[-1])
    except Exception:
        return USER_MANAGEMENT_MENU
    context.user_data.pop("muid", None)
    context.user_data.pop("mop", None)
    await _send_user_panel(update, target_id)
    return USER_MANAGEMENT_MENU

async def manage_user_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    txt = (em.text or "").strip().replace(",", "")
    try:
        amount = int(abs(float(txt)))
    except Exception:
        await em.reply_text("❌ مبلغ نامعتبر است. یک عدد مثبت وارد کنید.", reply_markup=_user_mgmt_keyboard())
        return MANAGE_USER_AMOUNT

    target_id = context.user_data.get("muid")
    op = context.user_data.get("mop")
    if not target_id or op not in ("add", "sub"):
        await em.reply_text("❌ حالت نامعتبر. دوباره تلاش کنید.", reply_markup=_user_mgmt_keyboard())
        return USER_MANAGEMENT_MENU

    delta = amount if op == "add" else -amount
    ok = _update_balance(target_id, delta)

    # پیام به کاربر
    try:
        info2 = db.get_user(target_id)
        new_bal = int(info2.get("balance", 0)) if info2 else None
    except Exception:
        new_bal = None

    if ok:
        await em.reply_text("✅ موجودی کاربر به‌روزرسانی شد.")
        # اطلاع‌رسانی به خود کاربر
        try:
            op_text = "افزایش" if delta >= 0 else "کاهش"
            amount_str = utils.format_toman(abs(delta), persian_digits=True)
            if new_bal is not None:
                new_bal_str = utils.format_toman(new_bal, persian_digits=True)
                note_txt = f"موجودی فعلی: {new_bal_str}."
            else:
                note_txt = ""
            await context.bot.send_message(
                chat_id=target_id,
                text=f"کیف پول شما توسط پشتیبانی {op_text} یافت به مبلغ {amount_str}. {note_txt}"
            )
        except Forbidden:
            pass
        except Exception as e:
            logger.warning("Notify user about balance change failed: %s", e)
    else:
        await em.reply_text("❌ به‌روزرسانی موجودی ناموفق بود یا در DB پشتیبانی نشده است.")

    # پاکسازی و بازگشت به پنل کاربر
    context.user_data.pop("muid", None)
    context.user_data.pop("mop", None)
    await _send_user_panel(update, target_id)
    return USER_MANAGEMENT_MENU

# -------------------------------
# حذف سرویس از سمت ادمین (پشتیبانی از الگوی جدید و قدیم)
# -------------------------------
async def admin_delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    raw = q.data.replace("admin_delete_service_", "", 1)
    parts = raw.split("_")
    service_id = None
    target_id = None
    try:
        service_id = int(parts[0])
        if len(parts) > 1:
            target_id = int(parts[1])
    except Exception:
        await q.edit_message_text("❌ شناسه سرویس نامعتبر است.")
        return

    svc = db.get_service(service_id)
    if not svc:
        await q.edit_message_text("❌ سرویس یافت نشد.")
        if target_id:
            await _send_user_panel(update, target_id)
        return

    await q.edit_message_text("در حال حذف سرویس از پنل...")
    success = await hiddify_api.delete_user_from_panel(svc['sub_uuid'])
    if success:
        db.delete_service(service_id)
        if target_id:
            await _send_user_panel(update, target_id)
        else:
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
# تایید/رد شارژ (در صورت استفاده)
# -------------------------------
async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        charge_id = int(q.data.split('_')[-1])
    except Exception:
        await q.edit_message_text("❌ شناسه شارژ نامعتبر است.")
        return
    try:
        if hasattr(db, "confirm_charge_request"):
            ok = db.confirm_charge_request(charge_id)
        elif hasattr(db, "admin_confirm_charge"):
            ok = db.admin_confirm_charge(charge_id)
        else:
            ok = False
    except Exception:
        ok = False
    await q.edit_message_text("✅ شارژ تایید شد." if ok else "❌ تایید شارژ ناموفق بود یا قبلاً پردازش شده است.")

async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await q.edit_message_text("✅ شارژ رد شد." if ok else "❌ رد شارژ ناموفق بود یا قبلاً پردازش شده است.")