# filename: bot/handlers/start.py
# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from typing import List

from telegram.ext import ContextTypes, ConversationHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.constants import ParseMode

import database as db
from bot.keyboards import get_main_menu_keyboard, get_admin_menu_keyboard
from bot.constants import ADMIN_MENU
from bot.handlers.charge import _get_payment_info_text
from bot.ui import nav_row, chunk, btn  # UI helpers
from bot import utils

try:
    from config import REFERRAL_BONUS_AMOUNT
except Exception:
    REFERRAL_BONUS_AMOUNT = 0

try:
    import jdatetime
except ImportError:
    jdatetime = None

logger = logging.getLogger(__name__)


def _kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


async def _send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None, disable_web_page_preview=False):
    q = getattr(update, "callback_query", None)
    if q:
        try:
            await q.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
        except BadRequest as e:
            emsg = str(e).lower()
            if "can't parse entities" in emsg or "can't find end of the entity" in emsg:
                try:
                    await q.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=None, disable_web_page_preview=disable_web_page_preview)
                except Exception:
                    try:
                        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)
                    except Exception:
                        pass
            else:
                try:
                    await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
                except BadRequest:
                    await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)
    else:
        try:
            await update.effective_message.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
        except BadRequest as e:
            emsg = str(e).lower()
            if "can't parse entities" in emsg or "can't find end of the entity" in emsg:
                await update.effective_message.reply_text(text=text, reply_markup=reply_markup, parse_mode=None, disable_web_page_preview=disable_web_page_preview)


def _format_hist_rows(rows: List[dict], empty_msg: str, row_fmt: str) -> str:
    if not rows:
        return empty_msg
    lines = []
    for r in rows:
        try:
            # sale_date یا created_at را با parser منعطف به تاریخ خوانا تبدیل می‌کنیم
            ds = r.get("sale_date") or r.get("created_at") or ""
            dt = utils.parse_date_flexible(ds)
            dt_s = dt.strftime("%Y-%m-%d %H:%M") if dt else (ds or "")
        except Exception:
            dt_s = r.get("sale_date") or r.get("created_at") or ""
        amount = r.get("price") or r.get("amount") or 0
        pname = r.get("plan_name") or "-"
        rtype = r.get("type") or ""
        try:
            amount_i = int(float(amount or 0))
        except Exception:
            amount_i = 0
        lines.append(row_fmt.format(dt=dt_s, amount=amount_i, name=pname, typ=rtype))
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username)

    # referral ?start=ref_<id>
    if getattr(context, "args", None) and context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            if referrer_id != user.id:
                db.set_referrer(user.id, referrer_id)
        except (ValueError, IndexError):
            logger.warning("Invalid referral link: %s", context.args[0])

    user_info = db.get_user(user.id)
    if user_info and user_info.get('is_banned'):
        if update.message:
            await update.message.reply_text("شما از استفاده از این ربات منع شده‌اید.")
        elif update.callback_query:
            await update.callback_query.answer("شما از استفاده از این ربات منع شده‌اید.", show_alert=True)
        return ConversationHandler.END

    text = "👋 به ربات خوش آمدید!"
    reply_markup = get_main_menu_keyboard(user.id)

    if update.callback_query:
        q = update.callback_query
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

    return ConversationHandler.END


async def user_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_menu_keyboard(update.effective_user.id))
    return ConversationHandler.END


async def admin_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ADMIN_MENU


async def admin_conv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_admin_menu_keyboard())
    return ConversationHandler.END


async def show_account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_or_create_user(user_id, update.effective_user.username)

    # تعداد سرویس‌ها
    services = db.get_user_services(user_id)
    services_count = len(services)

    # مصرف کل کاربر (اسنپ‌شات تجمیعی)
    try:
        total_usage_gb = db.get_total_user_traffic(user_id)
    except Exception:
        total_usage_gb = 0.0

    # تاریخ عضویت به جلالی
    join_date = user.get('join_date', '')
    join_date_jalali = "N/A"
    if jdatetime and join_date:
        try:
            dt = utils.parse_date_flexible(join_date)
            if dt:
                join_date_jalali = jdatetime.date.fromgregorian(date=dt.date()).strftime('%Y/%m/%d')
        except Exception:
            join_date_jalali = join_date or "N/A"

    balance_str = utils.format_toman(user.get("balance", 0), persian_digits=True)

    text = (
        "👤 اطلاعات حساب شما\n\n"
        f"▫️ شناسه عددی: {utils.to_persian_digits(str(user_id))}\n"
        f"▫️ موجودی کیف‌پول: {balance_str}\n"
        f"▫️ تعداد سرویس‌های فعال: {utils.to_persian_digits(str(services_count))}\n"
        f"▫️ مصرف کل: {utils.to_persian_digits(f'{total_usage_gb:.2f}')} GB\n"
        f"▫️ تاریخ عضویت: {join_date_jalali}"
    )

    keyboard = _kb([
        [InlineKeyboardButton("🧾 سوابق خرید", callback_data="acc_purchase_history"),
         InlineKeyboardButton("💳 سوابق شارژ", callback_data="acc_charge_history")],
        [InlineKeyboardButton("📄 راهنمای شارژ", callback_data="acc_charging_guide")],
        [InlineKeyboardButton("💳 شارژ حساب", callback_data="acc_start_charge")],
        [InlineKeyboardButton("🏠 بازگشت به منو", callback_data="home_menu")]
    ])
    await _send_or_edit(update, context, text, reply_markup=keyboard, parse_mode=None)


async def show_purchase_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    hist = db.get_user_sales_history(user_id)
    text = "🧾 سوابق خرید/تمدید شما:\n\n" + _format_hist_rows(
        hist,
        empty_msg="⛔️ سابقه‌ای یافت نشد.",
        row_fmt="• {dt} | {name} | {amount:,} تومان"
    )
    kb = _kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="acc_back_to_main")]])
    await _send_or_edit(update, context, text, reply_markup=kb, parse_mode=None)


async def show_charge_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    hist = db.get_user_charge_history(user_id)
    text = "💳 سوابق شارژ شما:\n\n" + _format_hist_rows(
        hist,
        empty_msg="⛔️ سابقه شارژی یافت نشد.",
        row_fmt="• {dt} | {typ} | {amount:,} تومان"
    )
    kb = _kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="acc_back_to_main")]])
    await _send_or_edit(update, context, text, reply_markup=kb, parse_mode=None)


async def show_charging_guide_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guide = _get_payment_info_text()
    kb = _kb([[InlineKeyboardButton("🔙 بازگشت", callback_data="acc_back_to_main")]])
    # راهنما ممکنه Markdown داشته باشه؛ با fallback می‌فرستیم
    await _send_or_edit(update, context, guide, reply_markup=kb, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        btn("📱 راهنمای اتصال", "guide_connection"),
        btn("💳 راهنمای شارژ حساب", "guide_charging"),
        btn("🛍️ راهنمای خرید از ربات", "guide_buying"),
    ]
    rows = chunk(buttons, cols=2)
    rows.append(nav_row(home_cb="home_menu"))
    await _send_or_edit(update, context, "📚 لطفاً موضوع راهنمای مورد نظر خود را انتخاب کنید:", reply_markup=_kb(rows), parse_mode=None)


async def show_guide_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
    data = q.data if q else ""
    key_map = {
        "guide_connection": "guide_connection",
        "guide_charging": "guide_charging",
        "guide_buying": "guide_buying",
    }
    setting_key = key_map.get(data, "")
    content = db.get_setting(setting_key) or "محتوایی برای این راهنما ثبت نشده است."
    kb = _kb([[InlineKeyboardButton("🔙 بازگشت به منوی راهنما", callback_data="guide_back_to_menu")]])
    await _send_or_edit(update, context, content, reply_markup=kb, parse_mode=None, disable_web_page_preview=True)


async def back_to_guide_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        return await show_guide(update, context)
    return await show_guide(update, context)


async def show_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    bonus_str = db.get_setting('referral_bonus_amount')
    try:
        bonus = int(float(bonus_str)) if bonus_str is not None else REFERRAL_BONUS_AMOUNT
    except (ValueError, TypeError):
        bonus = REFERRAL_BONUS_AMOUNT

    text = (
        "🎁 دوستان خود را دعوت کنید و هدیه بگیرید!\n\n"
        "با لینک اختصاصی زیر دوستان خود را دعوت کنید:\n"
        f"`{referral_link}`\n\n"
        f"با اولین خرید دوست شما، مبلغ {bonus:,.0f} تومان به کیف پول شما و همین مقدار به کیف پول دوستتان اضافه می‌شود."
    )
    # ارسال با fallback
    await _send_or_edit(update, context, text, reply_markup=None, parse_mode=ParseMode.MARKDOWN)