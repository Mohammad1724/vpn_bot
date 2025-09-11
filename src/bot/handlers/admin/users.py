# bot/handlers/admin/users.py
# -*- coding: utf-8 -*-

import re
import logging
import asyncio
from datetime import datetime
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
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
# Helpers (Inline UI)
# -------------------------------

def _user_mgmt_root_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 جستجو با ID", callback_data="admin_users_ask_id")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")],
    ])

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
        [InlineKeyboardButton("🔄 بروزرسانی پنل", callback_data=f"admin_user_refresh_{target_id}")],
        [
            InlineKeyboardButton("🔙 مدیریت کاربران", callback_data="admin_users"),
            InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel"),
        ]
    ]
    return InlineKeyboardMarkup(rows)

def _amount_prompt_kb(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data=f"admin_user_amount_cancel_{target_id}")]])

async def _send_new(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb: InlineKeyboardMarkup | None = None, pm: str | None = None):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=kb, parse_mode=pm)
    else:
        await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=pm)

def _sanitize_for_code(s: str) -> str:
    return (s or "").replace("`", "")

async def _render_user_panel_text(target_id: int) -> tuple[str, bool]:
    try:
        info = db.get_user(target_id)
        if not info:
            return "❌ کاربر یافت نشد.", False

        try:
            services = db.get_user_services(target_id) or []
        except Exception as e:
            logger.error(f"Error fetching services for user {target_id}: {e}")
            services = []

        ban_state = bool(info.get('is_banned'))

        username = info.get('username') or "-"
        if username != "-" and not username.startswith("@"):
            username = f"@{username}"
        # Escape Markdown special chars
        username = username.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")

        try:
            total_usage_gb = db.get_total_user_traffic(target_id)
        except Exception as e:
            logger.error(f"Error getting traffic for user {target_id}: {e}")
            total_usage_gb = 0.0

        text = (
            f"👤 شناسه: `{target_id}`\n"
            f"👥 نام کاربری: `{username}`\n"
            f"💰 موجودی: {int(info.get('balance', 0)):,} تومان\n"
            f"🧪 تست: {'استفاده کرده' if info.get('has_used_trial') else 'آزاد'}\n"
            f"🚫 وضعیت: {'مسدود' if ban_state else 'آزاد'}\n"
            f"📋 تعداد سرویس‌ها: {len(services)}\n"
            f"📊 مصرف کل (همه نودها): {total_usage_gb:.2f} GB"
        )
        return text, ban_state

    except Exception as e:
        logger.error(f"Error in _render_user_panel_text for user {target_id}: {e}", exc_info=True)
        return "❌ خطای داخلی در نمایش اطلاعات کاربر.", False


def _ensure_user_exists(user_id: int):
    try:
        if hasattr(db, "get_or_create_user"):
            db.get_or_create_user(user_id)
    except Exception:
        pass

def _update_balance(user_id: int, delta: int) -> bool:
    _ensure_user_exists(user_id)
    try:
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
# Entry Point (Inline UI)
# -------------------------------

async def user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "👥 مدیریت کاربران\n\nشناسه عددی کاربر را تایپ کنید یا از دکمه زیر استفاده کنید."
    await _send_new(update, context, text, _user_mgmt_root_inline())
    return USER_MANAGEMENT_MENU

async def user_management_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    برای دکمه «🔙 مدیریت کاربران».
    پیام پنل کاربر را حذف و منوی اصلی مدیریت کاربران را نشان می‌دهد.
    """
    return await user_management_menu(update, context)

async def ask_user_id_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    🔥 اصلاح شده: فقط state رو تغییر میده — پیام رو عوض نمی‌کنه!
    کاربر باید مستقیماً ID رو بفرسته — بدون نمایش پیام جدید.
    """
    q = update.callback_query
    await q.answer("✅ منتظر ارسال ID کاربر هستم...", show_alert=False)
    return USER_MANAGEMENT_MENU

# -------------------------------
# User Panel
# -------------------------------

async def _send_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int):
    q = getattr(update, "callback_query", None)
    chat_id = q.from_user.id if q else update.effective_chat.id

    try:
        text, ban_state = await _render_user_panel_text(target_id)
    except Exception as e:
        logger.error(f"Failed to render user panel for {target_id}: {e}")
        text = "❌ خطایی در بارگذاری اطلاعات کاربر رخ داد."
        ban_state = False

    kb = None
    try:
        kb = _action_kb(target_id, ban_state)
    except Exception as e:
        logger.error(f"Failed to generate action keyboard for {target_id}: {e}")
        kb = None

    try:
        if q:
            try:
                await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception:
                # fallback to plain text
                await q.edit_message_text(text, reply_markup=kb)
        else:
            try:
                await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception:
                await update.effective_message.reply_text(text, reply_markup=kb)
    except Exception as e:
        logger.error(f"Failed to send user panel to {chat_id}: {e}")
        try:
            await context.bot.send_message(chat_id=chat_id, text="❌ خطایی در نمایش پنل کاربر رخ داد. لطفاً دوباره تلاش کنید.")
        except Exception:
            pass

async def manage_user_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    text = (em.text or "").strip()
    if not re.fullmatch(r"\d+", text):
        await em.reply_text("شناسه معتبر نیست. یک عدد مثبت وارد کنید.", reply_markup=_user_mgmt_root_inline())
        return USER_MANAGEMENT_MENU
    target_id = int(text)
    if target_id <= 0:
        await em.reply_text("شناسه معتبر نیست. یک عدد مثبت وارد کنید.", reply_markup=_user_mgmt_root_inline())
        return USER_MANAGEMENT_MENU
    await _send_user_panel(update, context, target_id)
    return USER_MANAGEMENT_MENU

# -------------------------------
# User Actions (Callbacks)
# -------------------------------

async def admin_user_refresh_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    await _send_user_panel(update, context, target_id)

async def admin_user_services_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    target_id = int(q.data.split('_')[-1])
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
        server_name = s.get('server_name') or "-"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ حذف سرویس", callback_data=f"admin_delete_service_{sid}_{target_id}")]])
        try:
            await q.from_user.send_message(f"- {name} (ID: {sid}) | نود: {server_name}", reply_markup=kb)
        except Exception:
            pass

async def admin_user_purchases_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    target_id = int(q.data.split('_')[-1])
    await q.answer()
    purchases = db.get_user_sales_history(target_id)
    if not purchases:
        try:
            await q.from_user.send_message("هیچ سابقه خریدی یافت نشد.")
        except Exception:
            pass
        return
    for p in purchases[:30]:
        try:
            price = int(float(p.get('price', 0)))
        except Exception:
            price = 0
        ts = p.get('sale_date') or '-'
        txt = f"- پلن: {p.get('plan_name') or '-'} | مبلغ: {price:,} تومان | تاریخ: {ts}"
        try:
            await q.from_user.send_message(txt)
        except Exception:
            pass

async def admin_user_trial_reset_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    target_id = int(q.data.split('_')[-1])
    db.reset_user_trial(target_id)
    await q.answer("✅ وضعیت تست کاربر ریست شد.", show_alert=False)
    await _send_user_panel(update, context, target_id)

async def admin_user_toggle_ban_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    info = db.get_user(target_id)
    if not info:
        await q.edit_message_text("❌ کاربر یافت نشد.")
        return
    ban_state = bool(info.get('is_banned'))
    db.set_user_ban_status(target_id, not ban_state)
    await _send_user_panel(update, context, target_id)

async def admin_user_addbal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    context.user_data["muid"] = target_id
    context.user_data["mop"] = "add"
    try:
        await q.edit_message_text(f"➕ مبلغ افزایش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    except BadRequest:
        await context.bot.send_message(chat_id=q.from_user.id, text=f"➕ مبلغ افزایش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    return MANAGE_USER_AMOUNT

async def admin_user_subbal_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target_id = int(q.data.split('_')[-1])
    context.user_data["muid"] = target_id
    context.user_data["mop"] = "sub"
    try:
        await q.edit_message_text(f"➖ مبلغ کاهش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
    except BadRequest:
        await context.bot.send_message(chat_id=q.from_user.id, text=f"➖ مبلغ کاهش موجودی برای کاربر {target_id} را وارد کنید:", reply_markup=_amount_prompt_kb(target_id))
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
    await _send_user_panel(update, context, target_id)
    return USER_MANAGEMENT_MENU

async def manage_user_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    em = update.effective_message
    txt = (em.text or "").strip().replace(",", "").replace("٬", "")
    try:
        amount = int(abs(float(txt)))
    except Exception:
        await em.reply_text("❌ مبلغ نامعتبر است. یک عدد مثبت وارد کنید.", reply_markup=_user_mgmt_root_inline())
        return MANAGE_USER_AMOUNT

    target_id = context.user_data.get("muid")
    op = context.user_data.get("mop")
    if not target_id or op not in ("add", "sub"):
        await em.reply_text("❌ حالت نامعتبر. دوباره تلاش کنید.", reply_markup=_user_mgmt_root_inline())
        return USER_MANAGEMENT_MENU

    delta = amount if op == "add" else -amount
    ok = _update_balance(target_id, delta)

    if ok:
        await em.reply_text("✅ موجودی کاربر به‌روزرسانی شد.", reply_markup=ReplyKeyboardRemove())
        try:
            info2 = db.get_user(target_id)
            new_bal = int(info2.get("balance", 0)) if info2 else None
            op_text = "افزایش" if delta >= 0 else "کاهش"
            amount_str = utils.format_toman(abs(delta), persian_digits=True)
            note_txt = f"موجودی فعلی: {utils.format_toman(new_bal, persian_digits=True)}." if new_bal is not None else ""
            await context.bot.send_message(chat_id=target_id, text=f"کیف پول شما توسط پشتیبانی {op_text} یافت به مبلغ {amount_str}. {note_txt}")
        except Forbidden:
            pass
        except Exception as e:
            logger.warning("Notify user about balance change failed: %s", e)
    else:
        await em.reply_text("❌ به‌روزرسانی موجودی ناموفق بود یا در DB پشتیبانی نشده است.", reply_markup=ReplyKeyboardRemove())

    context.user_data.pop("muid", None)
    context.user_data.pop("mop", None)
    await _send_user_panel(update, context, target_id)
    return USER_MANAGEMENT_MENU

async def admin_delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    raw = q.data.replace("admin_delete_service_", "", 1)
    parts = raw.split("_")
    service_id = target_id = None
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
            await _send_user_panel(update, context, target_id)
        return

    server_name = svc.get('server_name')
    try:
        await q.edit_message_text("در حال حذف سرویس از پنل... ⏳")
    except BadRequest:
        pass

    success = await hiddify_api.delete_user_from_panel(svc['sub_uuid'], server_name=server_name)

    if not success:
        try:
            probe = await hiddify_api.get_user_info(svc['sub_uuid'], server_name=server_name)
            if isinstance(probe, dict) and probe.get("_not_found"):
                success = True
        except Exception:
            pass

    if success:
        db.delete_service(service_id)
        if target_id:
            await _send_user_panel(update, context, target_id)
        else:
            try:
                await q.edit_message_text(f"✅ سرویس {svc.get('name') or service_id} با موفقیت از پنل و ربات حذف شد.")
            except BadRequest:
                pass
    else:
        try:
            await q.edit_message_text("❌ حذف سرویس از پنل ناموفق بود.")
        except BadRequest:
            pass

# -------------------------------
# Broadcast (untouched)
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
# Confirm/Reject Charge
# -------------------------------

async def admin_confirm_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        charge_id = int(q.data.split('_')[3])
    except (IndexError, ValueError):
        await q.edit_message_caption("❌ اطلاعات دکمه نامعتبر است.")
        return

    req = db.get_charge_request(charge_id)
    if not req:
        await q.edit_message_caption("❌ درخواست شارژ یافت نشد یا قبلاً پردازش شده است.")
        return

    user_id = int(req['user_id'])
    amount = int(float(req['amount']))
    promo_code_in = (req.get('note') or "").strip().upper()

    ok = db.confirm_charge_request(charge_id)
    if not ok:
        await q.edit_message_caption("❌ تایید شارژ ناموفق بود (احتمالاً در DB).")
        return

    bonus_applied = 0
    try:
        if hasattr(db, "get_user_charge_count") and db.get_user_charge_count(user_id) == 1:
            pc = (db.get_setting('first_charge_code') or '').upper()
            pct = int(db.get_setting('first_charge_bonus_percent') or 0)
            exp_raw = db.get_setting('first_charge_expires_at') or ''
            exp_dt = utils.parse_date_flexible(exp_raw) if exp_raw else None
            now = datetime.now().astimezone()

            if promo_code_in and promo_code_in == pc and pct > 0 and (not exp_dt or now <= exp_dt):
                bonus = int(amount * (pct / 100.0))
                if bonus > 0:
                    _update_balance(user_id, bonus)
                    bonus_applied = bonus
    except Exception as e:
        logger.error(f"Error applying first charge bonus: {e}")

    final_text = f"✅ مبلغ {amount:,} تومان برای کاربر `{user_id}` تایید شد."
    if bonus_applied > 0:
        final_text += f"\n🎁 پاداش شارژ اول به مبلغ {bonus_applied:,} تومان نیز اعمال شد."

    await q.edit_message_caption(final_text, parse_mode=ParseMode.MARKDOWN)

    try:
        user_info = db.get_user(user_id)
        new_balance = user_info['balance'] if user_info else 0
        user_message = f"✅ حساب شما به مبلغ {amount:,} تومان شارژ شد."
        if bonus_applied > 0:
            user_message += f"\n🎁 شما {bonus_applied:,} تومان پاداش شارژ اول دریافت کردید."
        user_message += f"\n💰 موجودی جدید شما: {new_balance:,.0f} تومان"
        await context.bot.send_message(chat_id=user_id, text=user_message)
    except Exception as e:
        logger.warning(f"Failed to notify user {user_id} about successful charge: {e}")


async def admin_reject_charge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        charge_id = int(q.data.split('_')[3])
        user_id = int(q.data.split('_')[4])
    except (IndexError, ValueError):
        await q.edit_message_caption("❌ اطلاعات دکمه نامعتبر است.")
        return

    if db.reject_charge_request(charge_id):
        await q.edit_message_caption(f"❌ درخواست شارژ کاربر `{user_id}` رد شد.")
        try:
            await context.bot.send_message(chat_id=user_id, text="❌ متاسفانه درخواست شارژ شما توسط ادمین رد شد.")
        except Exception:
            pass
    else:
        await q.edit_message_caption("❌ عملیات ناموفق بود یا درخواست قبلاً پردازش شده است.")