# filename: bot/handlers/admin/gift_codes.py
# -*- coding: utf-8 -*-

import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.error import BadRequest

from bot.constants import (
    ADMIN_MENU, GIFT_CODES_MENU,
    PROMO_GET_CODE, PROMO_GET_PERCENT, PROMO_GET_MAX_USES, PROMO_GET_EXPIRES,
    AWAIT_REFERRAL_BONUS
)
from bot import utils
import database as db

# state محلی برای دریافت مبلغ کد هدیه
CREATE_GIFT_AMOUNT = 201

# ---------------- Helpers ----------------
def _kb(rows): return InlineKeyboardMarkup(rows)

def _gift_root_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("🎁 مدیریت کدهای هدیه", callback_data="gift_menu_gift")],
        [InlineKeyboardButton("💳 مدیریت کدهای تخفیف", callback_data="gift_menu_promo")],
        [InlineKeyboardButton("٪ تخفیف همگانی", callback_data="global_discount_submenu")],
        [InlineKeyboardButton("💰 تنظیم هدیه دعوت", callback_data="gift_referral_bonus")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

def _gift_codes_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("➕ ساخت کد هدیه جدید", callback_data="gift_new_gift")],
        [InlineKeyboardButton("📋 لیست کدهای هدیه", callback_data="gift_list_gift")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="gift_root_menu")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

def _promo_codes_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("➕ ساخت کد تخفیف جدید", callback_data="promo_new")],
        [InlineKeyboardButton("📋 لیست کدهای تخفیف", callback_data="promo_list")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="gift_root_menu")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

def _back_to_gift_codes_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("🔙 بازگشت به کدهای هدیه", callback_data="gift_menu_gift")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

def _back_to_promo_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("🔙 بازگشت به کدهای تخفیف", callback_data="gift_menu_promo")],
        [InlineKeyboardButton("🏠 منوی ادمین", callback_data="admin_panel")]
    ])

def _cancel_gift_create_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("❌ لغو", callback_data="gift_create_cancel")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="gift_menu_gift")]
    ])

def _promo_cancel_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("❌ لغو", callback_data="promo_cancel")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="gift_menu_promo")]
    ])

def _promo_expires_kb() -> InlineKeyboardMarkup:
    return _kb([
        [InlineKeyboardButton("⏭️ بدون تاریخ (نامحدود)", callback_data="promo_skip_expires")],
        [InlineKeyboardButton("❌ لغو", callback_data="promo_cancel")]
    ])

def _send_or_edit_text(update: Update, text: str, reply_markup=None, parse_mode: ParseMode | None = ParseMode.HTML):
    """
    Helper همسان برای ارسال/ویرایش پیام‌ها با مدیریت خطاهای پارس مارک‌داون/HTML
    """
    async def _inner():
        q = getattr(update, "callback_query", None)
        if q:
            try: await q.answer()
            except Exception: pass
            try:
                await q.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            except BadRequest as e:
                emsg = str(e).lower()
                if "can't parse entities" in emsg or "can't find end of the entity" in emsg:
                    try:
                        await q.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
                    except Exception:
                        try:
                            await q.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
                        except Exception:
                            pass
                else:
                    try:
                        await q.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
                    except BadRequest as e2:
                        emsg2 = str(e2).lower()
                        if "can't parse entities" in emsg2 or "can't find end of the entity" in emsg2:
                            await q.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
        else:
            try:
                await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            except BadRequest as e:
                emsg = str(e).lower()
                if "can't parse entities" in emsg or "can't find end of the entity" in emsg:
                    await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
    return _inner()

# ---------------- Root menu ----------------
async def gift_code_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_or_edit_text(update, "🎁 مدیریت تخفیف و کد هدیه", reply_markup=_gift_root_kb())
    return GIFT_CODES_MENU

# ---------------- Gift codes submenu ----------------
async def admin_gift_codes_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_or_edit_text(update, "🎁 بخش مدیریت کدهای هدیه", reply_markup=_gift_codes_kb())
    return GIFT_CODES_MENU

async def list_gift_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    codes = db.get_all_gift_codes()
    if not codes:
        await _send_or_edit_text(update, "هیچ کد هدیه‌ای تا به حال ساخته نشده است.", reply_markup=_gift_codes_kb())
        return GIFT_CODES_MENU

    await _send_or_edit_text(update, "📋 لیست کدهای هدیه:", reply_markup=_back_to_gift_codes_kb(), parse_mode=ParseMode.MARKDOWN)

    # نمایش هر کد در یک پیام جداگانه
    for code in codes:
        status = "✅ استفاده شده" if code.get('is_used') else "🟢 فعال"
        used_by = f" (توسط: `{code.get('used_by')}`)" if code.get('used_by') else ""
        amount_str = utils.format_toman(code.get('amount', 0), persian_digits=True)
        text = f"`{code.get('code')}` - **{amount_str}** - {status}{used_by}"
        keyboard = None
        if not code.get('is_used'):
            keyboard = _kb([[InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_gift_code_{code.get('code')}")]])
        try:
            await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception:
            # در صورت خطای پارس
            await update.effective_message.reply_text(text, reply_markup=keyboard)
    return GIFT_CODES_MENU

async def delete_gift_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    code_to_delete = q.data.split('delete_gift_code_')[-1]
    if db.delete_gift_code(code_to_delete):
        await q.edit_message_text(f"✅ کد `{code_to_delete}` با موفقیت حذف شد.", parse_mode=ParseMode.MARKDOWN)
    else:
        await q.edit_message_text(f"❌ خطا: کد `{code_to_delete}` یافت نشد یا قبلاً حذف شده بود.", parse_mode=ParseMode.MARKDOWN)
    return GIFT_CODES_MENU

async def create_gift_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "لطفاً مبلغ کد هدیه را به تومان وارد کنید:"
    await _send_or_edit_text(update, text, reply_markup=_cancel_gift_create_kb())
    return CREATE_GIFT_AMOUNT

async def cancel_create_gift_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # لغو ساخت کد هدیه و بازگشت
    await admin_gift_codes_submenu(update, context)
    return GIFT_CODES_MENU

async def create_gift_amount_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.effective_message.text or "").strip().replace(",", ".")
    try:
        amount = float(txt)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await update.effective_message.reply_text("❗️ لطفاً یک مبلغ عددی و مثبت وارد کنید.", reply_markup=_cancel_gift_create_kb())
        return CREATE_GIFT_AMOUNT

    code = str(uuid.uuid4()).split('-')[0].upper()
    if db.create_gift_code(code, amount):
        amount_str = utils.format_toman(amount, persian_digits=True)
        await update.effective_message.reply_text(
            f"✅ کد هدیه با موفقیت ساخته شد:\n\n`{code}`\n\nمبلغ: **{amount_str}**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_gift_codes_kb()
        )
    else:
        await update.effective_message.reply_text(
            "❌ در ساخت کد هدیه خطایی رخ داد (احتمالاً کد تکراری است). لطفاً دوباره تلاش کنید.",
            reply_markup=_gift_codes_kb()
        )
    return GIFT_CODES_MENU

# ---------------- Promo codes submenu ----------------
async def admin_promo_codes_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_or_edit_text(update, "💳 بخش مدیریت کدهای تخفیف", reply_markup=_promo_codes_kb())
    return GIFT_CODES_MENU

async def list_promo_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_all_promo_codes() or []
    if not rows:
        await _send_or_edit_text(update, "هیچ کد تخفیفی تعریف نشده است.", reply_markup=_promo_codes_kb())
        return GIFT_CODES_MENU

    await _send_or_edit_text(update, "📋 لیست کدهای تخفیف:", reply_markup=_back_to_promo_kb())
    for p in rows:
        # p ممکن است Row یا dict باشد
        code = p.get('code') if isinstance(p, dict) else p['code']
        percent = p.get('percent') if isinstance(p, dict) else p['percent']
        max_uses = p.get('max_uses') if isinstance(p, dict) else p['max_uses']
        used_count = p.get('used_count') if isinstance(p, dict) else p['used_count']
        expires_at = p.get('expires_at') if isinstance(p, dict) else p['expires_at']
        first_purchase_only = p.get('first_purchase_only') if isinstance(p, dict) else p['first_purchase_only']
        is_active = p.get('is_active') if isinstance(p, dict) else p['is_active']

        status = "🟢 فعال" if is_active else "🔴 غیرفعال"
        exp = utils.parse_date_flexible(expires_at).strftime('%Y-%m-%d') if expires_at else "همیشگی"
        uses = f"{used_count}/{max_uses}" if (max_uses or 0) > 0 else f"{used_count}"
        text = f"`{code}` | {percent}% | استفاده: {uses} | انقضا: {exp} | فقط خرید اول: {'بله' if first_purchase_only else 'خیر'} | {status}"
        kb = _kb([[InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_promo_code_{code}")]])
        try:
            await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            await update.effective_message.reply_text(text, reply_markup=kb)
    return GIFT_CODES_MENU

async def delete_promo_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    code_to_delete = q.data.split('delete_promo_code_')[-1]
    if db.delete_promo_code(code_to_delete):
        await q.edit_message_text(f"✅ کد تخفیف `{code_to_delete}` با موفقیت حذف شد.", parse_mode=ParseMode.MARKDOWN)
    else:
        await q.edit_message_text(f"❌ خطا: کد `{code_to_delete}` یافت نشد.", parse_mode=ParseMode.MARKDOWN)
    return GIFT_CODES_MENU

# ---------------- Promo create flow (inline navigation + text inputs) ----------------
async def create_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['promo'] = {}
    await _send_or_edit_text(update, "کد تخفیف را وارد کنید (مثلاً SUMMER20):", reply_markup=_promo_cancel_kb())
    return PROMO_GET_CODE

async def promo_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('promo', None)
    await _send_or_edit_text(update, "❌ عملیات لغو شد.", reply_markup=_promo_codes_kb())
    return GIFT_CODES_MENU

async def promo_code_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = (update.message.text or "").strip().upper()
    if db.get_promo_code(code):
        await update.message.reply_text("این کد قبلاً وجود دارد. لطفاً کد دیگری وارد کنید.", reply_markup=_promo_cancel_kb())
        return PROMO_GET_CODE
    context.user_data['promo'] = {'code': code}
    await update.message.reply_text("درصد تخفیف را وارد کنید (مثلاً 30):", reply_markup=_promo_cancel_kb())
    return PROMO_GET_PERCENT

async def promo_percent_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        percent = int((update.message.text or "").strip())
        if not (0 < percent <= 100):
            raise ValueError
    except Exception:
        await update.message.reply_text("لطفاً یک عدد بین 1 تا 100 وارد کنید.", reply_markup=_promo_cancel_kb())
        return PROMO_GET_PERCENT

    context.user_data.setdefault('promo', {})['percent'] = percent
    await update.message.reply_text("حداکثر تعداد استفاده را وارد کنید (برای نامحدود 0):", reply_markup=_promo_cancel_kb())
    return PROMO_GET_MAX_USES

async def promo_max_uses_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        max_uses = int((update.message.text or "").strip())
        if max_uses < 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("لطفاً یک عدد صحیح و مثبت (یا 0) وارد کنید.", reply_markup=_promo_cancel_kb())
        return PROMO_GET_MAX_USES

    context.user_data.setdefault('promo', {})['max_uses'] = max_uses
    await update.message.reply_text(
        "تعداد روز اعتبار کد را وارد کنید (مثلاً 5).",
        reply_markup=_promo_expires_kb()
    )
    return PROMO_GET_EXPIRES

async def promo_days_valid_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int((update.message.text or "").strip())
        if days <= 0:
            raise ValueError
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    except Exception:
        await update.message.reply_text("لطفاً یک عدد مثبت وارد کنید (مثلاً 5).", reply_markup=_promo_expires_kb())
        return PROMO_GET_EXPIRES

    context.user_data.setdefault('promo', {})['expires_at'] = expires_at
    # سوال «فقط خرید اول؟» به صورت شیشه‌ای
    kb = _kb([
        [InlineKeyboardButton("بله", callback_data="promo_first_yes"),
         InlineKeyboardButton("خیر", callback_data="promo_first_no")],
        [InlineKeyboardButton("❌ لغو", callback_data="promo_cancel")]
    ])
    await update.message.reply_text("آیا این کد فقط برای خرید اول باشد؟", reply_markup=kb)
    # این مرحله را با کال‌بک نهایی می‌کنیم؛ نیازی به state جدید نیست
    return GIFT_CODES_MENU

async def promo_skip_expires_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.setdefault('promo', {})['expires_at'] = None
    kb = _kb([
        [InlineKeyboardButton("بله", callback_data="promo_first_yes"),
         InlineKeyboardButton("خیر", callback_data="promo_first_no")],
        [InlineKeyboardButton("❌ لغو", callback_data="promo_cancel")]
    ])
    await q.edit_message_text("آیا این کد فقط برای خرید اول باشد؟", reply_markup=kb)
    return GIFT_CODES_MENU

async def promo_first_purchase_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    first_only = True if q.data.endswith("_yes") else False

    promo = context.user_data.get('promo') or {}
    code = promo.get('code')
    percent = promo.get('percent')
    max_uses = promo.get('max_uses')
    expires_at = promo.get('expires_at')

    if not code or percent is None or max_uses is None:
        await q.edit_message_text("❌ داده‌های کد تخفیف کامل نیست. از ابتدا شروع کنید.", reply_markup=_promo_codes_kb())
        context.user_data.pop('promo', None)
        return GIFT_CODES_MENU

    # ذخیره در DB
    db.add_promo_code(code, percent, max_uses, expires_at, first_only)

    await q.edit_message_text(f"✅ کد تخفیف `{code}` با موفقیت ساخته شد.", parse_mode=ParseMode.MARKDOWN, reply_markup=_promo_codes_kb())
    context.user_data.pop('promo', None)
    return GIFT_CODES_MENU

# ---------------- Referral bonus (inline) ----------------
async def ask_referral_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_bonus = db.get_setting('referral_bonus_amount') or "5000"
    msg = (
        f"💰 تنظیم هدیه دعوت\n\n"
        f"مبلغ فعلی هدیه دعوت: {int(float(current_bonus)):,} تومان\n\n"
        "مبلغ جدید را به تومان وارد کنید:"
    )
    await _send_or_edit_text(update, msg, reply_markup=_kb([[InlineKeyboardButton("❌ لغو", callback_data="gift_referral_cancel")]]))
    return AWAIT_REFERRAL_BONUS

async def referral_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_or_edit_text(update, "❌ عملیات لغو شد.", reply_markup=_gift_root_kb())
    return GIFT_CODES_MENU

async def referral_bonus_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.effective_message.text or "").strip().replace(",", "")
    try:
        amount = int(float(txt))
        if amount < 0:
            raise ValueError
    except Exception:
        await update.effective_message.reply_text("❌ مبلغ نامعتبر است. یک عدد صحیح وارد کنید.", reply_markup=_kb([[InlineKeyboardButton("❌ لغو", callback_data="gift_referral_cancel")]]))
        return AWAIT_REFERRAL_BONUS

    db.set_setting('referral_bonus_amount', str(amount))
    await update.effective_message.reply_text(
        f"✅ مبلغ هدیه دعوت به {amount:,} تومان تغییر کرد.",
        reply_markup=_gift_root_kb()
    )
    return GIFT_CODES_MENU